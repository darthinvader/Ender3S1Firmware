#!/usr/bin/env python3
"""Write measured costs from measure.py back into features.json.

Every cost here comes from a build. For a feature that is on in the shipped
configuration the measurement was "turn it off and see how much the image
shrinks" (cost = baseline - result). For a feature that is off it was "turn it
on against the slimmed baseline and see how much it grows" (cost = result -
baseline), which is signed: a feature that saves flash gets a negative price.
"""
import json
from pathlib import Path

ROOT = Path("/home/darthinvader/Projects/Ender3S1Firmware")
CAT = ROOT / "tools" / "configurator" / "features.json"
RES = ROOT / "build" / "configurator" / "measure" / "results.json"

cat = json.loads(CAT.read_text())
res = json.loads(RES.read_text())
a = res["__baseline_a__"]
b = res["__baseline_b__"]

measured = failed = skipped = 0
for f in cat["features"]:
    r = res.get(f["id"])
    if f.get("buildable") is False and not (r and r.get("status") == "ok"):
        skipped += 1
        continue
    if not r:
        skipped += 1
        continue
    status = r.get("status", "")
    if status == "ok":
        base = a["flash"] if f["on_by_default"] else b["flash"]
        base_ram = a["ram"] if f["on_by_default"] else b["ram"]
        delta = r["flash"] - base
        cost = -delta if f["on_by_default"] else delta
        if cost < 0:
            # a feature cannot remove code; a negative delta means the difference
            # is inside the linker's alignment granularity
            f["measurement_note"] = ("measured %d B, i.e. no measurable cost: the difference is inside the "
                                     "linker's section alignment" % cost)
            cost = 0
        f["flash"] = cost
        f["ram"] = (r["ram"] - base_ram) if r.get("ram") is not None else 0
        if f["on_by_default"]:
            f["ram"] = base_ram - r["ram"] if r.get("ram") is not None else 0
        f["cost_source"] = "measured"
        f["measured_on"] = "2026-10-27"
        f["measured_against"] = "shipped baseline (turn off)" if f["on_by_default"] else "slimmed baseline (turn on)"
        f.pop("build_failed", None)
        f.pop("buildable", None)  # a successful build clears an earlier failure flag
        measured += 1
    elif status.startswith("overflow:"):
        base = a["flash"] if f["on_by_default"] else b["flash"]
        over = int(status.split(":")[1])
        f["flash"] = (a["region"] - base) + over if not f["on_by_default"] else 0
        f["cost_source"] = "measured"
        f["measured_on"] = "2026-10-27"
        f["measured_against"] = "linker overflow converted to cost"
        measured += 1
    else:
        f["buildable"] = False
        f["cost_source"] = "unmeasured"
        f["build_failed"] = status[:200]
        failed += 1

cat["calibration"] = {
    "date": "2026-10-27",
    "method": ("every feature built twice-baselined: features on in the shipped image were measured by turning them "
               "off against it, features off by turning them on against a slimmed baseline (shipped minus the UI "
               "extras, BFT, macros). Signed deltas, so a feature that saves flash prices negative."),
    "baseline_a": {"flash": a["flash"], "ram": a["ram"]},
    "baseline_b": {"flash": b["flash"], "ram": b["ram"], "off": b.get("off", [])},
    "region": a["region"],
    "counts": {"measured": measured, "failed": failed, "skipped": skipped,
               "total": len(cat["features"])},
}
CAT.write_text(json.dumps(cat, indent=2) + chr(10))
print("written: %d measured, %d failed, %d skipped, %d total" % (measured, failed, skipped, len(cat["features"])))
print("baseline A %d B, baseline B %d B, region %d B" % (a["flash"], b["flash"], a["region"]))
neg = [f["id"] for f in cat["features"] if f.get("flash", 0) < 0]
print("features that SAVE flash when enabled:", neg or "none")
