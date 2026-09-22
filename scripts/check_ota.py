#!/usr/bin/env python3
"""Reject obviously malformed ESP32 app OTA images; not hardware validation."""
import argparse
import hashlib
from pathlib import Path

MIN_APP = 64 * 1024
MAX_SLOT = 0x1E0000  # min_spiffs OTA partition on 4 MB ESP32


def inspect(data: bytes) -> str:
    if not MIN_APP <= len(data) <= MAX_SLOT:
        raise ValueError(f"OTA image length {len(data)} outside {MIN_APP}..{MAX_SLOT}")
    if data[0] != 0xE9 or not 1 <= data[1] <= 16:
        raise ValueError("Invalid ESP image header")
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    if args.image.suffix.lower() != ".bin":
        parser.error("Expected app image .bin")
    binary = args.image.read_bytes()
    print(f"OTA-CANDIDATE {args.image.name} bytes={len(binary)} sha256={inspect(binary)}")
    print("UNVERIFIED: actual installed partition table, hardware, reboot and recovery")
