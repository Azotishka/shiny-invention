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

    /**
     * Save a factory flash backup to Downloads/NeuroWatch on Android 10+.
     * This is deliberately separate from flashing so a readable backup exists
     * before any write is allowed.
     */
    @JavascriptInterface
    fun saveBackupBase64(b64: String, name: String): String {
        val safeName = name.replace(Regex("[^A-Za-z0-9._-]"), "_")
        return try {
            val bytes = Base64.decode(b64, Base64.NO_WRAP)
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
                context.contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
                    ?: return "error: cannot open backup output"
                values.clear()
                values.put(MediaStore.Downloads.IS_PENDING, 0)
                context.contentResolver.update(uri, values, null, null)
                "ok: Downloads/NeuroWatch/$safeName"
            } else {
                val dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                    ?: return "error: Downloads directory unavailable"
                if (!dir.exists()) dir.mkdirs()
                val file = File(dir, safeName)
                file.writeBytes(bytes)
                "ok: ${file.absolutePath}"
            }
        } catch (e: Exception) {
            Log.e(TAG, "saveBackup failed", e)
            "error: ${e.message}"
        }
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

  log('Создаём резервную копию заводской Flash 4 MB… Это может занять несколько минут.', 'info');
  setProgress('Резервная копия…', 2);
  const backup = await session.loader.readFlash(
    0x00000000,
    0x00400000,
    (packet, progress, total) => {
      const pct = total ? Math.round(progress * 100 / total) : 0;
      setProgress('Резервная копия: ' + pct + '%', Math.max(2, Math.min(9, Math.round(pct * 0.09))));
    }
  );
  if (!backup || backup.length !== 0x00400000) {
    throw new Error('Резервная копия неполная: получено ' + (backup ? backup.length : 0) + ' байт вместо 4194304. Ничего не записано.');
  }

  const saveResult = Android.saveBackupBase64(
    bytesToB64(backup),
    'watchy_factory_4mb_' + Date.now() + '.bin'
  );
  if (!String(saveResult).startsWith('ok:')) {
    throw new Error('Не удалось сохранить резервную копию: ' + saveResult + '. Ничего не записано.');
  }
  log('Заводская Flash сохранена: ' + saveResult, 'ok');
  return saveResult;
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

    const backupLocation = await makeFactoryBackup(session);
    const proceed = confirm(
      'Резервная копия заводской системы сохранена: ' + backupLocation +
      '\n\nПродолжить установку NeuroWatch OS? После подтверждения будут перезаписаны загрузчик, таблица разделов и приложение.'
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
