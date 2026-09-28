import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const [htmlPath, usbPath] = process.argv.slice(2);
if (!htmlPath || !usbPath) {
  throw new Error('usage: node test_installer_usb_session.mjs flash.html UsbSerialManager.kt');
}

const html = readFileSync(htmlPath, 'utf8');
const usb = readFileSync(usbPath, 'utf8');
assert.doesNotMatch(html, /readFlashSlowRom|ROM read flash block/,
  'partition reads must not use the fragile 64-byte ROM polling path');
const readStart = html.indexOf('async function readSlipPacketResync(');
const readEnd = html.indexOf('\nfunction parsePartitionTable', readStart);
assert.ok(readStart >= 0 && readEnd > readStart, 'RAM-backed Flash reader was not found');

const emittedLogs = [];
const flashContext = {
  Uint8Array,
  log(message) { emittedLogs.push(String(message)); },
  bytesToB64(bytes) { return Buffer.from(bytes).toString('base64'); },
  Android: {
    md5Base64(base64) {
      return createHash('md5').update(Buffer.from(base64, 'base64')).digest('hex');
    },
  },
  setTimeout,
};
vm.createContext(flashContext);
vm.runInContext(html.slice(readStart, readEnd) +
  '\nglobalThis.readFlashCheckedForTest = readFlashChecked;', flashContext);

const expectedBytes = Uint8Array.from({ length: 128 }, (_, i) => (i * 7) & 0xff);
expectedBytes[13] = 0xc0;
expectedBytes[14] = 0xdb;
let stubRuns = 0;
const progress = [];
const acknowledgements = [];
const int32 = value => Uint8Array.from([
  value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff,
]);
const append = (left, right) => {
  const result = new Uint8Array(left.length + right.length);
  result.set(left, 0);
  result.set(right, left.length);
  return result;
};
const words = bytes => Array.from({ length: bytes.length / 4 }, (_, i) =>
  (bytes[i * 4] | (bytes[i * 4 + 1] << 8) | (bytes[i * 4 + 2] << 16) |
    (bytes[i * 4 + 3] << 24)) >>> 0);
const digestBytes = createHash('md5').update(expectedBytes).digest();
const responsePackets = [expectedBytes.slice(0, 64), expectedBytes.slice(64), new Uint8Array(digestBytes)];
const originalTrace = function originalTransportTrace() {};
const slipFrame = payload => {
  const encoded = [0xc0];
  for (const byte of payload) {
    if (byte === 0xc0) encoded.push(0xdb, 0xdc);
    else if (byte === 0xdb) encoded.push(0xdb, 0xdd);
    else encoded.push(byte);
  }
  encoded.push(0xc0);
  return Uint8Array.from(encoded);
};
const framedBytes = packets => {
  const frames = packets.map(slipFrame);
  return frames.reduce(append, new Uint8Array(0));
};
const transportFor = (bytes, onWrite = async () => {}) => ({
  tracing: false,
  trace: originalTrace,
  SLIP_END: 0xc0,
  SLIP_ESC: 0xdb,
  SLIP_ESC_END: 0xdc,
  SLIP_ESC_ESC: 0xdd,
  buffer: bytes,
  appendArray: append,
  async write(ack) { await onWrite(ack); },
});
const readOnlyLoader = {
  IS_STUB: false,
  ESP_READ_FLASH: 0xd2,
  FLASH_READ_TIMEOUT: 1000,
  _appendArray: append,
  _intToByteArray: int32,
  async runStub() { stubRuns++; this.IS_STUB = true; },
  async checkCommand(name, op, request) {
    assert.equal(name, 'read flash (64-byte packets)');
    assert.equal(op, 0xd2);
    assert.deepEqual(words(request), [0x8000, expectedBytes.length, 4096, 64]);
    return 0;
  },
  transport: transportFor(append(Uint8Array.of(0xff, 0xff, 0xff, 0xc0), framedBytes(responsePackets)),
    async ack => acknowledgements.push(words(ack)[0])),
};
const readBytes = await flashContext.readFlashCheckedForTest(
  readOnlyLoader, 0x8000, expectedBytes.length,
  (done, total) => progress.push([done, total]));
