#!/usr/bin/env python3
"""Measure the flash and RAM cost of every feature in the catalogue.

One feature at a time, one real build each:

  * features that are ON in the shipped build are measured against that build,
    by turning them off and seeing how much the image shrinks
  * features that are OFF are measured against a slimmed baseline that frees
    room, by turning them on and seeing how much the image grows

A link that overflows is still a measurement: the linker states how many bytes
over it went, and that is the cost. Nothing here is estimated.

Usage:
  measure.py [--only id,id,...] [--resume]

Writes build/configurator/measure/results.json (and a .jsonl per build) so an
interrupted run can be resumed.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/darthinvader/Projects/Ender3S1Firmware")
CATALOG = ROOT / "tools" / "configurator" / "features.json"
TREE = ROOT / "build" / "Ender3V2S1"
PIO = ROOT / "build" / ".venv" / "bin" / "platformio"
APPLY = ROOT / "tools" / "configurator" / "apply_features.py"
CONFIG = ROOT / "configs" / "Ender3S1-F1-v2"
OUT = ROOT / "build" / "configurator" / "measure"

FLASH_RE = re.compile(r"Flash:\s*\[[^\]]*\]\s*([\d.]+)% \(used (\d+) bytes from (\d+) bytes\)")
RAM_RE = re.compile(r"RAM:\s*\[[^\]]*\]\s*([\d.]+)% \(used (\d+) bytes from (\d+) bytes\)")
OVER_RE = re.compile(r"region .FLASH. overflowed by (\d+) bytes")

# Turning these off frees enough room to measure the features that are off by
# default. They are measured themselves, against the full baseline.
SLIM = ["ui_gcode_preview", "ui_toolbar", "ui_colors", "ui_plot", "ui_esdiag",
        "ui_lockscreen", "gcode_macros", "bft"]


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def run(sel, tag):
    """Apply a selection and build it. Returns (flash, ram, region, status)."""
    sel_path = OUT / ("sel-%s.json" % tag)
    sel_path.write_text(json.dumps(sel, indent=2))
    meta = OUT / ("meta-%s.json" % tag)
    rc = subprocess.run([sys.executable, str(APPLY), "--catalog", str(CATALOG),
                         "--tree", str(TREE), "--config-dir", str(CONFIG),
                         "--selection", "@" + str(sel_path), "--out", str(meta)],
                        capture_output=True, text=True)
    if rc.returncode != 0:
        return None, None, None, "apply-failed: " + (rc.stderr.strip().splitlines() or [""])[-1][:120]

    proc = subprocess.run([str(PIO), "run", "-e", "STM32F103RC_creality"], cwd=str(TREE),
                          capture_output=True, text=True, timeout=600)
    out = proc.stdout + proc.stderr
    (OUT / ("build-%s.log" % tag)).write_text(out)
    flash = FLASH_RE.search(out)
    ram = RAM_RE.search(out)
    if flash:
        return (int(flash.group(2)), int(ram.group(2)) if ram else None,
                int(flash.group(3)), "ok")
    over = OVER_RE.search(out)
    if over:
        return None, None, None, "overflow:%s" % over.group(1)
    tail = [l for l in out.splitlines() if "error:" in l.lower()][:1]
    return None, None, None, "build-failed: " + (tail[0][:160] if tail else "unknown")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(CATALOG.read_text())
    feats = catalog["features"]
    results_path = OUT / "results.json"
    results = json.loads(results_path.read_text()) if (args.resume and results_path.exists()) else {}

    wanted = [x for x in args.only.split(",") if x] or [f["id"] for f in feats]

    log("baseline A: shipped configuration")
    a_flash, a_ram, region, a_status = run({"machine": "ender3s1-f103"}, "baseline-a")
    if a_flash is None:
        log("baseline A failed: " + a_status)
        return 1
    log("  A = %d B flash, %s B ram" % (a_flash, a_ram))
    results["__baseline_a__"] = {"flash": a_flash, "ram": a_ram, "region": region}

    log("baseline B: shipped minus the slimming set")
    slim_sel = {"machine": "ender3s1-f103", "off": SLIM}
    b_flash, b_ram, _, b_status = run(slim_sel, "baseline-b")
    if b_flash is None:
        log("baseline B failed: " + b_status)
        return 1
    log("  B = %d B flash, %s B ram (free %d)" % (b_flash, b_ram, region - b_flash))
    results["__baseline_b__"] = {"flash": b_flash, "ram": b_ram, "region": region, "off": SLIM}

    for i, f in enumerate(feats, 1):
        fid = f["id"]
        if fid not in wanted:
            continue
        if args.resume and fid in results and results[fid].get("status", "").startswith("ok"):
            log("%2d/%d %-32s cached" % (i, len(feats), fid))
            continue
        if f["on_by_default"]:
            sel = {"machine": "ender3s1-f103", "off": [fid]}
            base, base_ram = a_flash, a_ram
        else:
            sel = dict(slim_sel)
            sel["on"] = [fid]
            base, base_ram = b_flash, b_ram

        flash, ram, reg, status = run(sel, fid)
        entry = {"status": status, "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if status == "ok":
            entry.update(flash=flash, ram=ram, cost=abs(flash - base),
                         ram_cost=(abs(ram - base_ram) if ram is not None else None),
                         baseline="A" if f["on_by_default"] else "B")
        elif status.startswith("overflow:"):
            over = int(status.split(":")[1])
            cost = (reg - base) + over
            entry.update(cost=cost, overflow=over, baseline="A" if f["on_by_default"] else "B",
                         note="linker overflow converted to cost")
        results[fid] = entry
        results_path.write_text(json.dumps(results, indent=2) + chr(10))
        (OUT / "results.jsonl").open("a").write(json.dumps({"id": fid, **entry}) + chr(10))
        log("%2d/%d %-32s %-8s cost=%s" % (i, len(feats), fid, status,
                                           entry.get("cost", "-")))

    ok = sum(1 for k, v in results.items() if not k.startswith("__") and v.get("status") == "ok")
    log("done: %d measured cleanly, %d recorded overall" % (ok, len(results) - 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
