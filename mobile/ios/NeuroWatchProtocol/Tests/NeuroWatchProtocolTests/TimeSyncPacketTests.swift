import XCTest
@testable import NeuroWatchProtocol

final class TimeSyncPacketTests: XCTestCase {
    func testEncodesTheSharedEkaterinburgGoldenPacket() throws {
        let packet = try TimeSyncPacket.encode(
            year: 2026, month: 9, day: 27,
            hour: 1, minute: 29, second: 18,
            utcOffsetMinutes: 300
        )
        XCTAssertEqual(packet, [78, 87, 1, 1, 234, 7, 9, 27, 1, 29, 18, 44, 1, 158, 200])
    }

    func testRejectsOffsetsOutsideSupportedTimeZones() {
        XCTAssertThrowsError(try TimeSyncPacket.encode(
            year: 2026, month: 9, day: 27,
            hour: 1, minute: 29, second: 18,
            utcOffsetMinutes: 900
        ))
    }

    func testEncodesNegativeUtcOffsetAsSignedLittleEndian() throws {
        let packet = try TimeSyncPacket.encode(
            year: 2026, month: 9, day: 27,
            hour: 1, minute: 29, second: 18,
            utcOffsetMinutes: -300
        )
        XCTAssertEqual(packet, [78, 87, 1, 1, 234, 7, 9, 27, 1, 29, 18, 212, 254, 6, 76])
    }
}