assert.deepEqual(Array.from(readBytes), Array.from(expectedBytes));
assert.equal(stubRuns, 1, 'reader did not start the RAM stub for a ROM session');
assert.deepEqual(acknowledgements, [64, 128], 'reader did not ACK each 64-byte packet');
assert.deepEqual(progress, [[expectedBytes.length, expectedBytes.length]]);
assert.equal(readOnlyLoader.transport.buffer.length, 0,
  'reader did not consume the trailing MD5 frame');
assert.equal(readOnlyLoader.transport.tracing, false, 'temporary USB tracing was not restored');
assert.equal(readOnlyLoader.transport.trace, originalTrace,
  'the original transport trace callback was not restored');

const corruptPackets = [new Uint8Array(64), new Uint8Array(64), new Uint8Array(16)];
const corruptRead = {
  IS_STUB: true,
  ESP_READ_FLASH: 0xd2,
  FLASH_READ_TIMEOUT: 1000,
  _appendArray: append,
  _intToByteArray: int32,
  async checkCommand() { return 0; },
  transport: transportFor(framedBytes(corruptPackets)),
};
await assert.rejects(
  flashContext.readFlashCheckedForTest(corruptRead, 0x8000, expectedBytes.length),
  /контрольная сумма Flash не совпала/i,
  'mismatched Flash read digest must stop before partition data is parsed'
);

const noisyTransport = {
  IS_STUB: true,
  ESP_READ_FLASH: 0xd2,
  FLASH_READ_TIMEOUT: 1000,
  _appendArray: append,
  _intToByteArray: int32,
  async checkCommand() { return 0; },
  transport: transportFor(new Uint8Array(257).fill(0xff)),
};
await assert.rejects(
  flashContext.readFlashCheckedForTest(noisyTransport, 0x8000, expectedBytes.length),
  /более 256 байт шума/i,
  'resynchronization must stop after its bounded noise allowance'
);
assert.ok(emittedLogs.some(message => message.includes('пропущено 3 байт USB-шума')),
  'recovered USB noise was not added to the diagnostic log');
assert.equal(noisyTransport.transport.tracing, false,
  'USB trace mode was left enabled after a failed read');

const start = html.indexOf('class AndroidSerialPort {');
const end = html.indexOf('\nconst terminal =', start);
assert.ok(start >= 0 && end > start, 'WebSerial adapter was not found');

const disconnectStart = usb.indexOf('    fun disconnect() {');
const disconnectEnd = usb.indexOf('\n    //', disconnectStart);
assert.ok(disconnectStart >= 0 && disconnectEnd > disconnectStart);
const nativeDisconnect = usb.slice(disconnectStart, disconnectEnd);
assert.doesNotMatch(nativeDisconnect, /webView\.post|__usbDisconnected/,
  'an intentional disconnect must not schedule a stale event for a later session');
assert.match(usb, /readLoop\(currentPort, session\)/);
assert.match(usb, /private fun readLoop\(activePort: UsbSerialPort, session: Long\)/);
assert.match(usb, /sessionGeneration\.get\(\) == session/);
assert.doesNotMatch(usb, /val len = port\?\.read/,
  'a previous read thread must not steal bytes from the next serial port');

const context = {
  window: {},
  Android: { disconnect() {}, readData() { return ''; } },
  ReadableStream: class { constructor(source) { this.source = source; } },
  WritableStream: class { constructor(sink) { this.sink = sink; } },
  setTimeout,
};
vm.createContext(context);
vm.runInContext(html.slice(start, end) + '\nglobalThis.SerialPortForTest = AndroidSerialPort;', context);
assert.equal(typeof context.disconnectCurrentTransport, 'function',
  'an internal reconnect must close its own stream synchronously');

const first = new context.SerialPortForTest();
context.disconnectCurrentTransport();
assert.equal(first._closed, true, 'previous stream is still reading USB data');
const second = new context.SerialPortForTest();
assert.equal(second._closed, false, 'fresh session must remain readable');
await first.close();
assert.equal(second._closed, false, 'late close of a previous stream closed the new session');
context.disconnectCurrentTransport();
assert.equal(second._closed, true, 'second stream did not close at its own disconnect');
console.log('USB session lifecycle and read-only Flash reader: OK');
