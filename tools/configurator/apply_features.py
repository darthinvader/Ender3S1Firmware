#!/usr/bin/env python3
"""Apply a feature selection to a Marlin tree.

This is the part of the configurator that has to be right, so it is a separate,
testable program with no web server attached.

What it does, in order:

  1. copies the baseline configuration (configs/Ender3S1-F1-v2) into the tree
  2. flips every #define the selection asks for
  3. re-reads the files and asserts that every flip actually landed
     (a silent no-op here is the failure mode this project already paid for once)
  4. stamps the image with a distinct machine name so M115 identifies it
  5. predicts the flash/RAM cost from the catalogue and refuses an over-budget
     selection before a compiler is ever started
  6. writes a manifest describing exactly what was built

Usage:
  apply_features.py --catalog tools/configurator/features.json \
                    --tree build/Ender3V2S1 \
                    --selection '{"machine":"ender3s1-f103","off":["ui_colors"]}' \
                    --out build/configurator/last/meta.json
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEF_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<comment>//[ \t]*)?#define[ \t]+(?P<macro>[A-Z0-9_]+)(?P<tail>.*)$")
MACHINE_NAME = "Ender3S1-CFG"


def die(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print("apply_features: " + msg, file=sys.stderr)
    raise SystemExit(2)


def define_state(path: Path, macro: str):
    """Return ('on'|'off'|None, line_index) for the first definition of macro."""
    for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        m = DEF_RE.match(line)
        if m and m.group("macro") == macro:
            return ("off" if m.group("comment") else "on"), idx
    return None, -1


def set_define(path: Path, macro: str, enabled: bool, value=None) -> int:
    """Rewrite every definition of macro to the requested state. Returns the count."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(True)
    hits = 0
    for i, raw in enumerate(lines):
        m = DEF_RE.match(raw.rstrip(chr(10)))
        if not m or m.group("macro") != macro:
            continue
        hits += 1
        tail = m.group("tail")
        if value is not None:
            tail = " " + value
        lines[i] = m.group("indent") + ("" if enabled else "//") + "#define " + macro + tail + chr(10)
    if hits == 0:
        die("macro %s not found in %s" % (macro, path.name))
    path.write_text("".join(lines), encoding="utf-8")
    return hits


