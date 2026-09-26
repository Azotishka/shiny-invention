import Combine
import CoreBluetooth
import Foundation
import NeuroWatchProtocol

final class BluetoothSyncManager: NSObject, ObservableObject {
    @Published private(set) var status = "На часах открой меню → SYNC PHONE TIME"
    @Published private(set) var isSyncing = false

    private var central: CBCentralManager!
    private var watch: CBPeripheral?
    private var timeCharacteristic: CBCharacteristic?
    private var statusCharacteristic: CBCharacteristic?
    private var scanTimeout: DispatchWorkItem?
    private var statusPolls = 0
    private var synced = false

    private let serviceID = CBUUID(string: TimeSyncPacket.serviceUUID)
    private let timeID = CBUUID(string: TimeSyncPacket.timeUUID)
    private let statusID = CBUUID(string: TimeSyncPacket.statusUUID)

    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: .main)
    }

    func startSync() {
        isSyncing = true
        synced = false
        statusPolls = 0
        status = "Проверяю Bluetooth…"
        switch central.state {
        case .poweredOn:
            scanForWatch()
        case .unauthorized:
            fail("Разреши NeuroWatch Connect доступ к Bluetooth")
        case .poweredOff:
            fail("Включи Bluetooth на iPhone")
        case .unsupported:
            fail("Этот iPhone не поддерживает Bluetooth LE")
        default:
            status = "Жду запуска Bluetooth…"
        }
    }

    func cancel() {
        isSyncing = false
        scanTimeout?.cancel()
        scanTimeout = nil
        central.stopScan()
        if let watch { central.cancelPeripheralConnection(watch) }
        status = "Синхронизация отменена"
    }

    private func scanForWatch() {
        guard isSyncing else { return }
        status = "Ищу NeuroWatch… Оставь часы на экране синхронизации"
        central.scanForPeripherals(withServices: [serviceID], options: [
            CBCentralManagerScanOptionAllowDuplicatesKey: false
        ])
        let timeout = DispatchWorkItem { [weak self] in
            guard let self, self.isSyncing, self.watch == nil else { return }
            self.central.stopScan()
            self.fail("Часы не найдены. Снова открой SYNC PHONE TIME")
        }
        scanTimeout = timeout
        DispatchQueue.main.asyncAfter(deadline: .now() + 15, execute: timeout)
    }

    private func sendCurrentLocalTime() {
        guard let watch, let timeCharacteristic, statusCharacteristic != nil else {
            fail("В прошивке часов нет службы синхронизации")
            return
        }

        let instant = Date()
        let zone = TimeZone.autoupdatingCurrent
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = zone
        let parts = calendar.dateComponents(
            [.year, .month, .day, .hour, .minute, .second],
            from: instant
        )
        guard let year = parts.year, let month = parts.month, let day = parts.day,
              let hour = parts.hour, let minute = parts.minute, let second = parts.second else {
            fail("Не удалось прочитать время iPhone")
            return
        }

        do {
            let offsetMinutes = zone.secondsFromGMT(for: instant) / 60
            let packet = try TimeSyncPacket.encode(
                year: year, month: month, day: day,
                hour: hour, minute: minute, second: second,
                utcOffsetMinutes: offsetMinutes
            )
            status = "Передаю дату, время и \(zone.identifier)…"
            watch.writeValue(Data(packet), for: timeCharacteristic, type: .withResponse)
        } catch {
            fail("Часовой пояс iPhone не поддерживается")
        }
    }

    private func readWatchStatus() {
        guard let watch, let statusCharacteristic else {
            fail("Часы не отправили подтверждение")
            return
        }
        statusPolls += 1
        watch.readValue(for: statusCharacteristic)
    }

    private func handleStatus(_ value: Data) {
        switch String(data: value, encoding: .utf8) ?? "" {
        case "OK":
            synced = true
            isSyncing = false
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "ru_RU")
            formatter.timeZone = .autoupdatingCurrent
            formatter.dateFormat = "dd.MM.yyyy HH:mm:ss"
            status = "Синхронизировано: \(formatter.string(from: Date()))\n\(TimeZone.autoupdatingCurrent.identifier)"
            if let watch { central.cancelPeripheralConnection(watch) }
        case "INVALID", "ERROR":
            fail("Часы отклонили время. Попробуй ещё раз")
        default:
            guard statusPolls < 15 else {
                fail("Часы не подтвердили синхронизацию")
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
                self?.readWatchStatus()
            }
        }
    }

    private func fail(_ message: String) {
        scanTimeout?.cancel()
        scanTimeout = nil
        central.stopScan()
        if let watch { central.cancelPeripheralConnection(watch) }
        isSyncing = false
        status = message
    }
}

extension BluetoothSyncManager: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        guard isSyncing else { return }
        if central.state == .poweredOn {
            scanForWatch()
        } else if central.state == .poweredOff {
            fail("Включи Bluetooth на iPhone")
        } else if central.state == .unauthorized {
            fail("Разреши NeuroWatch Connect доступ к Bluetooth")
        }
    }

    func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        scanTimeout?.cancel()
        scanTimeout = nil
        central.stopScan()
        watch = peripheral
        watch?.delegate = self
        status = "Часы найдены. Подключаюсь…"
        central.connect(peripheral, options: nil)
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        status = "Подключено. Читаю службы часов…"
        peripheral.discoverServices([serviceID])
    }

    func centralManager(
        _ central: CBCentralManager,
        didFailToConnect peripheral: CBPeripheral,
        error: Error?
    ) {
        fail("Не удалось подключиться к часам")
    }

    func centralManager(
        _ central: CBCentralManager,
        didDisconnectPeripheral peripheral: CBPeripheral,
        error: Error?
    ) {
        watch = nil
        if isSyncing && !synced { fail("Соединение с часами прервано") }
    }
}

extension BluetoothSyncManager: CBPeripheralDelegate {
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard error == nil,
              let service = peripheral.services?.first(where: { $0.uuid == serviceID }) else {
            fail("Не найдена служба синхронизации в часах")
            return
        }
        peripheral.discoverCharacteristics([timeID, statusID], for: service)
    }

    func peripheral(
        _ peripheral: CBPeripheral,
        didDiscoverCharacteristicsFor service: CBService,
        error: Error?
    ) {
        guard error == nil else {
            fail("Не удалось прочитать службы часов")
            return
        }
        timeCharacteristic = service.characteristics?.first(where: { $0.uuid == timeID })
        statusCharacteristic = service.characteristics?.first(where: { $0.uuid == statusID })
        sendCurrentLocalTime()
    }

    func peripheral(
        _ peripheral: CBPeripheral,
        didWriteValueFor characteristic: CBCharacteristic,
        error: Error?
    ) {
        guard characteristic.uuid == timeID else { return }
        if error != nil {
            fail("Часы не приняли время")
        } else {
            readWatchStatus()
        }
    }

    func peripheral(
        _ peripheral: CBPeripheral,
        didUpdateValueFor characteristic: CBCharacteristic,
        error: Error?
    ) {
        guard characteristic.uuid == statusID else { return }
        guard error == nil, let value = characteristic.value else {
            fail("Не удалось прочитать ответ часов")
            return
        }
        handleStatus(value)
    }
}
