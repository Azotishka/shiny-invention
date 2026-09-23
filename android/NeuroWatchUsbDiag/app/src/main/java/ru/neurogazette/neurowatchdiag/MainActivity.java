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
        title.setText("NeuroWatch USB Diagnostic");
        title.setTextSize(24);
        root.addView(title);

        TextView safety = new TextView(this);
        safety.setText("\nREAD-ONLY режим. Приложение только перечисляет USB-устройства. Оно не переводит ESP32 в bootloader, не стирает Flash и ничего не прошивает.\n");
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
            if (cp2102 || espUsbSerialJtag) knownCandidate = true;

            if (cp2102) {
                b.append("★ Silicon Labs CP2102 — совместимо с классической Watchy V2\n");
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
            b.append("Android сейчас не видит ни одного USB-устройства.\n");
            b.append("Поскольку аппаратная ревизия часов ещё не подтверждена, не делаем вывод только по CP2102. Проверь data-кабель и USB-C/OTG-схему подключения.\n");
        } else if (!knownCandidate) {
            b.append("Известные идентификаторы CP2102 и Espressif USB Serial/JTAG не найдены. Не прошивай часы; сохрани VID/PID найденных устройств для анализа.\n");
        } else {
            b.append("Подходящий USB-интерфейс найден. Это только диагностика соединения; запись Flash остаётся запрещена на этом этапе.\n");
        }

        output.setText(b.toString());
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
