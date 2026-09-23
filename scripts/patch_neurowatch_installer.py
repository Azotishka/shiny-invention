#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(__file__).resolve().parents[1]
flasher = Path(os.environ.get("FLASHER_DIR", root / ".build/esp-flash-android"))

# Native bridge: stream backup to Downloads/NeuroWatch.
p = flasher / "app/src/main/java/io/github/drakosha/espflash/JsBridge.kt"
s = p.read_text(encoding="utf-8")
s = s.replace("import android.content.Context\n", "import android.content.ContentValues\nimport android.content.Context\n")
s = s.replace("import android.net.Uri\n", "import android.net.Uri\nimport android.os.Build\nimport android.os.Environment\nimport android.provider.MediaStore\n")
s = s.replace("import android.webkit.JavascriptInterface\n", "import android.webkit.JavascriptInterface\nimport java.io.OutputStream\n")
s = s.replace(
'''    companion object {
        private const val TAG = "JsBridge"
    }
''',
'''    companion object {
        private const val TAG = "JsBridge"
    }

    private var backupStream: OutputStream? = null
    private var backupUri: Uri? = null
'''
)
anchor = '''    @JavascriptInterface
    fun readPickedBase64(slot: Int): String {
'''
insert = '''    @JavascriptInterface
    @Synchronized
    fun beginBackup(fileName: String): String {
        closeBackup(false)
        return try {
            val safe = fileName.replace(Regex("[^A-Za-z0-9._-]"), "_")
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, safe)
                    put(MediaStore.Downloads.MIME_TYPE, "application/octet-stream")
                    put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/NeuroWatch")
                    put(MediaStore.Downloads.IS_PENDING, 1)
                }
                val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    ?: return "error: cannot create backup"
                backupUri = uri
                backupStream = context.contentResolver.openOutputStream(uri, "w")
                    ?: return "error: cannot open backup"
                "ok"
            } else {
                val dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                    ?: return "error: no external files dir"
                val file = java.io.File(dir, safe)
                backupUri = Uri.fromFile(file)
                backupStream = file.outputStream()
                "ok"
            }
        } catch (e: Exception) {
            Log.e(TAG, "beginBackup failed", e)
            closeBackup(false)
            "error: " + e.message
        }
    }

    @JavascriptInterface
    @Synchronized
    fun appendBackupBase64(b64: String): String {
        return try {
            val out = backupStream ?: return "error: backup not open"
            out.write(Base64.decode(b64, Base64.NO_WRAP))
            "ok"
        } catch (e: Exception) {
            Log.e(TAG, "appendBackup failed", e)
            "error: " + e.message
        }
    }

    @JavascriptInterface
    @Synchronized
    fun finishBackup(): String {
        val uri = backupUri ?: return "error: backup not open"
        return try {
            backupStream?.flush()
            backupStream?.close()
            backupStream = null
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply { put(MediaStore.Downloads.IS_PENDING, 0) }
                context.contentResolver.update(uri, values, null, null)
            }
            backupUri = null
            uri.toString()
        } catch (e: Exception) {
            Log.e(TAG, "finishBackup failed", e)
            closeBackup(false)
            "error: " + e.message
        }
    }

    @JavascriptInterface
    @Synchronized
    fun cancelBackup() {
        closeBackup(true)
    }

    private fun closeBackup(delete: Boolean) {
        try { backupStream?.close() } catch (_: Exception) {}
        backupStream = null
        val uri = backupUri
        backupUri = null
        if (delete && uri != null) {
            try { context.contentResolver.delete(uri, null, null) } catch (_: Exception) {}
        }
    }

'''
if anchor not in s:
    raise SystemExit("JsBridge anchor not found")
s = s.replace(anchor, insert + anchor)
p.write_text(s, encoding="utf-8")

