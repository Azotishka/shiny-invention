"""Synthetic ESP32 partition-table tests; no device access or flashing."""
import struct
import unittest
from inspect_factory_partitions import (FLASH_SIZE, TABLE_SIZE, MAGIC,
                                        parse_table, assess)

ENTRY = struct.Struct("<HBBII16sI")


def record(type_, subtype, offset, size, label):
    return ENTRY.pack(MAGIC, type_, subtype, offset, size,
                      label.encode("ascii").ljust(16, b"\x00"), 0)


def table(ota=True):
    records = [
        record(1, 2, 0x9000, 0x5000, "nvs"),
        record(1, 0, 0xe000, 0x2000, "otadata"),
    ]
    if ota:
        records += [
            record(0, 0x10, 0x10000, 0x1e0000, "app0"),
            record(0, 0x11, 0x1f0000, 0x1e0000, "app1"),
        ]
    else:
        records += [record(0, 0, 0x10000, 0x300000, "factory")]
    return b"".join(records).ljust(TABLE_SIZE, b"\xff")


class PartitionInspectorTests(unittest.TestCase):
    def test_dual_ota_table_sufficient_for_candidate(self):
        partitions = parse_table(table())
        self.assertTrue(assess(partitions, 1828288))
        self.assertFalse(assess(partitions, 0x1e0000 + 1))

    def test_huge_app_has_no_dual_ota(self):
        self.assertFalse(assess(parse_table(table(ota=False)), 1828288))

    def test_full_flash_backup_can_be_read(self):
        backup = b"\xff" * 0x8000 + table() + b"\xff" * (FLASH_SIZE - 0x9000)
        self.assertEqual(parse_table(backup), parse_table(table()))

    def test_bad_magic_short_data_and_out_of_bounds_rejected(self):
        cases = [
            b"bad",
            b"\x00" * TABLE_SIZE,
            record(0, 0x10, FLASH_SIZE - 4096, 8192, "bad").ljust(TABLE_SIZE, b"\xff"),
        ]
        for blob in cases:
            with self.subTest(case=len(blob)), self.assertRaises(ValueError):
                parse_table(blob)

    def test_overlap_is_rejected(self):
        bad = record(0, 0x10, 0x10000, 0x1e0000, "app0") + (
            record(0, 0x11, 0x1e0000, 0x1e0000, "app1"))
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            parse_table(bad.ljust(TABLE_SIZE, b"\xff"))


if __name__ == "__main__":
    unittest.main()
