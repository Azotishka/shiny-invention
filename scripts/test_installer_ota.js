global.window = {};
function assertEq(actual, expected, msg) {
  if (actual !== expected) throw new Error(msg + ": got " + actual + ", expected " + expected);
}
function mkEntry(seq, state = 0xffffffff) {
  const b = new Uint8Array(0x1000); b.fill(0xff);
  putU32le(b, 0, seq >>> 0);
  putU32le(b, 24, state >>> 0);
  const q = new Uint8Array(4); putU32le(q, 0, seq >>> 0);
  putU32le(b, 28, crc32SeedFFFFFFFF(q));
  return b;
}
function concat(a, b) {
  const x = new Uint8Array(a.length + b.length);
  x.set(a, 0); x.set(b, a.length); return x;
}
const parts = [
  {type:0x00, subtype:0x00, offset:0x10000, size:0x100000, label:"factory"},
  {type:0x00, subtype:0x10, offset:0x110000, size:0x140000, label:"ota_0"},
  {type:0x00, subtype:0x11, offset:0x250000, size:0x140000, label:"ota_1"},
];
let blank = new Uint8Array(0x2000); blank.fill(0xff);
let x = pickSafeOtaTarget(parts, blank);
assertEq(x.targetIndex, 0, "factory -> ota0");
assertEq(x.nextSeq, 1, "factory seq");

let ota0 = concat(mkEntry(1), mkEntry(0xffffffff));
x = pickSafeOtaTarget(parts, ota0);
assertEq(x.currentIndex, 0, "active ota0");
assertEq(x.targetIndex, 1, "ota0 -> ota1");
assertEq(x.nextSeq, 2, "ota1 seq");

let ota1 = concat(mkEntry(1), mkEntry(2));
x = pickSafeOtaTarget(parts, ota1);
assertEq(x.currentIndex, 1, "active ota1");
assertEq(x.targetIndex, 0, "ota1 -> ota0");
assertEq(x.nextSeq, 3, "ota0 next seq");

let invalidHigh = concat(mkEntry(5, 3), mkEntry(2, 2));
x = pickSafeOtaTarget(parts, invalidHigh);
assertEq(x.currentIndex, 1, "invalid high sequence ignored");

// Independent ESP-IDF CRC vectors generated with binascii.crc32(<seq LE>, 0xffffffff).
const v1 = new Uint8Array([1,0,0,0]);
const v2 = new Uint8Array([2,0,0,0]);
assertEq(crc32SeedFFFFFFFF(v1) >>> 0, 0x4743989a, "CRC seq1");
assertEq(crc32SeedFFFFFFFF(v2) >>> 0, 0x55f63774, "CRC seq2");
console.log("OTA logic tests passed");
