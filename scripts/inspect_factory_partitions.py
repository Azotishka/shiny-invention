#!/usr/bin/env python3
"""Read-only ESP32 partition-table inspector. Does not communicate with or flash a watch.

Expected input: a USB-created full 4 MiB flash backup, or a 0x1000-byte
partition-table dump from 0x8000. It cannot prove a bootloader is recoverable.
"""
import argparse
import struct
from pathlib import Path

FLASH_SIZE = 4 * 1024 * 1024
TABLE_OFFSET = 0x8000
TABLE_SIZE = 0x1000
SLOT_MINIMUM = 0x1E0000
ENTRY = struct.Struct("<HBBII16sI")
MAGIC = 0x50AA
END = 0xFFFF


def parse_table(raw: bytes, flash_size: int = FLASH_SIZE):
    if len(raw) == flash_size:
        table = raw[TABLE_OFFSET:TABLE_OFFSET + TABLE_SIZE]
    elif len(raw) == TABLE_SIZE:
        table = raw
    else:
        raise ValueError("Expected a full 4 MiB flash backup or a 4096-byte table dump")
    partitions = []
    for offset in range(0, TABLE_SIZE, ENTRY.size):
        magic, kind, subtype, address, size, label_raw, flags = ENTRY.unpack_from(table, offset)
        if magic == END:
            break
        if magic == 0xEBEB:  # ESP-IDF partition-table MD5 marker
            break
        if magic != MAGIC:
            raise ValueError(f"Unexpected partition entry at 0x{offset:x}: 0x{magic:04x}")
        if not size or address < TABLE_OFFSET + TABLE_SIZE or address >= flash_size or size > flash_size - address:
            raise ValueError(f"Partition outside physical Flash at 0x{address:x}")
        label = label_raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
        partitions.append(dict(type=kind, subtype=subtype, offset=address,
                               size=size, label=label, flags=flags))
    if not partitions:
        raise ValueError("No ESP32 partitions found")
    intervals = sorted(partitions, key=lambda p: p["offset"])
    for previous, current in zip(intervals, intervals[1:]):
        if previous["offset"] + previous["size"] > current["offset"]:
            raise ValueError(f"Overlapping partitions: {previous['label']} / {current['label']}")
    return partitions


def assess(partitions: list[dict], image_size: int = SLOT_MINIMUM):
    app0 = [p for p in partitions if p["type"] == 0 and p["subtype"] == 0x10]
    app1 = [p for p in partitions if p["type"] == 0 and p["subtype"] == 0x11]
    otadata = [p for p in partitions if p["type"] == 1 and p["subtype"] == 0]
    return (len(app0) == 1 and len(app1) == 1 and len(otadata) == 1
            and otadata[0]["size"] >= 0x2000
            and app0[0]["size"] >= image_size and app1[0]["size"] >= image_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path, help="4 MiB flash dump or 0x1000 partition-table dump")
    parser.add_argument("--image", type=Path, help="Optional application .bin to check its byte length")
    args = parser.parse_args()
    partitions = parse_table(args.backup.read_bytes())
    for p in partitions:
        print(f"{p['label']:16} type={p['type']:02x} subtype={p['subtype']:02x} "
              f"offset=0x{p['offset']:06x} size={p['size']} B")
    image_size = args.image.stat().st_size if args.image else SLOT_MINIMUM
    print("DUAL OTA STRUCTURAL CHECK:", "PASS" if assess(partitions, image_size) else "FAIL")
    print("IMPORTANT: not a bootloader, live-device, rollback or USB-recovery verification.")


if __name__ == "__main__":
    main()
