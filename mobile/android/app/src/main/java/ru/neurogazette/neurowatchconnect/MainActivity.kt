package ru.neurogazette.neurowatchconnect

import android.Manifest
import android.app.Activity
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.UUID

class MainActivity : Activity() {
    private lateinit var statusText: TextView
    private lateinit var actionButton: Button
    private val handler = Handler(Looper.getMainLooper())
    private val serviceUuid = UUID.fromString(TimeSyncPacket.SERVICE_UUID)
    private val timeUuid = UUID.fromString(TimeSyncPacket.TIME_UUID)
    private val statusUuid = UUID.fromString(TimeSyncPacket.STATUS_UUID)
    private var adapter: BluetoothAdapter? = null
    private var scanner: BluetoothLeScanner? = null
    private var scanCallback: ScanCallback? = null
    private var gatt: BluetoothGatt? = null
    private var statusCharacteristic: BluetoothGattCharacteristic? = null
    private var scanTimeout: Runnable? = null
    private var statusPollCount = 0
    private var completed = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildScreen()
        val manager = getSystemService(Context.BLUETOOTH_SERVICE) as android.bluetooth.BluetoothManager
        adapter = manager.adapter
    }

    private fun buildScreen() {
        val background = 0xfff4f1e8.toInt()
        val ink = 0xff222a2a.toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(28), dp(32), dp(28), dp(32))
            setBackgroundColor(background)
        }
        val title = TextView(this).apply {
            text = "NEUROWATCH"
            textSize = 27f
            setTextColor(ink)
            gravity = Gravity.CENTER
        }
        val subtitle = TextView(this).apply {
            text = "Синхронизация времени"
            textSize = 18f
            setTextColor(ink)
            gravity = Gravity.CENTER
            setPadding(0, dp(8), 0, dp(24))
        }
        statusText = TextView(this).apply {
            text = "На часах открой: меню → SYNC PHONE TIME"
            textSize = 16f
            setTextColor(ink)
            gravity = Gravity.CENTER
            setPadding(dp(10), dp(18), dp(10), dp(24))
        }
        actionButton = Button(this).apply {
            text = "Подключить и синхронизировать"
            isAllCaps = false
            setOnClickListener { beginSync() }
        }
        val note = TextView(this).apply {
            text = "Телефон передаст текущие дату, время и часовой пояс.\nBLE включается на часах только на время синхронизации."
            textSize = 13f
            setTextColor(0xff5e6664.toInt())
            gravity = Gravity.CENTER
            setPadding(0, dp(22), 0, 0)
        }
        root.addView(title, fullWidth())
        root.addView(subtitle, fullWidth())
        root.addView(statusText, fullWidth())
        root.addView(actionButton, fullWidth())
        root.addView(note, fullWidth())
        setContentView(root)
    }

    private fun fullWidth(): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun beginSync() {
        completed = false
        statusPollCount = 0
        actionButton.isEnabled = false
        statusText.text = "Проверяю Bluetooth…"
        if (!requestBlePermissions()) return

        val bluetooth = adapter
        if (bluetooth == null) {
            fail("В этом устройстве нет Bluetooth LE")
            return
        }
        if (!bluetooth.isEnabled) {
            statusText.text = "Включи Bluetooth для синхронизации"
            actionButton.isEnabled = true
            startActivityForResult(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE), REQUEST_ENABLE_BT)
            return
        }
        scanner = bluetooth.bluetoothLeScanner
        startScan()
    }

    private fun requestBlePermissions(): Boolean {
        val required = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        val missing = required.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isEmpty()) return true
        requestPermissions(missing.toTypedArray(), REQUEST_BLE_PERMISSIONS)
        return false
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST_BLE_PERMISSIONS) return
        if (grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED }) {
            beginSync()
        } else {
            fail("Разреши доступ к Bluetooth в настройках телефона")
        }
    }

    @Deprecated("Uses the Android Bluetooth enable prompt")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_ENABLE_BT && resultCode == RESULT_OK) beginSync()
        else if (requestCode == REQUEST_ENABLE_BT) fail("Bluetooth не включён")
    }

    private fun startScan() {
        val bleScanner = scanner
        if (bleScanner == null) {
            fail("Не удалось запустить поиск Bluetooth")
            return
        }
        statusText.text = "Ищу NeuroWatch… Оставь часы на экране синхронизации"
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                stopScan()
                statusText.text = "Часы найдены. Подключаюсь…"
                gatt = result.device.connectGatt(
                    this@MainActivity,
                    false,
                    gattCallback,
                    BluetoothDevice.TRANSPORT_LE,
                )
            }

            override fun onScanFailed(errorCode: Int) {
                fail("Поиск Bluetooth завершился с ошибкой $errorCode")
            }
        }
        scanCallback = callback
        try {
            bleScanner.startScan(
                listOf(ScanFilter.Builder().setServiceUuid(ParcelUuid(serviceUuid)).build()),
                ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(),
                callback,
            )
        } catch (_: SecurityException) {
            fail("Нет разрешения на поиск Bluetooth")
            return
        }
        val timeout = Runnable {
            if (gatt == null && !completed) fail("Часы не найдены. Снова открой SYNC PHONE TIME")
        }
        scanTimeout = timeout
        handler.postDelayed(timeout, SCAN_TIMEOUT_MS)
    }

    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                fail("Не удалось подключиться к часам")
                return
            }
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                handler.post { statusText.text = "Подключено. Отправляю время…" }
                if (!gatt.discoverServices()) fail("Не удалось прочитать службы часов")
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED && !completed) {
                fail("Соединение с часами прервано")
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                fail("Часы не предоставили BLE-службу")
                return
            }
            val service = gatt.getService(serviceUuid)
            val timeCharacteristic = service?.getCharacteristic(timeUuid)
            statusCharacteristic = service?.getCharacteristic(statusUuid)
            if (timeCharacteristic == null || statusCharacteristic == null) {
                fail("Версия прошивки часов не поддерживает синхронизацию")
                return
            }

            val instant = Instant.now()
            val zone = ZoneId.systemDefault()
            val localTime = LocalDateTime.ofInstant(instant, zone)
            val offsetMinutes = zone.rules.getOffset(instant).totalSeconds / 60
            val payload = try {
                TimeSyncPacket.encode(localTime, offsetMinutes)
            } catch (error: IllegalArgumentException) {
                fail(error.message ?: "Часовой пояс не поддерживается")
                return
            }
            writeTimePacket(gatt, timeCharacteristic, payload)
        }

        override fun onCharacteristicWrite(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            status: Int,
        ) {
            if (characteristic.uuid != timeUuid) return
            if (status != BluetoothGatt.GATT_SUCCESS) {
                fail("Часы не приняли время")
                return
            }
            readSyncStatus(gatt)
        }

        @Deprecated("Reads status on Android versions below API 33")
        override fun onCharacteristicRead(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            status: Int,
        ) {
            handleStatusRead(gatt, characteristic.uuid, characteristic.value ?: byteArrayOf(), status)
        }

        override fun onCharacteristicRead(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            value: ByteArray,
            status: Int,
        ) {
            handleStatusRead(gatt, characteristic.uuid, value, status)
        }
    }

    private fun writeTimePacket(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        payload: ByteArray,
    ) {
        try {
            if (Build.VERSION.SDK_INT >= 33) {
                val result = gatt.writeCharacteristic(
                    characteristic,
                    payload,
                    BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT,
                )
                if (result != BluetoothStatusCodes.SUCCESS) fail("Не удалось отправить время")
            } else {
                @Suppress("DEPRECATION")
                characteristic.value = payload
                characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                @Suppress("DEPRECATION")
                if (!gatt.writeCharacteristic(characteristic)) fail("Не удалось отправить время")
            }
        } catch (_: SecurityException) {
            fail("Нет разрешения на подключение Bluetooth")
        }
    }

    private fun readSyncStatus(gatt: BluetoothGatt) {
        val characteristic = statusCharacteristic
        if (characteristic == null) {
            fail("Часы не подтвердили синхронизацию")
            return
        }
        statusPollCount += 1
        try {
            if (!gatt.readCharacteristic(characteristic)) fail("Не удалось прочитать ответ часов")
        } catch (_: SecurityException) {
            fail("Нет разрешения на чтение статуса Bluetooth")
        }
    }

    private fun handleStatusRead(
        gatt: BluetoothGatt,
        uuid: UUID,
        value: ByteArray,
        status: Int,
    ) {
        if (uuid != statusUuid) return
        if (status != BluetoothGatt.GATT_SUCCESS) {
            fail("Не удалось проверить, сохранились ли часы")
            return
        }
        when (value.toString(Charsets.UTF_8)) {
            "OK" -> {
                completed = true
                val now = ZonedDateTime.now()
                val stamp = now.format(DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm:ss"))
                handler.post { statusText.text = "Синхронизировано: $stamp\n${now.zone.id}" }
                closeGatt()
            }
            "INVALID", "ERROR" -> fail("Часы отклонили дату или часовой пояс")
            else -> if (statusPollCount < MAX_STATUS_POLLS) {
                handler.postDelayed({ readSyncStatus(gatt) }, STATUS_POLL_INTERVAL_MS)
            } else {
                fail("Часы не подтвердили синхронизацию")
            }
        }
    }

    private fun stopScan() {
        scanTimeout?.let(handler::removeCallbacks)
        scanTimeout = null
        val callback = scanCallback ?: return
        try {
            scanner?.stopScan(callback)
        } catch (_: SecurityException) {
            // The permission can be revoked while the scan is running.
        }
        scanCallback = null
    }

    private fun closeGatt() {
        val activeGatt = gatt ?: return
        gatt = null
        try {
            activeGatt.disconnect()
            activeGatt.close()
        } catch (_: SecurityException) {
            activeGatt.close()
        }
        handler.post { actionButton.isEnabled = true }
    }

    private fun fail(message: String) {
        stopScan()
        completed = true
        handler.post {
            statusText.text = message
            actionButton.isEnabled = true
        }
        closeGatt()
    }

    override fun onDestroy() {
        stopScan()
        closeGatt()
        super.onDestroy()
    }

    companion object {
        private const val REQUEST_ENABLE_BT = 41
        private const val REQUEST_BLE_PERMISSIONS = 42
        private const val SCAN_TIMEOUT_MS = 15_000L
        private const val MAX_STATUS_POLLS = 15
        private const val STATUS_POLL_INTERVAL_MS = 150L
    }
}
