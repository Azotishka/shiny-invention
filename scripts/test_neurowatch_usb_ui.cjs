'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const scriptPath = process.argv[2];
assert.ok(scriptPath, 'pass the generated updater JavaScript path');
const fullScript = fs.readFileSync(scriptPath, 'utf8');
const marker = "(() => {\n  const out = document.getElementById('usbHealthText');";
const start = fullScript.indexOf(marker);
assert.notEqual(start, -1, 'unified USB diagnostics block is missing');
const close = fullScript.indexOf('\n})();', start);
assert.notEqual(close, -1, 'USB diagnostics block is not closed');
const usbScript = fullScript.slice(start, close + '\n})();'.length);

const ids = [
  'usbHealthText', 'flashBtn', 'preflightBtn', 'usbPermissionBtn',
  'usbRefreshBtn', 'usbDot', 'usbStatus', 'eraseBtn', 'copyDiagBtn', 'log'
];
const elements = new Map();
for (const id of ids) {
  const listeners = {};
  elements.set(id, {
    id,
    disabled: false,
    className: '',
    textContent: '',
    listeners,
    addEventListener(name, fn) { listeners[name] = fn; },
    fire(name) { if (listeners[name]) listeners[name](); }
  });
}
let snapshot = { usbHost: true, count: 0, devices: [] };
let diagnosticsCalls = 0;
let permissionRequests = 0;
const events = [];
const intervals = [];
const timeouts = [];
const documentListeners = {};
const document = {
  hidden: false,
  getElementById(id) { return elements.get(id); },
  addEventListener(name, fn) { documentListeners[name] = fn; }
};
const window = {
  __usbEvent(event) {
    events.push(event);
    if (event === 'connected') {
      elements.get('usbDot').className = 'dot connected';
      elements.get('usbStatus').textContent = 'Connected';
      elements.get('flashBtn').disabled = false;
    } else if (event === 'disconnected') {
      elements.get('usbDot').className = 'dot';
      elements.get('usbStatus').textContent = 'Disconnected';
      elements.get('flashBtn').disabled = true;
    }
    return event;
  }
};
const Android = {
  usbDiagnostics() {
    diagnosticsCalls += 1;
    return JSON.stringify(snapshot);
  },
  deviceInfo() { return 'USB Single Serial (0x1a86:0x55d4)'; },
  requestUsbPermission() { permissionRequests += 1; return 'requested'; },
  copyText() { return 'ok'; }
};
const context = {
  window,
  document,
  Android,
  t: () => ({ usbConnected: info => 'Подключены: ' + info }),
  doReadOnlyPreflight() {},
  log() {},
  setTimeout(fn, ms) { timeouts.push({ fn, ms }); return timeouts.length; },
  setInterval(fn, ms) { intervals.push({ fn, ms }); return intervals.length; }
};
vm.runInNewContext(usbScript, context, { filename: 'generated-neurowatch-usb.js' });

assert.equal(intervals.length, 1, 'only one USB scan interval should be installed');
assert.equal(intervals[0].ms, 2500, 'USB scan should be throttled to 2.5 seconds');
timeouts[0].fn();
assert.match(elements.get('usbStatus').textContent, /Подключите часы/);
assert.equal(elements.get('usbPermissionBtn').disabled, true);

snapshot = {
  usbHost: true, count: 1,
  devices: [{
    vid: 0x1A86, pid: 0x55D4, interfaces: 2, permission: false,
    defaultDriver: 'CdcAcmSerialDriver', selectedDriver: 'CdcAcmSerialDriver'
  }]
};
intervals[0].fn();
assert.match(elements.get('usbStatus').textContent, /нужен доступ USB/);
assert.equal(elements.get('usbPermissionBtn').disabled, false);
assert.equal(elements.get('usbPermissionBtn').textContent, 'РАЗРЕШИТЬ ДОСТУП');
assert.equal(elements.get('flashBtn').disabled, true);

elements.get('usbPermissionBtn').fire('click');
assert.equal(permissionRequests, 1);
assert.match(elements.get('usbStatus').textContent, /Подтвердите доступ/);

snapshot.devices[0].permission = true;
intervals[0].fn();
assert.deepEqual(events, ['connected']);
assert.equal(window.__neuroUsbConnected, true);
assert.equal(elements.get('preflightBtn').disabled, false);
assert.equal(elements.get('flashBtn').disabled, true, 'flash must wait for read-only preflight');

window.__preflightPassed = true;
intervals[0].fn();
assert.equal(elements.get('flashBtn').disabled, false);

snapshot = { usbHost: true, count: 0, devices: [] };
intervals[0].fn();
assert.deepEqual(events, ['connected', 'disconnected']);
assert.equal(window.__neuroUsbConnected, false);
assert.match(elements.get('usbStatus').textContent, /Подключите часы/);
assert.equal(elements.get('flashBtn').disabled, true);
assert.equal(elements.get('preflightBtn').disabled, true);

const callsBeforeBackgroundTick = diagnosticsCalls;
document.hidden = true;
intervals[0].fn();
assert.equal(diagnosticsCalls, callsBeforeBackgroundTick, 'USB scan should pause while app is hidden');
console.log('USB UI transitions passed: missing → permission → ready → preflight → unplugged');