# UI safety gates.
p = flasher / "app/src/main/assets/flash.html"
s = p.read_text(encoding="utf-8")
s = s.replace(
    '<button id="flashBtn" disabled></button>',
    '<button class="secondary" id="identifyBtn" disabled></button>\\n'
    '<button class="secondary" id="backupBtn" disabled></button>\\n'
    '<button id="flashBtn" disabled></button>'
)
s = s.replace('<button class="danger" id="eraseBtn"></button>', '<button class="danger" id="eraseBtn" style="display:none"></button>')
s = s.replace("    flash: 'Flash',\n", "    identify: 'Check watch',\n    backup: 'Back up factory flash',\n    flash: 'Install NeuroWatch OS',\n")
s = s.replace("    flash: 'Прошить',\n", "    identify: 'Проверить часы',\n    backup: 'Сделать резервную копию',\n    flash: 'Установить NeuroWatch OS',\n")
s = s.replace(
    "let nextSlot = 0;\n",
    "let nextSlot = 0;\nlet identifiedOk = false;\nlet backupDone = false;\nconst EXPECTED_FLASH_SIZE = '4MB';\nconst BACKUP_BYTES = 0x400000;\nconst BACKUP_CHUNK = 0x10000;\n"
)

safety = r'''// ─── NeuroWatch safe install gate ─────────────────────────────────────────────
function classicEsp32(chip) {
  const c = (chip || '').toUpperCase();
  return c.includes('ESP32') &&
         !c.includes('ESP32-S2') && !c.includes('ESP32-S3') &&
         !c.includes('ESP32-C2') && !c.includes('ESP32-C3') &&
         !c.includes('ESP32-C5') && !c.includes('ESP32-C6') &&
         !c.includes('ESP32-H2') && !c.includes('ESP32-P4');
}

async function verifySession(session) {
  const flashSize = await session.loader.detectFlashSize();
  log('Flash: ' + (flashSize || 'unknown'), flashSize ? 'ok' : 'err');
  if (!classicEsp32(session.chip))
    throw new Error('Ожидался классический ESP32, обнаружено: ' + session.chip);
  if (flashSize !== EXPECTED_FLASH_SIZE)
    throw new Error('Ожидалось ' + EXPECTED_FLASH_SIZE + ' Flash, обнаружено: ' + (flashSize || 'не определено'));
  return flashSize;
}

async function doIdentify() {
  const btn = document.getElementById('identifyBtn');
  btn.disabled = true;
  document.getElementById('progressWrap').style.display = 'block';
  openLog();
  let session = null;
  try {
    setProgress('Проверка часов…', 5);
    session = await openChip();
    log(t().chip(session.chip), 'ok');
    await verifySession(session);
    identifiedOk = true;
    backupDone = false;
    document.getElementById('backupBtn').disabled = false;
    document.getElementById('flashBtn').disabled = true;
    setProgress('Совместимость подтверждена', 100);
    log('Базовая совместимость подтверждена. Теперь сделай резервную копию.', 'ok');
  } catch (e) {
    identifiedOk = false;
    backupDone = false;
    log(t().error(e.message), 'err');
    setProgress('Проверка не пройдена', 0);
  } finally {
    try { await session?.serialPort.close(); } catch(_) {}
    btn.disabled = false;
  }
}

async function doBackup() {
  if (!identifiedOk) { log('Сначала нажми «Проверить часы».', 'err'); return; }
  const btn = document.getElementById('backupBtn');
  btn.disabled = true;
  document.getElementById('flashBtn').disabled = true;
  document.getElementById('progressWrap').style.display = 'block';
  openLog();
  let session = null;
  try {
    session = await openChip();
    log(t().chip(session.chip), 'ok');
    await verifySession(session);
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const name = 'watchy_factory_4mb_' + stamp + '.bin';
    const start = Android.beginBackup(name);
    if (start !== 'ok') throw new Error(start);

    let done = 0;
    for (let addr = 0; addr < BACKUP_BYTES; addr += BACKUP_CHUNK) {
      const size = Math.min(BACKUP_CHUNK, BACKUP_BYTES - addr);
      const chunk = await session.loader.readFlash(addr, size, (_packet, progress, total) => {
        const local = total > 0 ? progress / total : 0;
        const pct = Math.min(99, Math.floor((addr + local * size) * 100 / BACKUP_BYTES));
        setProgress('Резервная копия: ' + pct + '%', pct);
      });
      const res = Android.appendBackupBase64(bytesToB64(chunk));
      if (res !== 'ok') throw new Error(res);
      done += chunk.length;
      const pct = Math.min(99, Math.floor(done * 100 / BACKUP_BYTES));
      setProgress('Резервная копия: ' + pct + '%', pct);
    }
    const saved = Android.finishBackup();
    if (saved.startsWith('error:')) throw new Error(saved);
    backupDone = true;
    setProgress('Резервная копия готова', 100);
    log('Резервная копия сохранена: ' + saved, 'ok');
    log('Теперь разрешена установка NeuroWatch OS.', 'ok');
    document.getElementById('flashBtn').disabled = false;
  } catch (e) {
    try { Android.cancelBackup(); } catch(_) {}
    backupDone = false;
    log(t().error(e.message), 'err');
  } finally {
    try { await session?.serialPort.close(); } catch(_) {}
    btn.disabled = !identifiedOk;
  }
}

'''
anchor2 = "// ─── Прошивка ─────────────────────────────────────────────────────────────────\n"
if anchor2 not in s:
    raise SystemExit("flash anchor not found")
