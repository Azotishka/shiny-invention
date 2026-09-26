package ru.neurogazette.neurowatchconnect

import java.time.LocalDateTime

internal object TimeSyncPacket {
    const val SERVICE_UUID = "7d2ea28a-f7bd-485a-bd9d-92ad6ecfe93e"
    const val TIME_UUID = "7d2ea28a-f7bd-485a-bd9d-92ad6ecfe93f"
    const val STATUS_UUID = "7d2ea28a-f7bd-485a-bd9d-92ad6ecfe940"
    const val PACKET_SIZE = 15

    fun encode(local: LocalDateTime, utcOffsetMinutes: Int): ByteArray {
        require(local.year in 2020..2099) { "Year is outside the watch RTC range" }
        require(utcOffsetMinutes in -720..840) { "Timezone offset is not supported" }

        val packet = ByteArray(PACKET_SIZE)
        packet[0] = 'N'.code.toByte()
        packet[1] = 'W'.code.toByte()
        packet[2] = 1
        packet[3] = 1
        packet[4] = (local.year and 0xff).toByte()
        packet[5] = (local.year ushr 8).toByte()
        packet[6] = local.monthValue.toByte()
        packet[7] = local.dayOfMonth.toByte()
        packet[8] = local.hour.toByte()
        packet[9] = local.minute.toByte()
        packet[10] = local.second.toByte()
        packet[11] = (utcOffsetMinutes and 0xff).toByte()
        packet[12] = ((utcOffsetMinutes ushr 8) and 0xff).toByte()
        val crc = crc16(packet, 13)
        packet[13] = (crc and 0xff).toByte()
        packet[14] = ((crc ushr 8) and 0xff).toByte()
        return packet
    }

    private fun crc16(data: ByteArray, length: Int): Int {
        var crc = 0xffff
        for (index in 0 until length) {
            crc = crc xor ((data[index].toInt() and 0xff) shl 8)
            repeat(8) {
                crc = if ((crc and 0x8000) != 0) {
                    ((crc shl 1) xor 0x1021) and 0xffff
                } else {
                    (crc shl 1) and 0xffff
                }
            }
        }
        return crc
    }
}
