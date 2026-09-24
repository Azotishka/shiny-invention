#!/usr/bin/env python3
from pathlib import Path

root = Path(__import__("sys").argv[1])
js = root / "app/src/main/java/io/github/drakosha/espflash/JsBridge.kt"
usb = root / "app/src/main/java/io/github/drakosha/espflash/UsbSerialManager.kt"
gradle = root / "app/build.gradle"
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
    "import java.security.MessageDigest\n"
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

    @JavascriptInterface
    fun assetMd5(name: String): String {
        return try {
            val md = MessageDigest.getInstance("MD5")
            context.assets.open(name).use { input ->
                val buf = ByteArray(64 * 1024)
                while (true) {
                    val n = input.read(buf)
                    if (n <= 0) break
                    md.update(buf, 0, n)
                }
            }
            md.digest().joinToString("") { "%02x".format(it) }
        } catch (e: Exception) {
            Log.e(TAG, "assetMd5 failed: $name", e)
            ""
        }
    }

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

bridge_clear_needle = '''    @JavascriptInterface
    fun readData(): String = usbManager.readBufferedBase64()

    @JavascriptInterface
    fun setSignals(rts: Int, dtr: Int) = usbManager.setSignals(rts, dtr)
'''
bridge_clear_replacement = '''    @JavascriptInterface
    fun readData(): String = usbManager.readBufferedBase64()

    @JavascriptInterface
    fun clearInput() = usbManager.clearBufferedInput()

    @JavascriptInterface
    fun setSignals(rts: Int, dtr: Int): String = usbManager.setSignals(rts, dtr)
'''
if bridge_clear_needle not in s:
    raise SystemExit("JsBridge clearInput patch point not found")
s = s.replace(bridge_clear_needle, bridge_clear_replacement)
js.write_text(s)

u = usb.read_text()

u = u.replace(
    "import android.hardware.usb.UsbManager\n",
    "import android.hardware.usb.UsbManager\n"
    "import android.hardware.usb.UsbConstants\n"
    "import android.hardware.usb.UsbDeviceConnection\n"
    "import java.io.IOException\n"
)

field_needle = '''    private var port: UsbSerialPort? = null
    private var readThread: Thread? = null
'''
field_replacement = '''    private var port: UsbSerialPort? = null
    private var usbConnection: UsbDeviceConnection? = null
    private var connectedDevice: UsbDevice? = null
    private var signalRts = false
    private var signalDtr = false
    private var atomicControlMode = 0 // 0=generic, 1=CDC ACM, 2=CH34x vendor
    private var cdcControlInterfaceId = 0
    private var readThread: Thread? = null
'''
if field_needle not in u:
    raise SystemExit("UsbSerialManager field patch point not found")
u = u.replace(field_needle, field_replacement)

open_needle = '''        val connection = usbManager.openDevice(driver.device)
            ?: return "error: cannot open device"

        port = driver.ports[0]
        try {
            port!!.open(connection)
            port!!.setParameters(BAUD_RATE, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE)
            // pyserial (а значит и десктопный esptool) поднимает DTR/RTS при открытии
            // порта, usb-serial-for-android оставляет обе линии в 0. Без этого
            // ESP32-S3 USB-Serial/JTAG не разгребает OUT-endpoint и любая запись
            // висит до таймаута (SerialTimeoutException, rc=-1) — sync не проходит
            // никогда, ни в download mode, ни в обычном.
            port!!.dtr = true
            port!!.rts = true
            Log.i(TAG, "initial signals dtr=${port!!.dtr} rts=${port!!.rts}")
        } catch (e: Exception) {
'''
open_replacement = '''        val connection = usbManager.openDevice(driver.device)
            ?: return "error: cannot open device"

        usbConnection = connection
        connectedDevice = device
        signalRts = false
        signalDtr = false
        val driverName = driver.javaClass.simpleName
        atomicControlMode = when {
            driverName.contains("CdcAcm", ignoreCase = true) -> 1
            driverName.contains("Ch34", ignoreCase = true) -> 2
            else -> 0
        }
        cdcControlInterfaceId = 0
        if (atomicControlMode == 1) {
            for (i in 0 until device.interfaceCount) {
                val iface = device.getInterface(i)
                if (iface.interfaceClass == UsbConstants.USB_CLASS_COMM && iface.interfaceSubclass == 2) {
                    cdcControlInterfaceId = iface.id
                    break
                }
            }
        }
        Log.i(TAG, "driver=$driverName atomicMode=$atomicControlMode cdcIf=$cdcControlInterfaceId")
        port = driver.ports[0]
        try {
            port!!.open(connection)
            port!!.setParameters(BAUD_RATE, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE)

            if (isCh9102(device)) {
                // The physical NeuroWatch uses WCH CH9102 (1A86:55D4).
                // Keep both lines deasserted after open. Reset will be issued
                // atomically by setSignals(), avoiding the transient line state
                // created by separate port.rts / port.dtr USB requests.
                setSignals(0, 0)
                Log.i(TAG, "CH9102 opened with atomic DTR/RTS, both deasserted")
            } else {
                // Preserve upstream behaviour for other bridges.
                port!!.dtr = true
                port!!.rts = true
                signalDtr = true
                signalRts = true
                Log.i(TAG, "initial signals dtr=${port!!.dtr} rts=${port!!.rts}")
            }
        } catch (e: Exception) {
'''
if open_needle not in u:
    raise SystemExit("UsbSerialManager open patch point not found")
