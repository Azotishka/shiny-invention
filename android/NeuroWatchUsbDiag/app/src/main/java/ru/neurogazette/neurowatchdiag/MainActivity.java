package ru.neurogazette.neurowatchdiag;

import android.app.Activity;
import android.content.Context;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbManager;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.Map;

public class MainActivity extends Activity {
    private TextView output;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(18);
        root.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("NeuroWatch USB Diagnostic v0.2");
        title.setTextSize(24);
        root.addView(title);

        TextView safety = new TextView(this);
        safety.setText("\nREAD-ONLY режим. Приложение только перечисляет USB-устройства. Оно не переводит ESP в bootloader, не стирает Flash и ничего не прошивает.\n");
        safety.setTextSize(16);
        root.addView(safety);

        Button refresh = new Button(this);
        refresh.setText("Обновить список USB");
        refresh.setOnClickListener(v -> scan());
        root.addView(refresh);

        output = new TextView(this);
        output.setTextSize(15);
        output.setTextIsSelectable(true);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(output, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));

        setContentView(root);
        scan();
    }

    @Override
    protected void onResume() {
        super.onResume();
        scan();
    }

    private void scan() {
        UsbManager manager = (UsbManager) getSystemService(Context.USB_SERVICE);
        boolean host = getPackageManager().hasSystemFeature("android.hardware.usb.host");
        Map<String, UsbDevice> devices = manager.getDeviceList();

        StringBuilder b = new StringBuilder();
        b.append("USB Host: ").append(host ? "да" : "нет").append("\n");
        b.append("Найдено USB-устройств: ").append(devices.size()).append("\n\n");

        boolean knownCandidate = false;
        for (UsbDevice d : devices.values()) {
            int vid = d.getVendorId();
            int pid = d.getProductId();
            boolean cp2102 = vid == 0x10C4 && pid == 0xEA60;
            boolean espUsbSerialJtag = vid == 0x303A && pid == 0x1001;
            boolean ch9102 = vid == 0x1A86 && pid == 0x55D4;
            if (cp2102 || espUsbSerialJtag || ch9102) knownCandidate = true;

            if (ch9102) {
                b.append("★ WCH/QinHeng CH9102 USB-UART — USB DATA подтверждён\n");
            } else if (cp2102) {
                b.append("★ Silicon Labs CP2102 — классический USB-UART Watchy V2\n");
            } else if (espUsbSerialJtag) {
                b.append("★ Espressif USB Serial/JTAG — типично для ESP32-S3 / Watchy V3\n");
            } else {
                b.append("USB-устройство\n");
            }

            b.append("Имя: ").append(d.getDeviceName()).append("\n");
            b.append(String.format("VID: 0x%04X (%d)\n", vid, vid));
            b.append(String.format("PID: 0x%04X (%d)\n", pid, pid));
            b.append("Класс: ").append(d.getDeviceClass()).append("\n");
            b.append("Интерфейсов: ").append(d.getInterfaceCount()).append("\n\n");
        }

        if (devices.isEmpty()) {
            b.append("Android сейчас не видит ни одного USB-устройства. Не прошивай часы.\n");
        } else if (!knownCandidate) {
            b.append("USB-устройство видно, но его VID/PID пока не распознаны. Не прошивай часы; сохрани VID/PID для анализа.\n");
        } else {
            b.append("USB-соединение подтверждено. Это ещё НЕ подтверждает точную ревизию платы или совместимость прошивки.\n");
            b.append("Следующий безопасный этап: открыть serial-порт в read-only режиме и определить микроконтроллер без записи Flash.\n");
        }

        output.setText(b.toString());
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
