#!/usr/bin/env python3
"""Static checks on the catalogue, before anything is compiled.

Catches the two failure modes that cost real time in this project:

  * a define that does not exist in the configuration file (the flip would
    silently do nothing)
  * on_by_default disagreeing with what the file actually says, so the UI would
    lie about what the shipped build contains

Also checks that ids are unique, that the groups are declared, and that the
measured/predicted fields are present.

Exit status 0 = consistent, 1 = problems (printed).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAT = ROOT / "tools" / "configurator" / "features.json"
CFG = ROOT / "configs" / "Ender3S1-F1-v2"
DEF_RE = re.compile(r"^(?P<i>[ \t]*)(?P<c>//[ \t]*)?#define[ \t]+(?P<m>[A-Z0-9_]+)(?P<tail>.*)$")


def definitions(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        m = DEF_RE.match(line)
        if m:
            out.setdefault(m.group("m"), []).append(not m.group("c"))
    return out


def main() -> int:
    cat = json.loads(CAT.read_text())
    problems = []
    ids = [f["id"] for f in cat["features"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate feature ids: %s" % sorted(i for i in set(ids) if ids.count(i) > 1))

    known_groups = set(cat["groups"])
    defs = {name: definitions(CFG / name) for name in ("Configuration.h", "Configuration_adv.h")}

    for f in cat["features"]:
        if f["group"] not in known_groups:
            problems.append("%s: unknown group %r" % (f["id"], f["group"]))
        for key in ("flash", "ram", "cost_source"):
            if key not in f:
                problems.append("%s: missing %s" % (f["id"], key))
        for d in f["defines"]:
            table = defs.get(d["file"])
            if table is None:
                problems.append("%s: unknown file %s" % (f["id"], d["file"]))
                continue
            hits = table.get(d["macro"], [])
            if not hits:
                problems.append("%s: %s has no #define %s" % (f["id"], d["file"], d["macro"]))
            elif len(hits) > 1:
                problems.append("%s: %s defines %s %d times - the flip would be ambiguous"
                                % (f["id"], d["file"], d["macro"], len(hits)))
            else:
                want_on = f["on_by_default"] if d["on_enabled"] else (not f["on_by_default"])
                if hits[0] != want_on:
                    problems.append("%s: catalogue says on_by_default=%s but %s is %s in the file"
                                    % (f["id"], f["on_by_default"], d["macro"],
                                       "on" if hits[0] else "off"))

    # conflicts must be symmetric and must name real features
    idset = set(ids)
    for f in cat["features"]:
        for other in f.get("conflicts", []):
            if other not in idset:
                problems.append("%s: conflict with unknown feature %r" % (f["id"], other))
            elif f["id"] not in cat["features"][ids.index(other)].get("conflicts", []):
                problems.append("%s: conflict with %s is not declared both ways" % (f["id"], other))

    # dependency the build system enforces: EXTRA_PROBING must be 1 when MULTIPLE_PROBING > 0
    prob = next((f for f in cat["features"] if f["id"] == "probing_avg"), None)
    if prob:
        macros = {d["macro"] for d in prob["defines"]}
        if macros != {"MULTIPLE_PROBING", "EXTRA_PROBING"}:
            problems.append("probing_avg must flip MULTIPLE_PROBING and EXTRA_PROBING together")

    print("catalogue: %d features, %d groups" % (len(cat["features"]), len(cat["groups"])))
    measured = sum(1 for f in cat["features"] if f.get("cost_source") == "measured")
    print("costs measured: %d, unmeasured: %d" % (measured, len(cat["features"]) - measured))
    if problems:
        print("\n%d problem(s):" % len(problems))
        for p in problems:
            print("  -", p)
        return 1
    print("no inconsistencies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
