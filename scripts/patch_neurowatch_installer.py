#!/usr/bin/env python3
from pathlib import Path

root = Path(__import__("sys").argv[1])
js = root / "app/src/main/java/io/github/drakosha/espflash/JsBridge.kt"
html = root / "app/src/main/assets/flash.html"

s = js.read_text()

s = s.replace(
    "import android.content.Context\n",
    "import android.content.Context\n"
    "import android.content.ContentValues\n"
    "import android.os.Build\n"
    "import android.os.Environment\n"
    "import android.provider.MediaStore\n"
    "import java.io.File\n"
)

needle = '''    @JavascriptInterface
    fun deviceInfo(): String {
        val device = usbManager.findDevice() ?: return ""
        return usbManager.describeDevice(device)
    }

    @JavascriptInterface
    fun write(b64: String) {
'''
replacement = '''    @JavascriptInterface
    fun deviceInfo(): String {
        val device = usbManager.findDevice() ?: return ""
        return usbManager.describeDevice(device)
    }

    @JavascriptInterface
    fun usbVendorId(): Int = usbManager.findDevice()?.vendorId ?: 0

    @JavascriptInterface
    fun usbProductId(): Int = usbManager.findDevice()?.productId ?: 0

    private var backupUri: Uri? = null
    private var backupStream: java.io.OutputStream? = null
    private var backupDisplayName: String = ""
    private var backupBytes: Long = 0L
    private var backupLegacyFile: File? = null

    /**
     * Start a pending backup file. Chunks are appended from JS as they are
     * successfully read, so a full 4 MB image never has to cross the bridge
     * in one giant Base64 string.
     */
    @JavascriptInterface
    fun beginBackup(name: String): String {
        abortBackup()
        val safeName = name.replace(Regex("[^A-Za-z0-9._-]"), "_")
        return try {
            backupDisplayName = safeName
            backupBytes = 0L
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, safeName)
                    put(MediaStore.Downloads.MIME_TYPE, "application/octet-stream")
                    put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/NeuroWatch")
                    put(MediaStore.Downloads.IS_PENDING, 1)
                }
                val uri = context.contentResolver.insert(
                    MediaStore.Downloads.EXTERNAL_CONTENT_URI, values
                ) ?: return "error: cannot create backup in Downloads"
                val stream = context.contentResolver.openOutputStream(uri, "w")
                    ?: run {
                        context.contentResolver.delete(uri, null, null)
                        return "error: cannot open backup output"
                    }
                backupUri = uri
                backupStream = stream
                "ok"
            } else {
                val dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                    ?: return "error: Downloads directory unavailable"
                if (!dir.exists()) dir.mkdirs()
                val file = File(dir, safeName)
                backupLegacyFile = file
                backupStream = file.outputStream()
                "ok"
            }
        } catch (e: Exception) {
            Log.e(TAG, "beginBackup failed", e)
            abortBackup()
            "error: ${e.message}"
        }
    }

    @JavascriptInterface
    fun appendBackupBase64(b64: String): String {
        val stream = backupStream ?: return "error: backup not started"
        return try {
            val bytes = Base64.decode(b64, Base64.NO_WRAP)
            stream.write(bytes)
            backupBytes += bytes.size.toLong()
            backupBytes.toString()
        } catch (e: Exception) {
            Log.e(TAG, "appendBackup failed", e)
            "error: ${e.message}"
        }
    }

    @JavascriptInterface
    fun finishBackup(expectedBytes: Long): String {
        val stream = backupStream ?: return "error: backup not started"
        return try {
            stream.flush()
            stream.close()
            backupStream = null

            if (backupBytes != expectedBytes) {
                val got = backupBytes
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    backupUri?.let { context.contentResolver.delete(it, null, null) }
                } else {
                    backupLegacyFile?.delete()
                }
                backupUri = null
                backupLegacyFile = null
                backupBytes = 0L
                return "error: backup size mismatch: $got != $expectedBytes"
            }

            val location = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val uri = backupUri ?: return "error: backup URI missing"
                val values = ContentValues().apply {
                    put(MediaStore.Downloads.IS_PENDING, 0)
                }
                context.contentResolver.update(uri, values, null, null)
                "Downloads/NeuroWatch/$backupDisplayName"
            } else {
                backupLegacyFile?.absolutePath ?: "backup saved"
            }

            backupUri = null
            backupLegacyFile = null
            backupBytes = 0L
            "ok: $location"
        } catch (e: Exception) {
            Log.e(TAG, "finishBackup failed", e)
            abortBackup()
            "error: ${e.message}"
        }
    }

    @JavascriptInterface
    fun abortBackup(): String {
        try { backupStream?.close() } catch (_: Exception) {}
        backupStream = null
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                backupUri?.let { context.contentResolver.delete(it, null, null) }
            } else {
                backupLegacyFile?.delete()
            }
        } catch (_: Exception) {}
        backupUri = null
        backupLegacyFile = null
        backupBytes = 0L
        return "ok"
    }

    @JavascriptInterface
    fun write(b64: String) {
'''
if needle not in s:
    raise SystemExit("JsBridge insertion point not found")