def apply_patch(tree: Path, patch: Path, marker: str) -> str:
    """Keep the upstream source fix present, without assuming who applied it.

    git resolves a patch path relative to -C, so the path is made absolute;
    the marker check is the fallback for a tree whose git state is unclear.
    """
    patch = patch.resolve()
    if not patch.exists():
        return "missing"
    if subprocess.run(["git", "-C", str(tree), "apply", "--reverse", "--check", str(patch)],
                      capture_output=True).returncode == 0:
        return "already applied"
    if subprocess.run(["git", "-C", str(tree), "apply", "--check", str(patch)],
                      capture_output=True).returncode != 0:
        target = tree / "Marlin/src/lcd/dwin/proui/dwinui.h"
        if target.exists() and marker in target.read_text(errors="replace"):
            return "already applied (marker present)"
        return "does not apply"
    subprocess.run(["git", "-C", str(tree), "apply", str(patch)], check=True)
    return "applied"


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--config-dir", required=True)
    ap.add_argument("--selection", required=True, help="JSON string or @path")
    ap.add_argument("--out", required=True)
    ap.add_argument("--patch", default="configs/patches/0002-proui-add-ICON_ShapingZ.patch")
    ap.add_argument("--allow-overflow", action="store_true",
                    help="build even if the predicted image exceeds the region: the linker decides")
    ap.add_argument("--tolerant", action="store_true",
                    help="skip defines this firmware version does not have instead of failing")
    ap.add_argument("--no-predict", action="store_true",
                    help="the costs were measured on the pinned tree, so do not claim a prediction")
    ap.add_argument("--mesh", type=int, default=None,
                    help="default bed mesh size per axis; the bounds come from the catalogue's mesh section")
    ap.add_argument("--source-label", default="pinned",
                    help="which firmware version this build is from, recorded in the manifest")
    args = ap.parse_args(argv[1:])

    catalog = json.loads(Path(args.catalog).read_text())
    raw = args.selection
    sel = json.loads(Path(raw[1:]).read_text() if raw.startswith("@") else raw)

    machine_id = sel.get("machine", "ender3s1-f103")
    machine = next((m for m in catalog["machines"] if m["id"] == machine_id), None)
    if machine is None:
        die("unknown machine %s" % machine_id)
    if not machine.get("supported"):
        die("%s is not supported by this builder: %s" % (machine["label"], machine.get("reason", "")))

    tree = Path(args.tree)
    marlin = tree / "Marlin"
    if not (marlin / "Configuration.h").exists():
        die("no Marlin tree at %s" % marlin)

    features = {f["id"]: f for f in catalog["features"]}
    default_on = {fid: bool(f["on_by_default"]) for fid, f in features.items()}

    # 1. baseline configuration
    cfg_dir = Path(args.config_dir)
    for name in ("Configuration.h", "Configuration_adv.h", "Version.h"):
        shutil.copyfile(cfg_dir / name, marlin / name)

    # 2. desired state
    overrides = {}
    for fid in sel.get("on", []):
        if fid not in features:
            die("unknown feature in 'on': %s" % fid)
        overrides[fid] = True
    for fid in sel.get("off", []):
        if fid not in features:
            die("unknown feature in 'off': %s" % fid)
        overrides[fid] = False
    state = dict(default_on)
    state.update(overrides)

    # 2a. resolve dependencies: pull prerequisites in, drop dependents out
    auto_added, auto_removed = [], []
    changed = True
    while changed:
        changed = False
        for fid, want in list(state.items()):
            if not want:
                continue
            for req in features[fid].get("requires", []):
                if not state.get(req):
                    state[req] = True
                    auto_added.append({"feature": req, "because": fid})
                    changed = True
        for fid, want in list(state.items()):
            if want:
                continue
            for other, ofeat in features.items():
                if state.get(other) and fid in ofeat.get("requires", []):
                    state[other] = False
                    auto_removed.append({"feature": other, "because": fid})
                    changed = True

    # 2b. declared conflicts: the explicit choice wins, an ambiguity is refused
    explicit_on = set(sel.get("on", []))
    for fid, want in list(state.items()):
        if not want:
            continue
        for other in features[fid].get("conflicts", []):
            if not state.get(other):
                continue
            if fid in explicit_on and other in explicit_on:
                die("%s and %s were both requested, and they are mutually exclusive" % (fid, other))
            state[other] = False
            auto_removed.append({"feature": other, "because": fid})

    # a conflict removal can orphan a dependent, so resolve requires once more
    changed = True
    while changed:
        changed = False
        for fid, want in list(state.items()):
            if want:
                continue
            for other, ofeat in features.items():
                if state.get(other) and fid in ofeat.get("requires", []):
                    state[other] = False
                    auto_removed.append({"feature": other, "because": fid})
                    changed = True

    # 3. flip and verify
    applied = []
    skipped = []
    for fid, feat in features.items():
        want = state[fid]
        if want == default_on[fid]:
            continue
        for d in feat["defines"]:
            target = marlin / d["file"]
            present, _ = define_state(target, d["macro"])
            if present is None:
                if args.tolerant:
                    skipped.append({"feature": fid, "macro": d["macro"], "file": d["file"]})
                    continue
                die("macro %s is not in %s (use --tolerant for other firmware versions)"
                    % (d["macro"], d["file"]))
            flip_on = d["on_enabled"] if want else (not d["on_enabled"])
            set_define(target, d["macro"], flip_on, d.get("value") if flip_on else None)
            got, _ = define_state(target, d["macro"])
            expected = "on" if flip_on else "off"
            if got != expected:
                die("verification failed: %s in %s is %r, expected %r" % (d["macro"], d["file"], got, expected))
            applied.append({"feature": fid, "file": d["file"], "macro": d["macro"], "state": got})

    # 4. identifiable machine name
    name_re = re.compile(r'^(?P<i>[ \t]*)#define[ \t]+CUSTOM_MACHINE_NAME[ \t]+"(?P<v>[^"]*)"', re.M)
    text = (marlin / "Configuration.h").read_text()
    text, n = name_re.subn('#define CUSTOM_MACHINE_NAME "%s"' % MACHINE_NAME, text, count=1)
    if n != 1:
        die("could not stamp CUSTOM_MACHINE_NAME")
    (marlin / "Configuration.h").write_text(text)

    # M115 gets its identity from DETAILED_BUILD_VERSION, not from CUSTOM_MACHINE_NAME,
    # so Version.h is stamped too. The DEMO line above it must not be touched.
    vlines = (marlin / "Version.h").read_text().splitlines(True)
    stamped = 0
    for i, line in enumerate(vlines):
        if "DEMO" in line:
            continue
        if "DETAILED_BUILD_VERSION" in line and "SHORT_BUILD_VERSION" in line:
            vlines[i] = re.sub(r'"[^"]*"', '" %s"' % MACHINE_NAME, line)
            stamped += 1
    if stamped != 1:
        die("could not stamp DETAILED_BUILD_VERSION in Version.h (found %d)" % stamped)
    (marlin / "Version.h").write_text("".join(vlines))

    # 5. budget
    base = catalog["baseline"]
    pred_flash = base["flash"] + base.get("stamp_offset", 0)
    pred_ram = base["ram"]
    for fid, want in state.items():
        if want == default_on[fid]:
            continue
        sign = 1 if want else -1
        pred_flash += sign * features[fid]["flash"]
        pred_ram += sign * features[fid]["ram"]
    added = [fid for fid, want in state.items() if want and not default_on[fid]]
    margin = base.get("add_margin_per_feature", 0) * len(added)
    pred_flash += margin
    region = machine["flash_region"]
    if args.no_predict:
        pred_flash = None
        pred_ram = None
    over = (pred_flash - region) if pred_flash is not None else 0
    if over > 0 and not args.allow_overflow:
        die("selection is %.0f bytes over the %d byte application region "
            "(re-run with --allow-overflow to let the linker decide)" % (over, region))

    patch_result = apply_patch(tree, Path(args.patch), "ICON_ShapingZ")

    # 5b. default bed mesh size (the probed size itself stays a screen setting)
    mesh_info = None
    if args.mesh is not None:
        catalog_full = json.loads(Path(args.catalog).read_text())
        spec = catalog_full.get("mesh") or {}
        lo = int(spec.get("min", 3))
        hi = int(spec.get("max", 5))
        if not (lo <= args.mesh <= hi):
            die("mesh size %d is outside %d..%d. %s"
                % (args.mesh, lo, hi, spec.get("matrix_note", "")))
        hits = set_define(marlin / "Configuration.h", spec.get("define", "GRID_MAX_POINTS_X"),
                          True, str(args.mesh))
        mesh_info = {
            "size": args.mesh,
            "define": spec.get("define", "GRID_MAX_POINTS_X"),
            "definitions_rewritten": hits,
            "matrix_limit": spec.get("library_limit"),
            "note": "default size for a fresh EEPROM; the probed size is chosen on the screen",
        }

    # 6. manifest
    meta = {
        "machine": machine_id,
        "machine_label": machine["label"],
        "config_dir": args.config_dir,
        "machine_name_stamped": MACHINE_NAME,
        "upstream": base["upstream"],
        "selection": {fid: state[fid] for fid in sorted(features)},
        "changed": applied,
        "predicted": {"flash": pred_flash, "ram": pred_ram, "region": region,
                      "flash_free": (region - pred_flash) if pred_flash is not None else None,
                      "measured_baseline": not args.no_predict,
                      "over_budget": over > 0, "over_by": max(0, over)},
        "source_patch": patch_result,
        "auto_added": auto_added,
        "auto_removed": auto_removed,
        "source": args.source_label,
        "skipped": skipped,
        "mesh": mesh_info,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(meta, indent=2) + chr(10))
    print(json.dumps({k: meta[k] for k in ("predicted", "source_patch")}, indent=2))
    print("applied %d define flips, manifest %s" % (len(applied), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
