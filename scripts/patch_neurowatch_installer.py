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

html.write_text(h)
print("patched Android flasher for NeuroWatch safe-install flow")
