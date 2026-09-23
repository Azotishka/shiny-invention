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

        boolean watchyCandidate = false;
        for (UsbDevice d : devices.values()) {
            int vid = d.getVendorId();
            int pid = d.getProductId();
            boolean cp2102 = vid == 0x10C4 && pid == 0xEA60;
            if (cp2102) watchyCandidate = true;

            b.append(cp2102 ? "★ Возможный Watchy V2 / CP2102\n" : "USB-устройство\n");
            b.append("Имя: ").append(d.getDeviceName()).append("\n");
            b.append(String.format("VID: 0x%04X (%d)\n", vid, vid));
            b.append(String.format("PID: 0x%04X (%d)\n", pid, pid));
            b.append("Класс: ").append(d.getDeviceClass()).append("\n");
            b.append("Интерфейсов: ").append(d.getInterfaceCount()).append("\n\n");
        }

        if (devices.isEmpty()) {
            b.append("Android сейчас не видит ни одного USB-устройства.\n");
            b.append("Если другое устройство определяется через тот же OTG, но Watchy нет, сначала проверь кабель Watchy: он должен поддерживать DATA, а не только зарядку.\n");
        } else if (!watchyCandidate) {
            b.append("CP2102 (10C4:EA60) не найден. Не прошивай часы. Сохрани этот экран для диагностики.\n");
        } else {
            b.append("CP2102 найден. Это только подтверждение USB-соединения; запись Flash по-прежнему заблокирована на этом этапе.\n");
        }

        output.setText(b.toString());
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
