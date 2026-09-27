import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const [htmlPath, usbPath] = process.argv.slice(2);
if (!htmlPath || !usbPath) {
  throw new Error('usage: node test_installer_usb_session.mjs flash.html UsbSerialManager.kt');
}

const html = readFileSync(htmlPath, 'utf8');
const usb = readFileSync(usbPath, 'utf8');
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
console.log('USB session lifecycle: OK');
