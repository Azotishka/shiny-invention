import Foundation

public enum TimeSyncPacketError: Error, Equatable {
    case invalidDate
    case unsupportedOffset
}

public enum TimeSyncPacket {
    public static let serviceUUID = "7d2ea28a-f7bd-485a-bd9d-92ad6ecfe93e"
    public static let timeUUID = "7d2ea28a-f7bd-485a-bd9d-92ad6ecfe93f"
    public static let statusUUID = "7d2ea28a-f7bd-485a-bd9d-92ad6ecfe940"
    public static let packetSize = 15

    public static func encode(
        year: Int,
        month: Int,
        day: Int,
        hour: Int,
        minute: Int,
        second: Int,
        utcOffsetMinutes: Int
    ) throws -> [UInt8] {
        guard (2020...2099).contains(year), (1...12).contains(month),
              (1...daysInMonth(month: month, year: year)).contains(day),
              (0...23).contains(hour), (0...59).contains(minute),
              (0...59).contains(second) else {
            throw TimeSyncPacketError.invalidDate
        }
        guard (-720...840).contains(utcOffsetMinutes) else {
            throw TimeSyncPacketError.unsupportedOffset
        }

        var packet: [UInt8] = [
            0x4e, 0x57, 1, 1,
            UInt8(year & 0xff), UInt8((year >> 8) & 0xff),
            UInt8(month), UInt8(day), UInt8(hour), UInt8(minute), UInt8(second),
            UInt8(utcOffsetMinutes & 0xff), UInt8((utcOffsetMinutes >> 8) & 0xff),
        ]
        let crc = crc16(packet)
        packet.append(UInt8(crc & 0xff))
        packet.append(UInt8((crc >> 8) & 0xff))
        return packet
    }

    private static func daysInMonth(month: Int, year: Int) -> Int {
        switch month {
        case 2: return isLeapYear(year) ? 29 : 28
        case 4, 6, 9, 11: return 30
        default: return 31
        }
    }

    private static func isLeapYear(_ year: Int) -> Bool {
        year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
    }

    private static func crc16(_ bytes: [UInt8]) -> UInt16 {
        var crc: UInt16 = 0xffff
        for byte in bytes {
            crc ^= UInt16(byte) << 8
            for _ in 0..<8 {
                crc = (crc & 0x8000) != 0
                    ? (crc << 1) ^ 0x1021
                    : crc << 1
            }
        }
        return crc
    }
}
