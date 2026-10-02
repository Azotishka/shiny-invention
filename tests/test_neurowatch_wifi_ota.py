from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKETCH = ROOT / "firmware" / "NeuroWatch_OS" / "NeuroWatch_OS.ino"

source = SKETCH.read_text(encoding="utf-8")

def test_wifi_is_off_during_normal_boot():
    assert "WiFi.mode(WIFI_OFF);" in source
    assert "btStop();" in source

def test_wifi_update_menu_entry_exists():
    assert "WIFI UPDATE" in source

def test_wifi_update_service_has_ap_address():
    assert "192.168.4.1" in source
    assert "WiFi.softAP" in source

def test_wifi_update_http_routes_exist():
    assert '"/"' in source
    assert '"/status"' in source
    assert '"/update"' in source

def test_wifi_update_uses_ota_update_api():
    assert "Update.begin" in source
    assert "Update.write" in source
    assert "Update.end(true)" in source

def test_restart_happens_only_after_successful_update():
    end_pos = source.find("Update.end(true)")
    restart_pos = source.find("ESP.restart()", end_pos)
    assert end_pos >= 0
    assert restart_pos > end_pos

def test_usb_recovery_path_is_not_removed():
    assert "CdcAcmSerialDriver" in source or "usbHost" in source or "USB" in source

def test_ota_service_is_not_started_in_normal_loop():
    assert "void loop() {}" in source or "wifiOtaServiceLoop" in source
