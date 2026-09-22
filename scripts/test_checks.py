import struct
import unittest

from check_ota import inspect, MIN_APP, MAX_SLOT


def make_image(segments=1, fill=MIN_APP):
    """Minimal synthetic ESP32 app image for structural tests (not flashable)."""
    header = bytes([0xE9, segments]) + bytes(22)
    chunk = struct.pack("<II", 0x3F400020, 4) + bytes([1, 2, 3, 4])
    payload = header + chunk * segments
    return payload + bytes(max(0, fill - len(payload)))


class OtaCheckTests(unittest.TestCase):
    def test_accepts_structurally_valid_sized_image(self):
        self.assertEqual(len(inspect(make_image())), 64)

    def test_rejects_tiny_or_oversize(self):
        for blob in (b"", make_image(fill=MAX_SLOT + 1)):
            with self.subTest(length=len(blob)), self.assertRaises(ValueError):
                inspect(blob)

    def test_rejects_invalid_header(self):
        for head in (b"XX", bytes([0xE9, 0]), bytes([0xE9, 17])):
            with self.subTest(header=head), self.assertRaises(ValueError):
                inspect(head + bytes(MIN_APP - 2))

    def test_rejects_truncated_or_impossible_segments(self):
        cases = [
            bytes([0xE9, 1]) + bytes(MIN_APP - 2),
            (bytes([0xE9, 1]) + bytes(22) + struct.pack("<II", 0x3F400020, 0xFFFFFFFF)
             + bytes(MIN_APP - 32)),
        ]
        for blob in cases:
            with self.subTest(case=blob[24:32]), self.assertRaises(ValueError):
                inspect(blob)


if __name__ == "__main__":
    unittest.main()