u = u.replace(open_needle, open_replacement)

disconnect_needle = '''        try { port?.close() } catch (_: Exception) {}
        port = null
        synchronized(readLock) { readBuf.reset() }
'''
disconnect_replacement = '''        try { port?.close() } catch (_: Exception) {}
        port = null
        usbConnection = null
        connectedDevice = null
        signalRts = false
        signalDtr = false
        atomicControlMode = 0
        cdcControlInterfaceId = 0
        synchronized(readLock) { readBuf.reset() }
'''
if disconnect_needle not in u:
    raise SystemExit("UsbSerialManager disconnect patch point not found")
u = u.replace(disconnect_needle, disconnect_replacement)

signals_needle = '''    fun setSignals(rts: Int, dtr: Int) {
        try {
            if (rts != -1) port?.rts = rts != 0
            if (dtr != -1) port?.dtr = dtr != 0
        } catch (e: Exception) { Log.e(TAG, "setSignals error", e) }
    }
'''
signals_replacement = '''    private fun isCh9102(device: UsbDevice?): Boolean =
        device?.vendorId == 0x1A86 && device.productId == 0x55D4

    /**
     * Update DTR and RTS in ONE USB control transfer. The physical 1A86:55D4
     * device enumerates as CDC ACM on Android (USB class 2, two interfaces),
     * but some CH9102 variants can use the WCH vendor driver. Support both.
     *
     * CDC ACM: SET_CONTROL_LINE_STATE (0x22), value bit0=DTR bit1=RTS.
     * CH34x:   vendor request 0xA4, active-low SCL_DTR/SCL_RTS bits.
     */
    private fun setBridgeSignalsAtomic(rts: Boolean, dtr: Boolean) {
        val conn = usbConnection ?: throw IOException("USB connection is closed")
        val rc = when (atomicControlMode) {
            1 -> {
                val requestType = UsbConstants.USB_DIR_OUT or UsbConstants.USB_TYPE_CLASS or 0x01
                val value = (if (dtr) 0x01 else 0) or (if (rts) 0x02 else 0)
                conn.controlTransfer(
                    requestType, 0x22, value, cdcControlInterfaceId,
                    null, 0, 1500
                )
            }
            2 -> {
                val asserted = (if (dtr) 0x20 else 0) or (if (rts) 0x40 else 0)
                val value = asserted.inv() and 0xFFFF
                val requestType = UsbConstants.USB_TYPE_VENDOR or UsbConstants.USB_DIR_OUT
                conn.controlTransfer(requestType, 0xA4, value, 0, null, 0, 1500)
            }
            else -> throw IOException("No atomic control-line transport for this driver")
        }
        if (rc < 0) throw IOException("atomic DTR/RTS request failed: rc=$rc mode=$atomicControlMode")
    }

    fun setSignals(rts: Int, dtr: Int): String {
        return try {
            val nextRts = if (rts == -1) signalRts else rts != 0
            val nextDtr = if (dtr == -1) signalDtr else dtr != 0

            if (isCh9102(connectedDevice) && atomicControlMode != 0) {
                setBridgeSignalsAtomic(nextRts, nextDtr)
            } else {
                if (rts != -1) port?.rts = nextRts
                if (dtr != -1) port?.dtr = nextDtr
            }

            signalRts = nextRts
            signalDtr = nextDtr
            Log.d(TAG, "signals rts=$signalRts dtr=$signalDtr mode=$atomicControlMode")
            "ok"
        } catch (e: Exception) {
            Log.e(TAG, "setSignals error", e)
            "error: ${e.message}"
        }
    }
'''
if signals_needle not in u:
    raise SystemExit("UsbSerialManager signal patch point not found")
