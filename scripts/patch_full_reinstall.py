#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])
html = root / "app/src/main/assets/flash.html"
h = html.read_text()

start = h.find("async function doFlash() {")
end = h.find("\nasync function doErase()", start)
if start < 0 or end < 0:
    raise SystemExit("doFlash block not found")

full = r'''async function doFlash() {
  const btn = document.getElementById('flashBtn');
  btn.disabled = true;
  document.getElementById('progressWrap').style.display = 'block';
  openLog();

  let session = null;
  try {
    setProgress('Входим в ROM bootloader…', 3);
    session = await openChipRom();
    assertSupportedNeuroWatchChip(session.chip);
    log('Чип: ' + session.chip, 'ok');

    let flashSize = null;
    try { flashSize = await session.loader.detectFlashSize(); } catch (_) {}
    if (flashSize && flashSize !== '4MB') {
      throw new Error('Ожидалось 4MB Flash, найдено: ' + flashSize);
    }

    const bootloader = b64ToBytes(Android.readAssetBase64('bootloader.bin'));
    const partitions = b64ToBytes(Android.readAssetBase64('partitions.bin'));
    const bootApp0 = b64ToBytes(Android.readAssetBase64('boot_app0.bin'));
    const app = b64ToBytes(Android.readAssetBase64('app.bin'));

    if (!bootloader.length || !partitions.length || !bootApp0.length || !app.length) {
      throw new Error('В APK отсутствуют файлы полной прошивки.');
    }
    if (app[0] !== 0xE9) throw new Error('app.bin повреждён.');

    const proceed = confirm(
      'ПОЛНАЯ ПЕРЕУСТАНОВКА NEUROWATCH OS\n\n' +
      'Это ПОЛНОСТЬЮ СОТРЁТ заводскую систему, настройки и данные часов.\n' +
      'После стирания восстановление возможно только повторной прошивкой по USB.\n\n' +
      'Продолжить?'
    );
    if (!proceed) {
      setProgress('Отменено', 100);
      log('Полная переустановка отменена.', 'info');
      return;
    }

    await session.loader.runStub();

    setProgress('Стираем старую систему…', 10);
    log('FULL ERASE: начинаем полное стирание 4MB Flash.', 'err');
    await session.loader.eraseFlash();
    log('Flash полностью очищена.', 'ok');

    const parts = [
      { data: bootloader, address: 0x1000, label: 'bootloader', file: 'bootloader.bin' },
      { data: partitions, address: 0x8000, label: 'partitions', file: 'partitions.bin' },
      { data: bootApp0, address: 0xE000, label: 'boot_app0', file: 'boot_app0.bin' },
      { data: app, address: 0x10000, label: 'NeuroWatch OS', file: 'app.bin' },
    ];

    setProgress('Записываем NeuroWatch OS…', 25);
    await writeFlashRaw(session.loader, parts, (idx, written, total) => {
      const pct = total ? Math.round(written * 100 / total) : 100;
      setProgress(parts[idx].label + ': ' + pct + '%', 25 + Math.round((idx + pct/100) / parts.length * 60));
    });

    setProgress('Проверяем запись…', 88);
    for (const p of parts) {
      const expected = String(Android.assetMd5(p.file) || '').toLowerCase();
      const got = String(await session.loader.flashMd5sum(p.address, p.data.length)).toLowerCase();
      log('MD5 ' + p.label + ': ' + got, 'info');
      if (!/^[0-9a-f]{32}$/.test(expected) || got !== expected) {
        throw new Error('MD5 не совпадает для ' + p.label);
      }
    }

    setProgress('Готово. Перезагружаем часы…', 100);
    log('Полная установка NeuroWatch OS завершена.', 'ok');
    try { await session.loader.after(); } catch (_) {}
  } catch (e) {
    log('ОШИБКА FULL REINSTALL: ' + e.message, 'err');
    setProgress('Ошибка установки', 0);
    console.error(e);
  } finally {
    try { await session?.serialPort.close(); } catch (_) {}
    btn.disabled = false;
  }
}
'''
h = h[:start] + full + h[end:]

h = h.replace("УСТАНОВИТЬ NEUROWATCH OS", "ПОЛНАЯ УСТАНОВКА NEUROWATCH OS")
h = h.replace("INSTALL NEUROWATCH OS", "FULL INSTALL NEUROWATCH OS")

# Full reinstall does not depend on the factory partition table.
h = h.replace("flash.disabled = !ready || !window.__preflightPassed;", "flash.disabled = !ready;")
h = h.replace("flash.disabled = !window.__preflightPassed;", "flash.disabled = false;")
h = h.replace("document.getElementById('preflightBtn').addEventListener('click', doReadOnlyPreflight);",
              "document.getElementById('preflightBtn').style.display = 'none';")

html.write_text(h)
print("patched full reinstall mode")
