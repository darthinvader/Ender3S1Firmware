#!/usr/bin/env python3
"""Static checks on the workflows, before GitHub rejects them.

A GitHub expression written with one brace ($ { x } instead of $ {{ x }}) is
passed through as literal text: the job runs, the value is the string
"$ { inputs.mesh }", and the failure appears far away. This catches that class
of mistake, plus reusable-workflow references that do not exist.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
DOLLAR = chr(36)

def main() -> int:
    problems = []
    for path in sorted(WF.glob("*.yml")):
        text = path.read_text()
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if DOLLAR + "{{" in line:
                # every opened expression must close
                if line.count(DOLLAR + "{{") != line.count("}}"):
                    problems.append("%s:%d unclosed expression: %s" % (path.name, number, stripped))
                continue
            if re.search(re.escape(DOLLAR) + r"\{(?!\{)", line):
                problems.append("%s:%d single-brace expression (should be double): %s"
                                % (path.name, number, stripped))
        for used in re.findall(r"uses:\s*\./\.github/workflows/([\w.-]+)", text):
            if not (WF / used).exists():
                problems.append("%s calls a workflow that does not exist: %s" % (path.name, used))

    print("workflows: %d files" % len(list(WF.glob("*.yml"))))
    if problems:
        print("\n%d problem(s):" % len(problems))
        for item in problems:
            print("  -", item)
        return 1
    print("no workflow problems")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