s = s.replace(needle, replacement)
js.write_text(s)

h = html.read_text()

old_info = "  getInfo() { return { usbVendorId: 0x303A, usbProductId: 0x1001 }; }"
new_info = "  getInfo() { return { usbVendorId: Android.usbVendorId(), usbProductId: Android.usbProductId() }; }"
if old_info not in h:
    raise SystemExit("getInfo patch point not found")
h = h.replace(old_info, new_info)

h = h.replace(
    '<button class="danger" id="eraseBtn"></button>',
    '<button class="danger" id="eraseBtn" style="display:none"></button>'
)

h = h.replace(
    "flash: 'Прошить',",
    "flash: 'УСТАНОВИТЬ NEUROWATCH OS',"
)
h = h.replace(
    "flash: 'Flash',",
    "flash: 'INSTALL NEUROWATCH OS',"
)

h = h.replace(
    "instructionsEmbedded: '<b>1.</b> Подключите плату к телефону по USB OTG<br>' +\n"
    "                          '<b>2.</b> Зажмите BOOT, нажмите RESET, отпустите BOOT<br>' +\n"
    "                          '<b>3.</b> Нажмите «Прошить»',",
    "instructionsEmbedded: '<b>1.</b> Подключите часы по USB OTG<br>' +\n"
    "                          '<b>2.</b> Нажмите «УСТАНОВИТЬ NEUROWATCH OS»<br>' +\n"
    "                          '<b>3.</b> Приложение само проверит чип, сохранит заводскую Flash и только после подтверждения начнёт запись',"
)


# Strengthen CH9102 auto-reset handling: the user's physical watch enumerates
# as 1A86:55D4, but generic esptool reset did not put the ESP into ROM loader.
old_open = r'''async function openChip() {
  try {
    return await connectLoader('no_reset', 2);
  } catch (e) {
    log(t().resetFailed(e.message), 'err');
    log(t().retryWithReset, 'info');
    try { Android.disconnect(); } catch(_) {}
    await new Promise(r => setTimeout(r, 800));
    return await connectLoader('default_reset', 3);
  }
}'''
new_open = r'''async function connectLoaderWithSignalSequence(name, steps, attempts = 2) {
  const serialPort = new AndroidSerialPort();
  const res = Android.connect();
  if (res !== 'ok') throw new Error(res);
  log('USB-порт открыт; пробую ' + name, 'info');

  for (const [rts, dtr, delayMs] of steps) {
    Android.setSignals(rts, dtr);
    await new Promise(r => setTimeout(r, delayMs));
  }

  const transport = new esptool.Transport(serialPort, false);
  const loader = new esptool.ESPLoader({ transport, baudrate: 115200, terminal });
  await loader.connect('no_reset', attempts);
  const chip = await loader.chip.getChipDescription(loader);
  loader.info('Chip is ' + chip);
  if (loader.chip.postConnect) await loader.chip.postConnect(loader);
  await loader.runStub();
  return { loader, serialPort, chip };
}

async function openChip() {
  const vid = Android.usbVendorId();
  const pid = Android.usbProductId();

  // Physical device observed on Xiaomi Pad 7 Pro: WCH/QinHeng CH9102 1A86:55D4.
  // Try several harmless reset/boot control-line sequences before giving up.
  // These only toggle RTS/DTR; they do not write flash.
  if (vid === 0x1A86 && pid === 0x55D4) {
    const sequences = [
      ['CH9102 reset sequence A', [[1,0,120],[0,1,120],[0,0,160]]],
      ['CH9102 reset sequence B', [[0,1,120],[1,0,120],[0,0,160]]],
      ['CH9102 reset sequence C', [[1,1,120],[0,1,120],[0,0,160]]],
    ];
    for (const [name, steps] of sequences) {
      try {
        return await connectLoaderWithSignalSequence(name, steps, 2);
      } catch (e) {
        log(name + ': ' + e.message, 'err');
        try { Android.disconnect(); } catch(_) {}
        await new Promise(r => setTimeout(r, 500));
      }
    }
    throw new Error(
      'CH9102 виден, но ESP не вошёл в ROM bootloader. ' +
      'DTR/RTS, вероятно, не подключены к EN/GPIO0 на этой ревизии. ' +
      'Flash НЕ изменялась.'
    );
  }

  try {
    return await connectLoader('no_reset', 2);
  } catch (e) {
    log(t().resetFailed(e.message), 'err');
    log(t().retryWithReset, 'info');
    try { Android.disconnect(); } catch(_) {}
    await new Promise(r => setTimeout(r, 800));
    return await connectLoader('default_reset', 3);
  }
}'''

