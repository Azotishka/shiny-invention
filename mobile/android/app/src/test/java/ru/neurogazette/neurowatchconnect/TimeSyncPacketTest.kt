package ru.neurogazette.neurowatchconnect

import java.time.LocalDateTime
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class TimeSyncPacketTest {
    @Test
    fun encodesTheSharedEkaterinburgGoldenPacket() {
        val local = LocalDateTime.of(2026, 9, 27, 1, 29, 18)
        val expected = byteArrayOf(
            78, 87, 1, 1, -22, 7, 9, 27, 1, 29, 18, 44, 1, -98, -56,
        )
        assertArrayEquals(expected, TimeSyncPacket.encode(local, 300))
    }

    @Test
    fun rejectsOffsetsOutsideSupportedTimeZones() {
        val local = LocalDateTime.of(2026, 9, 27, 1, 29, 18)
        assertThrows(IllegalArgumentException::class.java) {
            TimeSyncPacket.encode(local, 900)
        }
    }

    @Test
    fun encodesNegativeUtcOffsetAsSignedLittleEndian() {
        val local = LocalDateTime.of(2026, 9, 27, 1, 29, 18)
        val expected = byteArrayOf(
            78, 87, 1, 1, -22, 7, 9, 27, 1, 29, 18, -44, -2, 6, 76,
        )
        assertArrayEquals(expected, TimeSyncPacket.encode(local, -300))
    }
}
