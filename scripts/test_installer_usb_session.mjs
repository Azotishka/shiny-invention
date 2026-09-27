import assert from 'node:assert/strict';
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
const readStart = html.indexOf('async function readFlashChecked(');
const readEnd = html.indexOf('\nfunction parsePartitionTable', readStart);
assert.ok(readStart >= 0 && readEnd > readStart, 'RAM-backed Flash reader was not found');

const flashContext = { log() {} };
vm.createContext(flashContext);
vm.runInContext(html.slice(readStart, readEnd) +
  '\nglobalThis.readFlashCheckedForTest = readFlashChecked;', flashContext);

const expectedBytes = Uint8Array.from({ length: 32 }, (_, i) => (i * 7) & 0xff);
let stubRuns = 0;
let readCalls = 0;
const progress = [];
const readOnlyLoader = {
  IS_STUB: false,
  async runStub() { stubRuns++; this.IS_STUB = true; },
  async readFlash(address, size, onPacket) {
    readCalls++;
    assert.equal(address, 0x8000);
    assert.equal(size, expectedBytes.length);
    onPacket(new Uint8Array(1), size, size);
    return expectedBytes;
  },
};
const readBytes = await flashContext.readFlashCheckedForTest(
  readOnlyLoader, 0x8000, expectedBytes.length,
  (done, total) => progress.push([done, total]));
assert.deepEqual(Array.from(readBytes), Array.from(expectedBytes));
assert.equal(stubRuns, 1, 'reader did not start the RAM stub for a ROM session');
assert.equal(readCalls, 1);
assert.deepEqual(progress, [[expectedBytes.length, expectedBytes.length]]);

const shortRead = {
  IS_STUB: true,
  async readFlash() { return new Uint8Array(expectedBytes.length - 1); },
};
await assert.rejects(
  flashContext.readFlashCheckedForTest(shortRead, 0x8000, expectedBytes.length),
  /короткое чтение/i,
  'truncated Flash reads must stop before partition data is parsed'
);

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