if old_open not in h:
    raise SystemExit("openChip patch point not found")
h = h.replace(old_open, new_open)

marker = "// ─── Прошивка ─────────────────────────────────────────────────────────────────"
insert = r'''
function assertSupportedNeuroWatchChip(chip) {
  const s = String(chip || '');
  const unsupported = /ESP32-(S2|S3|C2|C3|C5|C6|C61|H2|P4)/i.test(s);
  if (!/ESP32/i.test(s) || unsupported) {
    throw new Error('Установка остановлена: NeuroWatch OS v0.6 собрана для классического ESP32/Watchy V2, а определён чип: ' + s);
  }
}

async function makeFactoryBackup(session) {
  log('Проверяем размер Flash…', 'info');
  let flashSize = null;
  try {
    flashSize = await session.loader.detectFlashSize();
  } catch (e) {
    throw new Error('Не удалось определить размер Flash: ' + e.message);
  }
  log('Flash: ' + flashSize, 'info');
  if (flashSize !== '4MB') {
    throw new Error('Установка остановлена: ожидалось 4MB Flash, определено ' + flashSize + '. Ничего не записано.');
  }

  const TOTAL = 0x00400000;
  const CHUNK = 0x00004000; // 16 KiB: avoids the known large-read instability in esptool-js.
  const name = 'watchy_factory_4mb_' + Date.now() + '.bin';
  const begin = Android.beginBackup(name);
  if (begin !== 'ok') {
    throw new Error('Не удалось создать файл резервной копии: ' + begin);
  }

  log('Создаём резервную копию заводской Flash 4 MB небольшими блоками…', 'info');
  let currentSession = session;

  try {
    for (let offset = 0; offset < TOTAL; offset += CHUNK) {
      const length = Math.min(CHUNK, TOTAL - offset);
      let data = null;
      let lastError = null;

      for (let attempt = 1; attempt <= 4; attempt++) {
        try {
          data = await currentSession.loader.readFlash(offset, length);
          if (!data || data.length !== length) {
            throw new Error('получено ' + (data ? data.length : 0) + ' байт вместо ' + length);
          }
          lastError = null;
          break;
        } catch (e) {
          lastError = e;
          log(
            'Сбой чтения @0x' + offset.toString(16) +
            ' (попытка ' + attempt + '/4): ' + e.message,
            'err'
          );
          try { await currentSession.serialPort.close(); } catch(_) {}
          try { Android.disconnect(); } catch(_) {}
          await new Promise(r => setTimeout(r, 600));

          if (attempt < 4) {
            currentSession = await openChip();
            assertSupportedNeuroWatchChip(currentSession.chip);
          }
        }
      }

      if (lastError || !data) {
        Android.abortBackup();
        throw new Error(
          'Не удалось надёжно прочитать заводскую Flash @0x' +
          offset.toString(16) + ': ' + (lastError ? lastError.message : 'unknown error') +
          '. Ничего не записано.'
        );
      }

      const append = Android.appendBackupBase64(bytesToB64(data));
      if (String(append).startsWith('error:')) {
        Android.abortBackup();
        throw new Error('Ошибка сохранения резервной копии: ' + append + '. Ничего не записано.');
      }

      const done = offset + length;
      const pct = Math.round(done * 100 / TOTAL);
      setProgress('Резервная копия: ' + pct + '%', 2 + Math.round(pct * 0.43));
    }

    const finish = Android.finishBackup(TOTAL);
    if (!String(finish).startsWith('ok:')) {
      Android.abortBackup();
      throw new Error('Не удалось завершить резервную копию: ' + finish + '. Ничего не записано.');
    }

    log('Заводская Flash сохранена: ' + finish, 'ok');
    return { location: finish, session: currentSession };
  } catch (e) {
    Android.abortBackup();
    throw e;
  }
}


'''
if marker not in h:
    raise SystemExit("flash marker not found")
