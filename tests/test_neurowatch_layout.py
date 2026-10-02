#!/usr/bin/env python3
import re
from pathlib import Path

SOURCE = Path("firmware/NeuroWatch_OS/NeuroWatch_OS.ino")
TEXT = SOURCE.read_text(encoding="utf-8")

REQUIRED = [
    "NW_FACE_HEADER",
    "NW_FACE_TIME",
    "NW_FACE_DATE",
    "NW_FACE_BATTERY",
    "NW_FACE_STEPS",
    "NW_FACE_ALARM",
    "NW_FACE_CONTROLS",
]

for name in REQUIRED:
    assert name in TEXT, f"missing deterministic layout region: {name}"

assert "MENU:SETTINGS   NW " not in TEXT, "legacy crowded footer still present"

# Region declarations are x,y,w,h and must stay inside the 200x200 panel.
regions = re.findall(r"NW_FACE_[A-Z]+\s*\{\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\}", TEXT)
assert len(regions) >= 7, "expected all main-face regions"

rects = [tuple(map(int, r)) for r in regions]
for x, y, w, h in rects:
    assert 0 <= x < 200 and 0 <= y < 200
    assert w > 0 and h > 0
    assert x + w <= 200 and y + h <= 200

def overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah

for i, a in enumerate(rects):
    for b in rects[i + 1:]:
        assert not overlap(a, b), f"layout regions overlap: {a} vs {b}"

print("NeuroWatch UI layout tests: PASS")