u = u.replace(signals_needle, signals_replacement)

usb_clear_needle = '''    fun readBufferedBase64(): String {
        synchronized(readLock) {
            if (readBuf.size() == 0) return ""
            val data = readBuf.toByteArray()
            readBuf.reset()
            return Base64.encodeToString(data, Base64.NO_WRAP)
        }
    }

    private fun readLoop() {
'''
usb_clear_replacement = '''    fun readBufferedBase64(): String {
        synchronized(readLock) {
            if (readBuf.size() == 0) return ""
            val data = readBuf.toByteArray()
            readBuf.reset()
            return Base64.encodeToString(data, Base64.NO_WRAP)
        }
    }

    fun clearBufferedInput() {
        synchronized(readLock) { readBuf.reset() }
    }

    private fun readLoop() {
'''
if usb_clear_needle not in u:
    raise SystemExit("UsbSerialManager clear-buffer patch point not found")
u = u.replace(usb_clear_needle, usb_clear_replacement)
usb.write_text(u)

g = gradle.read_text()
if "com.github.mik3y:usb-serial-for-android:3.7.3" not in g:
    raise SystemExit("usb-serial dependency patch point not found")
g = g.replace(
    "com.github.mik3y:usb-serial-for-android:3.7.3",
    "com.github.mik3y:usb-serial-for-android:3.11.0"
)
gradle.write_text(g)

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
    "                          '<b>3.</b> Автовход в загрузчик → проверка железа → резервная копия OTA-разметки → запись в неактивный слот → MD5-проверка<br>' +\n"
    "                          '<b>4.</b> Не отключайте кабель после финального подтверждения',"
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
  const CHUNK = 0x00001000; // 4 KiB: more reliable on CH9102 + Android USB.
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

      for (let attempt = 1; attempt <= 5; attempt++) {
        try {
          if (Android.clearInput) Android.clearInput();
          await new Promise(r => setTimeout(r, 80));
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
            ' (попытка ' + attempt + '/5): ' + e.message,
            'err'
          );
          // First retries stay on the already-working stub session.
          // Reopening USB immediately can lose bootloader mode on this CH9102 board.
          if (attempt < 4) {
            if (Android.clearInput) Android.clearInput();
            await new Promise(r => setTimeout(r, 220));
            continue;
          }

          // One last recovery attempt: fully restart the bootloader session.
          if (attempt === 4) {
            try { await currentSession.serialPort.close(); } catch(_) {}
            try { Android.disconnect(); } catch(_) {}
            await new Promise(r => setTimeout(r, 700));
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
async function connectRomWithSignalSequence(name, steps, attempts = 6) {
  const serialPort = new AndroidSerialPort();
  const res = Android.connect();
  if (res !== 'ok') throw new Error(res);
  log('USB-порт открыт; atomic DTR/RTS ROM reset: ' + name, 'info');

  if (Android.clearInput) Android.clearInput();
  let signalResult = Android.setSignals(0, 0);
  if (signalResult && signalResult !== 'ok') throw new Error(signalResult);
  await new Promise(r => setTimeout(r, 100));

  for (const [rts, dtr, delayMs] of steps) {
    signalResult = Android.setSignals(rts, dtr);
    if (signalResult && signalResult !== 'ok') throw new Error(signalResult);
    await new Promise(r => setTimeout(r, delayMs));
  }

  if (Android.clearInput) Android.clearInput();
  await new Promise(r => setTimeout(r, 120));

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
    // Espressif classic sequence: D0/R1 -> D1/R0 -> D0/R0.
    // On this CH9102 board the exact sequence worked previously but was
    // intermittent when DTR/RTS were sent as two USB requests. v1.2 sends
    // each pair atomically and retries with progressively longer settling.
    const profiles = [
      ['classic-fast',   [[1,0,100],[0,1,70],[0,0,260]]],
      ['classic-normal', [[1,0,150],[0,1,100],[0,0,450]]],
      ['classic-long',   [[1,0,250],[0,1,150],[0,0,800]]],
    ];

    let lastError = null;
    for (let cycle = 1; cycle <= 3; cycle++) {
      for (const [profile, steps] of profiles) {
        const name = profile + ' ' + cycle + '/3';
        try {
          setProgress('Входим в загрузчик: ' + name, 2);
          return await connectRomWithSignalSequence(name, steps, 7);
        } catch (e) {
          lastError = e;
          log(name + ': ' + e.message, 'err');
          try { Android.setSignals(0, 0); } catch(_) {}
          try { Android.disconnect(); } catch(_) {}
          await new Promise(r => setTimeout(r, 700 + cycle * 250));
        }
      }
    }

    throw new Error(
      'Автовход в ROM bootloader не удался после 9 попыток. ' +
      'CH9102 определён, Flash не изменялась. Последняя ошибка: ' +
      (lastError ? lastError.message : 'unknown')
    );
  }
  throw new Error('Неподдерживаемый USB-UART для автоматической установки. Flash НЕ изменялась.');
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
  const state = u32le(otadata, start + 24);
  const crc = u32le(otadata, start + 28);
  const tmp = new Uint8Array(4);
  putU32le(tmp, 0, seq);
  const expected = crc32SeedFFFFFFFF(tmp);
  // INVALID(3) and ABORTED(4) must never be treated as the active copy.
  // UNDEFINED(0xffffffff), NEW(0), PENDING_VERIFY(1), VALID(2) are selectable.
  const stateBootable = state !== 3 && state !== 4;
  return {
    seq, state, crc,
    valid: seq !== 0xFFFFFFFF && crc === expected && stateBootable
  };
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

  // Select the smallest sequence number newer than the active entry which maps
  // to targetIndex. This is the same modulo rule used by the ESP-IDF bootloader:
  // selected slot = (ota_seq - 1) % ota_app_count.
  let nextSeq;
  if (base < 0) {
    nextSeq = targetIndex + 1;
  } else {
    const activeIndex = (baseSeq - 1) % otaApps.length;
    let delta = (targetIndex - activeIndex + otaApps.length) % otaApps.length;
    if (delta === 0) delta = otaApps.length;
    nextSeq = (baseSeq + delta) >>> 0;
  }
  if (nextSeq === 0 || nextSeq === 0xFFFFFFFF) {
    throw new Error('Невозможно безопасно сформировать OTA sequence number.');
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

    // ESP32 classic security eFuses. Refuse raw OTA writes if flash encryption
    // or Secure Boot is enabled: this installer intentionally never modifies
    // keys/fuses or tries to bypass platform security.
    const efuse0 = (await session.loader.readReg(0x3FF5A000)) >>> 0;
    const efuse6 = (await session.loader.readReg(0x3FF5A018)) >>> 0;
    const flashCryptCnt = (efuse0 >>> 20) & 0x7F;
    let cryptBits = 0;
    for (let x = flashCryptCnt; x; x >>>= 1) cryptBits += x & 1;
    const flashEncrypted = (cryptBits & 1) === 1;
    const secureBoot = ((efuse6 >>> 4) & 0x3) !== 0;
    log('Security: flashEncryption=' + flashEncrypted + ', secureBoot=' + secureBoot, 'info');
    if (flashEncrypted || secureBoot) {
      throw new Error(
        'Обнаружена защищённая конфигурация ESP32 (Flash Encryption/Secure Boot). ' +
        'Безопасная установка остановлена до записи.'
      );
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
    const nvsPart = partsInfo.find(p => p.type === 0x01 && p.subtype === 0x02);
    if (!nvsPart || nvsPart.size < 0x4000) {
      throw new Error('Совместимый NVS-раздел не найден. NeuroWatch OS не будет записана.');
    }

    const otadata = await readFlashSlowRom(session.loader, otadataPart.offset, 0x2000, (done,total) => {
      setProgress('OTA metadata: ' + Math.round(done*100/total) + '%', 10 + Math.round(done/total*10));
    });

    const choice = pickSafeOtaTarget(partsInfo, otadata);
    const app = b64ToBytes(Android.readAssetBase64('app.bin'));
    if (!app.length) throw new Error('В APK отсутствует app.bin');
    if (app[0] !== 0xE9) {
      throw new Error('Встроенный app.bin не похож на ESP32 application image. Запись отменена.');
    }
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
        setProgress(targetText + ': ' + pct + '%', 25 + Math.round(pct * 0.55));
      }
    );

    // Verify the inactive slot BEFORE switching boot selection. If verification
    // fails, the factory/current app remains selected and still boots normally.
    setProgress('Проверяем записанную систему…', 82);
    const expectedMd5 = String(Android.assetMd5('app.bin') || '').toLowerCase();
    if (!/^[0-9a-f]{32}$/.test(expectedMd5)) {
      throw new Error('Не удалось вычислить MD5 встроенной прошивки. OTA не переключена.');
    }
    const flashMd5 = String(await session.loader.flashMd5sum(choice.target.offset, app.length)).toLowerCase();
    log('MD5 app.bin: ' + expectedMd5, 'info');
    log('MD5 Flash:   ' + flashMd5, 'info');
    if (flashMd5 !== expectedMd5) {
      throw new Error('Проверка записи не пройдена: MD5 не совпадает. Текущая система остаётся активной.');
    }
    log('Проверка записи пройдена.', 'ok');

    // Prepare only the alternate 4K otadata sector, preserving the other copy.
    const copyStart = choice.writeCopy * 0x1000;
    const sector = otadata.slice(copyStart, copyStart + 0x1000);
    putU32le(sector, 0, choice.nextSeq);
    // Mark the target selectable regardless of stale INVALID/ABORTED state in
    // the alternate metadata copy. UNDEFINED is bootable in ESP-IDF both with
    // and without rollback support.
    putU32le(sector, 24, 0xFFFFFFFF);
    const seqBytes = new Uint8Array(4);
    putU32le(seqBytes, 0, choice.nextSeq);
    putU32le(sector, 28, crc32SeedFFFFFFFF(seqBytes));

    setProgress('Переключаем загрузку на NeuroWatch OS…', 92);
    await writeExact4kSector(session.loader, otadataPart.offset + copyStart, sector);

    setProgress('Готово — часы перезагружаются', 100);
    log('NeuroWatch OS записана в ' + targetText + '.', 'ok');
    log('Заводское приложение осталось во Flash. Если новая система не запустится, её можно вернуть через USB.', 'info');
  } catch (e) {
    log('Ошибка: ' + e.message, 'err');
    log(
      'Установщик остановился безопасно. Если переключение OTA не было завершено, ' +
      'активной остаётся прежняя система. Повторный запуск приложения безопасен.',
      'info'
    );
    setProgress('Остановлено безопасно', 0);
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
  'Приложение автоматически войдёт в загрузчик, проверит железо и безопасность, сохранит OTA-разметку, запишет NeuroWatch OS в неактивный слот и проверит запись перед переключением'
)

# Final hardening: remove dead full-flash-backup flow from generated UI and
# disable the destructive erase action completely. Safe OTA uses only app.bin.
dead_start = h.find("async function makeFactoryBackup(session) {")
dead_end = h.find("\n\nasync function connectRomWithSignalSequence", dead_start)
if dead_start >= 0 and dead_end > dead_start:
    h = h[:dead_start] + h[dead_end + 2:]

h = h.replace(
    "document.getElementById('eraseBtn').addEventListener('click', doErase);",
    "document.getElementById('eraseBtn').style.display = 'none';"
)

html.write_text(h)
print("patched Android flasher for NeuroWatch safe-install flow")

# v1.0 rebuild trigger
