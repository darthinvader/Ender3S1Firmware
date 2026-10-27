#!/usr/bin/env python3
"""Generate the SVG diagrams used by the documentation.

Everything here is computed from constants that also appear in the docs, so
the pictures cannot drift from the numbers. Re-run after changing a size:

    python3 tools/make-diagrams.py

Outputs:
    docs/img/memory-map.svg       flash and RAM budget of the current build
    docs/img/build-pipeline.svg   how a committed configuration becomes a flashed printer

Colours are chosen to read on both GitHub themes; every diagram carries its
own light background card.
"""
from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "docs", "img")

# --- constants that must match the documentation -----------------------
FLASH_TOTAL = 256 * 1024
BOOTLOADER = 28 * 1024
APP_USED = 232344
APP_REGION = 233472
RAM_TOTAL = 49152
RAM_USED = 28064

INK = "#1f2328"
MUTED = "#59636e"
CARD = "#ffffff"
BORDER = "#d1d9e0"
BOOT = "#8c959f"
APP = "#2da44e"
FREE = "#cf222e"
RAMC = "#0969da"
RAMFREE = "#eef2f6"


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_open(width, height):
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif">'
        % (width, height, width, height),
        '<rect x="0" y="0" width="%d" height="%d" rx="10" fill="%s" stroke="%s"/>'
        % (width, height, CARD, BORDER),
    ]


def text(x, y, value, size=13, weight="400", fill=None, anchor="start"):
    return ('<text x="%d" y="%d" font-size="%d" font-weight="%s" fill="%s" '
            'text-anchor="%s">%s</text>'
            % (x, y, size, weight, fill or INK, anchor, esc(value)))


def rect(x, y, w, h, fill, stroke="none", rx=3):
    return ('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="%d" fill="%s" stroke="%s"/>'
            % (x, y, w, h, rx, fill, stroke))


def line(x1, y1, x2, y2, stroke=None, width=1, dash=None):
    extra = ' stroke-dasharray="%s"' % dash if dash else ""
    return ('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
            'stroke-width="%d"%s/>' % (x1, y1, x2, y2, stroke or BORDER, width, extra))


def memory_map():
    width, height = 900, 430
    out = svg_open(width, height)
    out.append(text(36, 42, "STM32F103RCT6 on the shipped build", 19, "600"))
    out.append(text(36, 64, "256 KiB flash, 28 KiB of it reserved for the SD bootloader", 13, "400", MUTED))

    x0, bar_w = 150, 700

    # ---- flash row ----------------------------------------------------
    fy, fh = 120, 56
    scale = bar_w / float(FLASH_TOTAL)
    boot_w = BOOTLOADER * scale
    app_w = APP_USED * scale
    free_w = max(3.0, (APP_REGION - APP_USED) * scale)
    unused_w = (FLASH_TOTAL - BOOTLOADER - APP_REGION) * scale

    out.append(text(36, fy + 34, "FLASH", 13, "700", MUTED))
    out.append(rect(x0, fy, boot_w, fh, BOOT))
    out.append(rect(x0 + boot_w, fy, app_w, fh, APP))
    out.append(rect(x0 + boot_w + app_w, fy, free_w, fh, FREE))
    if unused_w > 1:
        out.append(rect(x0 + boot_w + app_w + free_w, fy, unused_w, fh, RAMFREE))

    out.append(text(x0 + boot_w / 2, fy + 25, "28 KiB", 12, "700", "#ffffff", "middle"))
    out.append(text(x0 + boot_w / 2, fy + 41, "bootloader", 10, "400", "#ffffff", "middle"))
    out.append(text(x0 + boot_w + app_w / 2, fy + 34,
                    "application 232,344 B  ·  99.5 %", 13, "600", "#ffffff", "middle"))

    # the 1,128 B sliver is ~3 px wide, so it gets a labelled arrow above the bar
    out.append(text(x0 + bar_w, fy - 34, "1,128 B free", 13, "700", FREE, "end"))
    out.append(text(x0 + bar_w, fy - 19, "the entire remaining budget", 10, "400", MUTED, "end"))
    out.append('<path d="M%d,%d L%d,%d" stroke="%s" stroke-width="1.2" '
               'stroke-dasharray="3,3"/>'
               % (x0 + bar_w - 96, fy - 14, x0 + bar_w - 6, fy + 4, FREE))

    # boundary ticks; only the two end addresses are labelled
    out.append(line(x0, fy - 8, x0, fy + fh + 30))
    out.append(line(x0 + boot_w, fy - 8, x0 + boot_w, fy + fh + 30, BORDER, 1, "4,3"))
    out.append(line(x0 + bar_w, fy - 8, x0 + bar_w, fy + fh + 30))
    out.append(text(x0, fy + fh + 44, "0x08000000", 11, "400", MUTED))
    out.append(text(x0 + bar_w, fy + fh + 44, "0x08040000", 11, "400", MUTED, "end"))

    # ---- RAM row ------------------------------------------------------
    ry, rh = 262, 46
    rscale = bar_w / float(RAM_TOTAL)
    used_w = RAM_USED * rscale
    out.append(text(36, ry + 28, "RAM", 13, "700", MUTED))
    out.append(rect(x0, ry, used_w, rh, RAMC))
    out.append(rect(x0 + used_w, ry, bar_w - used_w, rh, RAMFREE))
    out.append(text(x0 + used_w / 2, ry + 28, "28,064 B  ·  57.1 %", 13, "600", "#ffffff", "middle"))
    out.append(text(x0 + used_w + (bar_w - used_w) / 2, ry + 28,
                    "21,088 B free", 12, "500", MUTED, "middle"))
    out.append(text(x0, ry + rh + 20, "0x20000000", 11, "400", MUTED))
    out.append(text(x0 + bar_w, ry + rh + 20, "0x2000C000", 11, "400", MUTED, "end"))

    # ---- legend -------------------------------------------------------
    ly = 366
    items = [
        (BOOT, "bootloader, 28 KiB"),
        (APP, "application, 232,344 B of 233,472 B"),
        (FREE, "1,128 B unallocated"),
        (RAMC, "RAM in use, 57.1 %"),
    ]
    lx = x0 - 30
    for colour, label in items:
        out.append(rect(lx, ly - 9, 12, 12, colour))
        out.append(text(lx + 20, ly + 1, label, 12, "400", MUTED))
        lx += 28 + int(6.6 * len(label))

    out.append(text(36, height - 18,
                    "Application region 0x08007000-0x08040000. Every added feature has to be paid for by removing another.",
                    11, "400", MUTED))
    out.append("</svg>")
    return "\n".join(out)


