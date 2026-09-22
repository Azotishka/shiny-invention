import unittest

from check_ota import inspect, MIN_APP, MAX_SLOT


class OtaCheckTests(unittest.TestCase):
    def test_accepts_sized_esp_image_header(self):
        self.assertEqual(len(inspect(bytes([0xE9, 5]) + bytes(MIN_APP - 2))), 64)

    def test_rejects_tiny_or_oversize(self):
        for blob in (b"", bytes([0xE9, 5]) + bytes(MAX_SLOT - 1)):
            with self.subTest(length=len(blob)), self.assertRaises(ValueError):
                inspect(blob)

    def test_rejects_invalid_header(self):
        for head in (b"XX", bytes([0xE9, 0]), bytes([0xE9, 17])):
            with self.subTest(header=head), self.assertRaises(ValueError):
                inspect(head + bytes(MIN_APP - 2))


if __name__ == "__main__":
    unittest.main()
