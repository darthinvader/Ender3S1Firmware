#!/usr/bin/env python3
"""Check that a .bin looks like a bootable STM32F103 application image.

A Cortex-M image starts with two words:

    offset 0x00  initial stack pointer
    offset 0x04  reset handler address (Thumb, so bit 0 is set)

For this board the 28 KiB serial/SD bootloader occupies
0x08000000..0x08007000, so a firmware image must point its reset handler at or
above 0x08007000. Catching a wrong image here is much cheaper than catching it
after a flash that produced a silent board.

Two stack-pointer rules are used:

  * hard failure - the SP is outside the 64 KiB window at 0x20000000, which no
                   STM32F103 in this family has, so the image cannot be for
                   this board.
  * note only    - the SP sits above 48 KiB, i.e. the image was linked for a
                   device with 64 KiB SRAM. Creality's own stock images do this;
                   the mriscoc builds in this repository do not. It is reported,
                   never treated as an error, because vendor images are
                   redistributed unmodified.

Exit status: 0 = plausible image, 1 = not a plausible image, 2 = bad usage.

Usage: check-vector-table.py <file.bin> [more.bin ...]
"""
from __future__ import annotations

import struct
import sys

FLASH_BASE = 0x08000000
FLASH_SIZE = 0x40000  # 256 KiB
APP_BASE = 0x08007000  # 28 KiB bootloader below the application
APP_SIZE = 233472  # bytes available to the application
SRAM_BASE = 0x20000000
SRAM_48K_TOP = 0x2000C000
SRAM_64K_TOP = 0x20010000


def check(path):
    notes = []
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
            size = len(head) + len(fh.read())
    except OSError as exc:
        return False, ["cannot read %s: %s" % (path, exc)]

    if len(head) < 8:
        return False, ["file is shorter than one vector table"]

    sp, reset = struct.unpack("<II", head)
    ok = True

    notes.append("size    %d bytes (%.1f%% of the %d B app region)"
                 % (size, 100.0 * size / APP_SIZE, APP_SIZE))
    notes.append("init SP 0x%08X" % sp)
    notes.append("reset   0x%08X" % reset)

    if size % 4:
        notes.append("FAIL size is not a multiple of 4")
        ok = False
    if not (SRAM_BASE <= sp <= SRAM_64K_TOP):
        notes.append("FAIL initial SP is outside SRAM 0x20000000..0x20010000")
        ok = False
    elif sp > SRAM_48K_TOP:
        notes.append("note  SP is above 48 KiB: image linked for 64 KiB SRAM "
                     "(typical of vendor stock images)")
    if not (APP_BASE <= reset < FLASH_BASE + FLASH_SIZE):
        notes.append("FAIL reset handler is outside the application region "
                     "0x08007000..0x08040000")
        ok = False
    if not reset & 1:
        notes.append("FAIL reset handler has the Thumb bit clear")
        ok = False

    return ok, notes


def main(argv):
    if len(argv) < 2:
        print("usage: check-vector-table.py <file.bin> [more.bin ...]", file=sys.stderr)
        return 2
    overall = 0
    for path in argv[1:]:
        ok, notes = check(path)
        print("%s %s" % ("OK  " if ok else "BAD ", path))
        for note in notes:
            print("    " + note)
        if not ok:
            overall = 1
    return overall


if __name__ == "__main__":
    sys.exit(main(sys.argv))