def pipeline():
    width, height = 940, 250
    out = svg_open(width, height)
    out.append(text(30, 40, "From committed configuration to a flashed printer", 19, "600"))
    out.append(text(30, 62, "Every step is a script in this repository, and every artifact is checksummed", 13, "400", MUTED))

    boxes = [
        ("pinned upstream", "mriscoc Ender3V2S1\n@ ffe684b", "#0969da"),
        ("configs/ + patch", "variant folder +\nICON_ShapingZ fix", "#8250df"),
        ("PlatformIO 6.1.19", "env STM32F103RC\n_creality", "#bf3989"),
        ("firmware/*.bin", "232,344 B\n99.5 % of region", "#2da44e"),
        ("SD card", "MBR FAT32 4K\nunique 8.3 name", "#bc4c00"),
        ("printer", "M115 reports\nEnder3S1-F1-v2", "#1f2328"),
    ]
    bw, bh, gap = 128, 84, 20
    x = 30
    y = 100
    for i, (title, sub, colour) in enumerate(boxes):
        out.append(rect(x, y, bw, bh, "#f6f8fa", BORDER, 8))
        out.append(rect(x, y, 4, bh, colour, "none", 2))
        out.append(text(x + 14, y + 26, title, 13, "700", INK))
        for j, part in enumerate(sub.split("\n")):
            out.append(text(x + 14, y + 46 + j * 15, part, 11, "400", MUTED))
        if i < len(boxes) - 1:
            ax1 = x + bw + 3
            ax2 = x + bw + gap - 3
            ay = y + bh / 2
            out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1.6"/>'
                       % (ax1, ay, ax2, ay, BORDER))
            out.append('<path d="M%d,%d l-6,-4 l0,8 z" fill="%s"/>' % (ax2, ay, BORDER))
        x += bw + gap

    out.append(text(30, 224,
                    "scripts/bootstrap.sh  ->  scripts/build.sh  ->  scripts/verify-artifacts.sh  ->  scripts/flash-card.sh",
                    12, "500", MUTED))
    out.append("</svg>")
    return "\n".join(out)


def main():
    os.makedirs(OUT, exist_ok=True)
    targets = {"memory-map.svg": memory_map(), "build-pipeline.svg": pipeline()}
    for name, body in targets.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(body + "\n")
        print("wrote docs/img/" + name, len(body), "bytes")


if __name__ == "__main__":
    main()