h = h.replace(marker, insert + marker)

needle2 = """    session = await openChip();
    log(t().chip(session.chip), 'ok');

    const fileArray = loadParts();
"""
replacement2 = """    session = await openChip();
    log(t().chip(session.chip), 'ok');
    assertSupportedNeuroWatchChip(session.chip);

    const backupResult = await makeFactoryBackup(session);
    session = backupResult.session;
    const backupLocation = backupResult.location;
    const proceed = confirm(
      'Резервная копия заводской системы сохранена: ' + backupLocation +
      '\\n\\nПродолжить установку NeuroWatch OS? После подтверждения будут перезаписаны загрузчик, таблица разделов и приложение.'
    );
    if (!proceed) {
      log('Установка отменена пользователем. Flash не изменялась.', 'info');
      setProgress('Отменено — заводская система сохранена', 100);
      return;
    }

    const fileArray = loadParts();
"""
if needle2 not in h:
    raise SystemExit("doFlash patch point not found")
h = h.replace(needle2, replacement2)

# Embedded mode must never expose destructive full-chip erase.
h = h.replace("    erase.disabled = false;", "    erase.disabled = true;")


# v1.0: replace destructive full-backup flow with safe OTA-slot install.
# We read only the factory partition table + otadata via ESP32 ROM (no stub),
# write NeuroWatch OS into an inactive OTA app partition, then switch otadata.
# Existing bootloader, partition table, and currently running app are preserved.
safe_ota_helpers = r'''
async function connectRomWithSignalSequence(name, steps, attempts = 2) {
  const serialPort = new AndroidSerialPort();
  const res = Android.connect();
  if (res !== 'ok') throw new Error(res);
  log('USB-порт открыт; ROM probe: ' + name, 'info');

  for (const [rts, dtr, delayMs] of steps) {
    Android.setSignals(rts, dtr);
    await new Promise(r => setTimeout(r, delayMs));
  }

  const transport = new esptool.Transport(serialPort, false);
  const loader = new esptool.ESPLoader({ transport, baudrate: 115200, terminal });
  await loader.connect('no_reset', attempts);
  const chip = await loader.chip.getChipDescription(loader);
  loader.info('Chip is ' + chip);
  if (loader.chip.postConnect) await loader.chip.postConnect(loader);

  // Attach the normal SPI flash pins for ROM-side flash reads.
  try { await loader.flashSpiAttach(0); } catch (e) {
    log('SPI attach warning: ' + e.message, 'info');
  }
  return { loader, serialPort, chip };
}

async function openChipRom() {
  const vid = Android.usbVendorId();
  const pid = Android.usbProductId();

  if (vid === 0x1A86 && pid === 0x55D4) {
    const sequences = [
      ['CH9102 reset sequence A', [[1,0,120],[0,1,120],[0,0,160]]],
      ['CH9102 reset sequence B', [[0,1,120],[1,0,120],[0,0,160]]],
      ['CH9102 reset sequence C', [[1,1,120],[0,1,120],[0,0,160]]],
    ];
    for (const [name, steps] of sequences) {
      try {
        return await connectRomWithSignalSequence(name, steps, 2);
      } catch (e) {
        log(name + ': ' + e.message, 'err');
        try { Android.disconnect(); } catch(_) {}
        await new Promise(r => setTimeout(r, 500));
      }
    }
  }
  throw new Error('Не удалось войти в ROM bootloader. Flash НЕ изменялась.');
}

function u16le(a, o) {
  return (a[o] | (a[o+1] << 8)) >>> 0;
}
function u32le(a, o) {
  return (a[o] | (a[o+1] << 8) | (a[o+2] << 16) | (a[o+3] << 24)) >>> 0;
}
function putU32le(a, o, v) {
  a[o] = v & 0xff;
  a[o+1] = (v >>> 8) & 0xff;
  a[o+2] = (v >>> 16) & 0xff;
  a[o+3] = (v >>> 24) & 0xff;
}

async function readFlashSlowRom(loader, address, size, onProgress = null) {
  const out = new Uint8Array(size);
  const BLOCK = 64; // ESP32 ROM READ_FLASH_SLOW limit
  for (let off = 0; off < size; off += BLOCK) {
    const n = Math.min(BLOCK, size - off);
    let pkt = loader._appendArray(
      loader._intToByteArray((address + off) >>> 0),
      loader._intToByteArray(n)
    );
    const r = await loader.checkCommand(
      'ROM read flash block',
      0x0E,
      pkt,
      0,
      64,
      3000
    );
    if (!r || r.length < n) {
      throw new Error('ROM flash read short block @0x' + (address + off).toString(16));
    }
    out.set(r.slice(0, n), off);
    if (onProgress && ((off + n) % 1024 === 0 || off + n === size)) {
      onProgress(off + n, size);
    }
  }
  return out;
}

function parsePartitionTable(data) {
  const parts = [];
  const limit = Math.min(data.length, 0xC00);
  for (let off = 0; off + 32 <= limit; off += 32) {
    const magic = u16le(data, off);
    if (magic === 0xFFFF || magic === 0xEBEB) break;
    if (magic !== 0x50AA) {
      throw new Error('Некорректная таблица разделов @0x' + off.toString(16));
    }
    const type = data[off + 2];
    const subtype = data[off + 3];
    const pos = u32le(data, off + 4);
    const size = u32le(data, off + 8);
    let label = '';
    for (let i = 0; i < 16; i++) {
      const b = data[off + 12 + i];
      if (!b) break;
      label += String.fromCharCode(b);
    }
    const flags = u32le(data, off + 28);
    parts.push({ type, subtype, offset: pos, size, label, flags });
  }
  return parts;
}

function crc32SeedFFFFFFFF(bytes) {
  if (!window.__crc32Table) {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) {
        c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      }
      table[n] = c >>> 0;
    }
    window.__crc32Table = table;
  }
  let c = 0; // seed 0xFFFFFFFF converted to zlib's internal state
  for (const b of bytes) {
    c = window.__crc32Table[(c ^ b) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xFFFFFFFF) >>> 0;
}

function otaEntryInfo(otadata, start) {
  const seq = u32le(otadata, start);
  const crc = u32le(otadata, start + 28);
  const tmp = new Uint8Array(4);
  putU32le(tmp, 0, seq);
  const expected = crc32SeedFFFFFFFF(tmp);
  return { seq, crc, valid: seq !== 0xFFFFFFFF && crc === expected };
}

async function saveSmallBackup(bytes, name) {
  const begin = Android.beginBackup(name);
  if (begin !== 'ok') throw new Error('Не удалось создать backup: ' + begin);
  const append = Android.appendBackupBase64(bytesToB64(bytes));
  if (String(append).startsWith('error:')) {
    Android.abortBackup();
    throw new Error(append);
  }
  const finish = Android.finishBackup(bytes.length);
  if (!String(finish).startsWith('ok:')) {
    Android.abortBackup();
    throw new Error(finish);
  }
  return finish;
}

async function writeExact4kSector(loader, address, sector) {
  if (sector.length !== 0x1000) throw new Error('OTA sector must be 4096 bytes');

  let pkt = loader._appendArray(loader._intToByteArray(0x1000), loader._intToByteArray(1));
  pkt = loader._appendArray(pkt, loader._intToByteArray(0x1000));
  pkt = loader._appendArray(pkt, loader._intToByteArray(address >>> 0));

  await loader.checkCommand('enter 4K Flash mode', 0x02, pkt, 0, 0, 8000);
  await loader.flashBlock(sector, 0, 8000);
  await loader.flashFinish(true, 8000);
}

function pickSafeOtaTarget(parts, otadata) {
  const otaApps = parts
    .filter(p => p.type === 0x00 && p.subtype >= 0x10 && p.subtype <= 0x1F)
    .sort((a,b) => a.subtype - b.subtype);
  const factory = parts.find(p => p.type === 0x00 && p.subtype === 0x00) || null;
  if (!otaApps.length) throw new Error('В заводской разметке нет OTA app-разделов. Безопасная установка отменена.');

  const e0 = otaEntryInfo(otadata, 0x0000);
  const e1 = otaEntryInfo(otadata, 0x1000);
  let base = -1;
  if (e0.valid && e1.valid) base = e0.seq >= e1.seq ? 0 : 1;
  else if (e0.valid) base = 0;
  else if (e1.valid) base = 1;

  let currentIndex = -1; // -1 = factory/initial state
  let baseSeq = 0;
  if (base >= 0) {
    baseSeq = (base === 0 ? e0.seq : e1.seq) >>> 0;
    currentIndex = (baseSeq - 1) % otaApps.length;
  } else if (!factory) {
    currentIndex = 0; // IDF boots first OTA slot if there is no factory app.
  }

  let targetIndex;
  if (currentIndex < 0) {
    targetIndex = 0;
  } else {
    if (otaApps.length < 2) {
      throw new Error('Есть только один OTA-слот и он уже активен. Безопасная установка отменена.');
    }
    targetIndex = (currentIndex + 1) % otaApps.length;
  }

  const target = otaApps[targetIndex];
  const targetSeqBase = (target.subtype & 0x0F) + 1;
  let nextSeq = targetSeqBase;
  if (base >= 0) {
    while (baseSeq > (targetSeqBase % otaApps.length) + Math.floor((nextSeq - targetSeqBase) / otaApps.length) * otaApps.length) {
      nextSeq += otaApps.length;
    }
    while (((nextSeq - 1) % otaApps.length) !== targetIndex || nextSeq <= baseSeq) {
      nextSeq += otaApps.length;
    }
  }

  const writeCopy = base === 0 ? 1 : 0;
  return { otaApps, factory, currentIndex, targetIndex, target, nextSeq: nextSeq >>> 0, writeCopy };
}
'''

