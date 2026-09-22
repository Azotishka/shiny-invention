#!/usr/bin/env python3
"""Conservative ESP32 app-image preflight; not a boot or OTA compatibility test."""
import argparse
import hashlib
import struct
from pathlib import Path

MIN_APP = 64 * 1024
MAX_SLOT = 0x1E0000  # Arduino-ESP32 2.0.15 min_spiffs app partition size.
HEADER_BYTES = 24
SEGMENT_HEADER_BYTES = 8


def inspect(data: bytes) -> str:
    """Validate size, ESP magic and bounded declared segment lengths."""
    size = len(data)
    if not MIN_APP <= size <= MAX_SLOT:
        raise ValueError(f"OTA image length {size} outside {MIN_APP}..{MAX_SLOT}")
    if data[0] != 0xE9 or not 1 <= data[1] <= 16:
        raise ValueError("Invalid ESP image magic or segment count")

    offset = HEADER_BYTES
    for index in range(data[1]):
        if offset + SEGMENT_HEADER_BYTES > size:
            raise ValueError(f"Missing ESP segment header {index}")
        load_address, length = struct.unpack_from("<II", data, offset)
        offset += SEGMENT_HEADER_BYTES
        if length == 0 or length > size - offset:
            raise ValueError(
                f"ESP segment {index} invalid data length {length} "
                f"at 0x{load_address:08x}"
            )
        offset += length
    if offset >= size:
        raise ValueError("ESP image has no checksum/trailer after segments")
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    if args.image.suffix.lower() != ".bin":
        parser.error("Expected an ESP32 application image .bin")
    binary = args.image.read_bytes()
    print(f"OTA-CANDIDATE {args.image.name} bytes={len(binary)} sha256={inspect(binary)}")
    print("NOT VERIFIED: installed partition layout, hardware, boot, power or rollback")