s = s.replace(anchor2, safety + anchor2)

s = s.replace(
"async function doFlash() {\n  const btn = document.getElementById('flashBtn');\n",
"async function doFlash() {\n  const btn = document.getElementById('flashBtn');\n  if (!identifiedOk || !backupDone) {\n    log('Установка заблокирована: сначала проверка часов и полная резервная копия.', 'err');\n    return;\n  }\n"
)
s = s.replace(
"    session = await openChip();\n    log(t().chip(session.chip), 'ok');\n\n    const fileArray = loadParts();",
"    session = await openChip();\n    log(t().chip(session.chip), 'ok');\n    await verifySession(session);\n\n    const fileArray = loadParts();"
)
s = s.replace(
"  document.getElementById('flashBtn').textContent = T.flash;\n",
"  document.getElementById('identifyBtn').textContent = T.identify;\n  document.getElementById('backupBtn').textContent = T.backup;\n  document.getElementById('flashBtn').textContent = T.flash;\n"
)
s = s.replace(
"    flash.disabled = false;\n    erase.disabled = false;",
"    document.getElementById('identifyBtn').disabled = false;\n    document.getElementById('backupBtn').disabled = !identifiedOk;\n    flash.disabled = !(identifiedOk && backupDone);\n    erase.disabled = true;"
)
s = s.replace(
"    flash.disabled = true;\n    erase.disabled = true;",
"    document.getElementById('identifyBtn').disabled = true;\n    document.getElementById('backupBtn').disabled = true;\n    flash.disabled = true;\n    erase.disabled = true;"
)
s = s.replace(
"document.getElementById('flashBtn').addEventListener('click', doFlash);",
"document.getElementById('identifyBtn').addEventListener('click', doIdentify);\n"
"document.getElementById('backupBtn').addEventListener('click', doBackup);\n"
"document.getElementById('flashBtn').addEventListener('click', doFlash);"
)
s = s.replace(
"""    instructionsEmbedded: '<b>1.</b> Подключите плату к телефону по USB OTG<br>' +
                          '<b>2.</b> Зажмите BOOT, нажмите RESET, отпустите BOOT<br>' +
                          '<b>3.</b> Нажмите «Прошить»',""",
"""    instructionsEmbedded: '<b>1.</b> Подключи часы по USB OTG<br>' +
                          '<b>2.</b> Нажми «Проверить часы»<br>' +
                          '<b>3.</b> Сделай резервную копию<br>' +
                          '<b>4.</b> Затем нажми «Установить NeuroWatch OS»',"""
)
s = s.replace(
"""    instructionsEmbedded: '<b>1.</b> Connect the board to the phone via USB OTG<br>' +
                          '<b>2.</b> Hold BOOT, tap RESET, release BOOT<br>' +
                          '<b>3.</b> Tap Flash',""",
"""    instructionsEmbedded: '<b>1.</b> Connect the watch via USB OTG<br>' +
                          '<b>2.</b> Tap Check watch<br>' +
                          '<b>3.</b> Back up factory flash<br>' +
                          '<b>4.</b> Then install NeuroWatch OS',"""
)
p.write_text(s, encoding="utf-8")
print("NeuroWatch installer patch applied")