if marker not in h:
    raise SystemExit("safe OTA marker missing")
h = h.replace(marker, safe_ota_helpers + "\n" + marker, 1)

do_start = h.find("async function doFlash() {")
do_end = h.find("\nasync function doErase()", do_start)
if do_start < 0 or do_end < 0:
    raise SystemExit("doFlash block not found")

safe_do_flash = r'''async function doFlash() {
  const btn = document.getElementById('flashBtn');
  btn.disabled = true;
  document.getElementById('progressWrap').style.display = 'block';
  openLog();

  let session = null;
  try {
    setProgress('Читаем заводскую разметку…', 3);
    session = await openChipRom();
    log('Чип: ' + session.chip, 'ok');
    assertSupportedNeuroWatchChip(session.chip);

    let flashSize = null;
    try { flashSize = await session.loader.detectFlashSize(); } catch (_) {}
    if (flashSize && flashSize !== '4MB') {
      throw new Error('Ожидалось 4MB Flash, найдено: ' + flashSize + '. Ничего не записано.');
    }

    const table = await readFlashSlowRom(session.loader, 0x8000, 0x1000, (done,total) => {
      setProgress('Таблица разделов: ' + Math.round(done*100/total) + '%', 3 + Math.round(done/total*7));
    });
    const partsInfo = parsePartitionTable(table);
    log('Разделов найдено: ' + partsInfo.length, 'info');
    for (const p of partsInfo) {
      log('  ' + p.label + ' type=' + p.type + ' sub=0x' + p.subtype.toString(16) +
          ' @0x' + p.offset.toString(16) + ' size=0x' + p.size.toString(16));
    }

    const otadataPart = partsInfo.find(p => p.type === 0x01 && p.subtype === 0x00);
    if (!otadataPart || otadataPart.size < 0x2000) {
      throw new Error('OTA data partition не найден. Безопасная установка отменена.');
    }

    const otadata = await readFlashSlowRom(session.loader, otadataPart.offset, 0x2000, (done,total) => {
      setProgress('OTA metadata: ' + Math.round(done*100/total) + '%', 10 + Math.round(done/total*10));
    });

    const choice = pickSafeOtaTarget(partsInfo, otadata);
    const app = b64ToBytes(Android.readAssetBase64('app.bin'));
    if (!app.length) throw new Error('В APK отсутствует app.bin');
    if (app.length > choice.target.size) {
      throw new Error(
        'NeuroWatch OS (' + app.length + ' B) не помещается в ' +
        choice.target.label + ' (' + choice.target.size + ' B). Ничего не записано.'
      );
    }

    const stamp = Date.now();
    const tableSave = await saveSmallBackup(table, 'watchy_partition_table_' + stamp + '.bin');
    const otaSave = await saveSmallBackup(otadata, 'watchy_otadata_' + stamp + '.bin');
    log('Сохранено: ' + tableSave, 'ok');
    log('Сохранено: ' + otaSave, 'ok');

    const sourceText = choice.currentIndex < 0
      ? 'factory/initial'
      : choice.otaApps[choice.currentIndex].label;
    const targetText = choice.target.label || ('ota_' + choice.targetIndex);

    const proceed = confirm(
      'Безопасная OTA-установка готова.\n\n' +
      'Текущая система: ' + sourceText + '\n' +
      'NeuroWatch OS будет записана в НЕАКТИВНЫЙ раздел: ' + targetText +
      ' @0x' + choice.target.offset.toString(16) + '\n\n' +
      'Bootloader, таблица разделов и текущая заводская прошивка НЕ будут перезаписаны.\n\n' +
      'Продолжить?'
    );
    if (!proceed) {
      log('Установка отменена. Flash не изменялась.', 'info');
      setProgress('Отменено', 100);
      return;
    }

    // Switch from ROM to RAM stub only after all read-only validation succeeded.
    log('Запускаем временный flasher stub…', 'info');
    await session.loader.runStub();

    setProgress('Записываем NeuroWatch OS…', 25);
    await writeFlashRaw(
      session.loader,
      [{ data: app, address: choice.target.offset, label: targetText }],
      (idx, written, total) => {
        const pct = total ? Math.round(written * 100 / total) : 100;
        setProgress(targetText + ': ' + pct + '%', 25 + Math.round(pct * 0.60));
      }
    );

    // Prepare only the alternate 4K otadata sector, preserving the other copy.
    const copyStart = choice.writeCopy * 0x1000;
    const sector = otadata.slice(copyStart, copyStart + 0x1000);
    putU32le(sector, 0, choice.nextSeq);
    // Preserve seq_label/state bytes; only seq+CRC are required for boot selection.
    const seqBytes = new Uint8Array(4);
    putU32le(seqBytes, 0, choice.nextSeq);
    putU32le(sector, 28, crc32SeedFFFFFFFF(seqBytes));

    setProgress('Переключаем загрузку на NeuroWatch OS…', 90);
    await writeExact4kSector(session.loader, otadataPart.offset + copyStart, sector);

    setProgress('Готово — часы перезагружаются', 100);
    log('NeuroWatch OS записана в ' + targetText + '.', 'ok');
    log('Заводское приложение осталось во Flash. Если новая система не запустится, её можно вернуть через USB.', 'info');
  } catch (e) {
    log('Ошибка: ' + e.message, 'err');
    log('Если сообщение было до подтверждения записи — Flash не изменялась.', 'info');
    console.error(e);
  } finally {
    try { await session?.serialPort.close(); } catch(_) {}
    btn.disabled = false;
  }
}
'''

h = h[:do_start] + safe_do_flash + h[do_end:]

h = h.replace(
  'Приложение само проверит чип, сохранит заводскую Flash и только после подтверждения начнёт запись',
  'Приложение прочитает заводскую OTA-разметку и установит NeuroWatch OS в неактивный слот, не перезаписывая текущую систему'
)

html.write_text(h)
print("patched Android flasher for NeuroWatch safe-install flow")
