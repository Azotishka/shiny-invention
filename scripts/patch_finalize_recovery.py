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

finalize = r'''async function doFlash() {
  const btn = document.getElementById('flashBtn');
  btn.disabled = true;
  document.getElementById('progressWrap').style.display = 'block';
  openLog();

  let session = null;

  async function verifyApp(loader, expected, appLength) {
    let last = null;
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        const got = String(await loader.flashMd5sum(0x10000, appLength)).toLowerCase();
        log('MD5 app attempt ' + attempt + ': ' + got, 'info');
        return got === expected;
      } catch (e) {
        last = e;
        log('MD5 app attempt ' + attempt + ' failed: ' + e.message, 'info');
        await new Promise(r => setTimeout(r, 450));
      }
    }
    throw last || new Error('MD5 app verification failed');
  }

  async function reconnectStub() {
    try { await session?.serialPort.close(); } catch (_) {}
    try { Android.disconnect(); } catch (_) {}
    await new Promise(r => setTimeout(r, 500));
    session = await openChipRom();
    assertSupportedNeuroWatchChip(session.chip);
    await session.loader.runStub();
  }

  try {
    const app = b64ToBytes(Android.readAssetBase64('app.bin'));
    if (!app.length || app[0] !== 0xE9) throw new Error('app.bin отсутствует или повреждён.');
    const expected = String(Android.assetMd5('app.bin') || '').toLowerCase();
    if (!/^[0-9a-f]{32}$/.test(expected)) throw new Error('Не удалось вычислить MD5 app.bin.');

    setProgress('Подключаемся к ROM bootloader…', 10);
    session = await openChipRom();
    assertSupportedNeuroWatchChip(session.chip);
    log('Чип: ' + session.chip, 'ok');
    await session.loader.runStub();

    setProgress('Проверяем уже записанную NeuroWatch OS…', 35);
    let ok = false;
    try {
      ok = await verifyApp(session.loader, expected, app.length);
    } catch (e) {
      log('Первый канал проверки потерян, переподключаемся: ' + e.message, 'info');
      await reconnectStub();
      try { ok = await verifyApp(session.loader, expected, app.length); } catch (_) { ok = false; }
    }

    if (!ok) {
      setProgress('Повторно записываем только NeuroWatch OS…', 55);
      log('app.bin не подтверждён. Bootloader/partition table уже записаны — переписываем только приложение @0x10000.', 'info');
      await writeFlashRaw(
        session.loader,
        [{ data: app, address: 0x10000, label: 'NeuroWatch OS' }],
        (_idx, written, total) => {
          const pct = total ? Math.round(written * 100 / total) : 100;
          setProgress('NeuroWatch OS: ' + pct + '%', 55 + Math.round(pct * 0.3));
        }
      );

      setProgress('Финальная MD5-проверка…', 88);
      let verified = false;
      try {
        verified = await verifyApp(session.loader, expected, app.length);
      } catch (e) {
        log('MD5 после записи: переподключение…', 'info');
        await reconnectStub();
        verified = await verifyApp(session.loader, expected, app.length);
      }
      if (!verified) throw new Error('Финальная MD5-проверка app.bin не совпала.');
    }

    log('NeuroWatch OS подтверждена по MD5.', 'ok');

    setProgress('Перезагружаем часы в NeuroWatch OS…', 98);
    // Normal boot reset: keep IO0 high (DTR deasserted), pulse EN via RTS.
    Android.setSignalMode(2);
    Android.setSignals(1, 0);
    await new Promise(r => setTimeout(r, 180));
    Android.setSignals(0, 0);
    await new Promise(r => setTimeout(r, 500));

    setProgress('Готово', 100);
    log('NeuroWatch OS должна запуститься сейчас.', 'ok');
  } catch (e) {
    log('ОШИБКА FINALIZE: ' + e.message, 'err');
    setProgress('Ошибка финализации', 0);
    console.error(e);
  } finally {
    try { await session?.serialPort.close(); } catch (_) {}
    btn.disabled = false;
  }
}
'''
h = h[:start] + finalize + h[end:]
h = h.replace("УСТАНОВИТЬ NEUROWATCH OS", "ПРОВЕРИТЬ И ЗАПУСТИТЬ NEUROWATCH OS")
h = h.replace("INSTALL NEUROWATCH OS", "VERIFY & BOOT NEUROWATCH OS")
h = h.replace("flash.disabled = !ready || !window.__preflightPassed;", "flash.disabled = !ready;")
h = h.replace("flash.disabled = !window.__preflightPassed;", "flash.disabled = false;")
h = h.replace("document.getElementById('preflightBtn').addEventListener('click', doReadOnlyPreflight);",
              "document.getElementById('preflightBtn').style.display = 'none';")
html.write_text(h)
print("patched finalize/recovery mode")
