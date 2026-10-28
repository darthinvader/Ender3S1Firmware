#!/usr/bin/env python3
"""Firmware versions: discover what mriscoc has published, fetch one, inspect it.

The pinned tree this repository ships is a single commit. This module lets the
configurator work with *any* published version instead of a hardcoded one:

  * list_versions()  - tags, branch heads and release dates from GitHub
  * fetch(version)   - shallow clone of exactly that ref into build/sources/
  * inspect(path)    - which catalogue features exist in that tree, and which
                       options it has that the pinned tree does not

Nothing here assumes a version number: the list comes from the remote, and the
feature scan reads the tree it just downloaded.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "build" / "sources"
CACHE = ROOT / "build" / "configurator" / "versions.json"
UPSTREAM = "mriscoc/Ender3V2S1"
UPSTREAM_URL = "https://github.com/mriscoc/Ender3V2S1.git"
TREE = ROOT / "build" / "Ender3V2S1"
CACHE_TTL = 3600
PINNED = "ffe684b68bc5ce7d273079df4da7730065277e70"


def run(argv, cwd=None, timeout=600, check=False):
    proc = subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError("%s failed: %s" % (" ".join(argv[:3]), (proc.stderr or proc.stdout)[:300]))
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _gh(path):
    rc, out = run(["gh", "api", path])
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def _remote_refs():
    rc, out = run(["git", "ls-remote", "--heads", "--tags", UPSTREAM_URL], timeout=120)
    refs = {}
    if rc != 0:
        return refs
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, name = parts
        refs[name] = sha
    return refs


def list_versions(refresh: bool = False) -> dict:
    """Every version worth offering, newest first, plus which ones are local."""
    if not refresh and CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text())
            if time.time() - cached.get("fetched_at", 0) < CACHE_TTL:
                return _with_local_state(cached)
        except Exception:
            pass

    versions = []
    tags = _gh("repos/%s/tags?per_page=100" % UPSTREAM) or []
    releases = {r.get("tag_name"): r for r in (_gh("repos/%s/releases?per_page=100" % UPSTREAM) or [])}
    for tag in tags:
        name = tag.get("name", "")
        commit = (tag.get("commit") or {})
        rel = releases.get(name) or {}
        versions.append({
            "id": "tag:" + name,
            "kind": "tag",
            "ref": name,
            "label": name,
            "sha": (commit.get("sha") or "")[:12],
            "date": (rel.get("published_at") or "")[:10],
            "assets": len(rel.get("assets") or []),
            "release": "https://github.com/%s/releases/tag/%s" % (UPSTREAM, name) if rel else "",
        })

    branches = _gh("repos/%s/branches?per_page=100" % UPSTREAM) or []
    for branch in branches:
        name = branch.get("name", "")
        sha = ((branch.get("commit") or {}).get("sha") or "")[:12]
        if not name:
            continue
        versions.append({
            "id": "branch:" + name,
            "kind": "branch",
            "ref": name,
            "label": name + ("  (newest code)" if "Bugfix" in name else ""),
            "sha": sha,
            "date": "",
            "assets": 0,
            "release": "",
        })

    if not versions:  # no gh, fall back to the refs themselves
        for name, sha in sorted(_remote_refs().items()):
            if name.startswith("refs/tags/"):
                tag = name[len("refs/tags/"):]
                versions.append({"id": "tag:" + tag, "kind": "tag", "ref": tag, "label": tag,
                                 "sha": sha[:12], "date": "", "assets": 0, "release": ""})
            elif name.startswith("refs/heads/"):
                br = name[len("refs/heads/"):]
                versions.append({"id": "branch:" + br, "kind": "branch", "ref": br, "label": br,
                                 "sha": sha[:12], "date": "", "assets": 0, "release": ""})

    tags = [v for v in versions if v["kind"] == "tag"]
    branches = [v for v in versions if v["kind"] == "branch"]
    tags.sort(key=lambda v: (v.get("date") or "", v["label"]), reverse=True)
    branches.sort(key=lambda v: (("Bugfix" not in v["ref"]), v["label"]))
    versions = tags + branches
    # the local pin is always offered, and is the default
    versions.insert(0, {
        "id": "pinned", "kind": "pinned", "ref": PINNED, "sha": PINNED[:12],
        "label": "Pinned (the build in this repository)",
        "date": "2026-06-05", "assets": 0, "release": "", "fetched": True,
        "path": str(TREE.relative_to(ROOT)),
    })
    payload = {"upstream": UPSTREAM, "url": UPSTREAM_URL, "pinned_commit": PINNED,
               "fetched_at": time.time(), "versions": versions}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(payload, indent=2) + chr(10))
    return _with_local_state(payload)


def _slug(version: dict) -> str:
    return (version["kind"] + "-" + version["ref"]).replace("/", "-")


def _with_local_state(payload: dict) -> dict:
    for v in payload.get("versions", []):
        if v.get("kind") == "pinned":
            v["fetched"] = (TREE / "Marlin" / "Configuration.h").exists()
            v["path"] = str(TREE.relative_to(ROOT)) if v["fetched"] else ""
            continue
        path = SOURCES / _slug(v)
        # a half-finished clone has .git but no checkout: only trust the file we need
        v["fetched"] = (path / "Marlin" / "Configuration.h").exists()
        v["path"] = str(path.relative_to(ROOT)) if v["fetched"] else ""
    return payload


def get(version_id: str) -> dict | None:
    for v in list_versions().get("versions", []):
        if v["id"] == version_id:
            return v
    return None


def fetch(version_id: str, log=print) -> dict:
    """Shallow-clone exactly this ref. Idempotent: an existing checkout is reused."""
    version = get(version_id)
    if version is None:
        raise RuntimeError("unknown version %r" % version_id)
    dest = SOURCES / _slug(version)
    if (dest / "Marlin" / "Configuration.h").exists():
        log("already fetched: %s" % dest.relative_to(ROOT))
        return {"id": version_id, "path": str(dest.relative_to(ROOT)), "sha": version["sha"], "reused": True}

    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    log("cloning %s at %s ..." % (version["ref"], version["kind"]))
    rc, out = run(["git", "clone", "--depth", "1", "--branch", version["ref"], UPSTREAM_URL, str(dest)], timeout=1800)
    if rc != 0 and version["kind"] == "tag":
        # some tags are annotated or not directly clonable: fetch then detach
        run(["git", "init", "-q", str(dest)], timeout=60)
        run(["git", "-C", str(dest), "remote", "add", "origin", UPSTREAM_URL], timeout=60)
        rc, out = run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin", version["ref"]], timeout=1800)
        if rc == 0:
            rc, out = run(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"], timeout=120)
    if rc != 0 or not (dest / "Marlin" / "Configuration.h").exists():
        raise RuntimeError("could not fetch %s: %s" % (version["ref"], out.strip()[-300:]))

    rc, head = run(["git", "-C", str(dest), "rev-parse", "--short", "HEAD"])
    info = {
        "id": version_id,
        "ref": version["ref"],
        "kind": version["kind"],
        "label": version["label"],
        "path": str(dest.relative_to(ROOT)),
        "sha": head.strip() if rc == 0 else version["sha"],
        "date": version.get("date", ""),
        "reused": False,
    }
    (dest / ".dsh-source.json").write_text(json.dumps(info, indent=2) + chr(10))
    log("checked out %s at %s" % (info["label"], info["sha"]))
    return info


PINNED_DEFINES = ROOT / "build" / "configurator" / "pinned-defines.json"


def pinned_defines() -> dict:
    """Defines in the pinned commit's own Configuration.h, straight from GitHub.

    The working tree under build/Ender3V2S1 has our configuration applied, so it
    cannot be used as a reference for what the pinned mriscoc release shipped.
    """
    if PINNED_DEFINES.exists():
        try:
            return json.loads(PINNED_DEFINES.read_text())
        except Exception:
            pass
    out = {}
    for name in ("Configuration.h", "Configuration_adv.h"):
        rc, body = run(["gh", "api", "repos/%s/contents/Marlin/%s?ref=%s"
                        % (UPSTREAM, name, PINNED), "--jq", ".content"], timeout=120)
        if rc != 0 or not body.strip():
            continue
        try:
            import base64
            text = base64.b64decode(body.strip()).decode("utf-8", "replace")
        except Exception:
            continue
        tmp = ROOT / "build" / "configurator" / ("pinned-" + name)
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(text)
        out.update(_defines_of(tmp))
    if out:
        PINNED_DEFINES.write_text(json.dumps(out, indent=0))
    return out


DEF_RE = __import__("re").compile(r"^[ \t]*(?://[ \t]*)?#define[ \t]+(?P<macro>[A-Z0-9_]+)")


def _defines_of(path: Path) -> dict:
    """#define NAME -> the nearest comment above it (best effort description)."""
    out = {}
    if not path.exists():
        return out
    comment = ""
    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        # a commented-out option IS an option this tree knows about, so match first
        match = DEF_RE.match(line)
        if match:
            out[match.group("macro")] = comment
            comment = ""
            continue
        if stripped.startswith("//"):
            comment = stripped.lstrip("/ ").strip()
        elif stripped:
            comment = ""
    return out


def inspect(path: Path, catalog: dict) -> dict:
    """What of the catalogue exists here, and what is new compared to the pin."""
    marlin = path / "Marlin"
    cfg = _defines_of(marlin / "Configuration.h")
    adv = _defines_of(marlin / "Configuration_adv.h")
    everything = dict(cfg)
    everything.update(adv)

    present, missing = [], []
    for feature in catalog.get("features", []):
        macros = [d["macro"] for d in feature.get("defines", [])] or [feature.get("macro", "")]
        macros = [m for m in macros if m]
        if macros and all(m in everything for m in macros):
            present.append(feature["id"])
        else:
            missing.append({"id": feature["id"], "label": feature["label"],
                            "macros": [m for m in macros if m not in everything]})

    known = set(pinned_defines())
    if not known:  # no network: fall back to the working tree
        known = set(_defines_of(TREE / "Marlin" / "Configuration.h")) | \
            set(_defines_of(TREE / "Marlin" / "Configuration_adv.h"))
    known |= {d["macro"] for f in catalog.get("features", []) for d in f.get("defines", [])}
    fresh = []
    for macro, comment in list(everything.items()):
        if macro in known or len(macro) < 6 or "_" not in macro:
            continue
        # tuning constants (numbers, sizes, pins) are not features
        if any(word in macro for word in ("_PIN", "_SIZE", "_COUNT", "_WIDTH", "_HEIGHT", "_X_", "_Y_", "_Z_", "_MM", "_MS", "_TEMP", "_TIME")):
            continue
        fresh.append({"macro": macro, "note": comment[:120]})
    fresh.sort(key=lambda f: f["macro"])

    try:
        rel = str(Path(path).resolve().relative_to(ROOT))
    except Exception:
        rel = str(path)
    return {
        "path": rel,
        "features_present": len(present),
        "features_total": len(catalog.get("features", [])),
        "features_missing": missing,
        "new_defines": fresh[:80],
        "new_define_count": len(fresh),
        "config_ok": (marlin / "Configuration.h").exists() and (marlin / "Configuration_adv.h").exists(),
    }


def _main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Firmware versions this configurator can build")
    ap.add_argument("--list", action="store_true", help="print the versions")
    ap.add_argument("--offline", action="store_true", help="use the cache only, never GitHub")
    ap.add_argument("--inspect", metavar="ID", help="inspect a downloaded version")
    args = ap.parse_args()
    if args.inspect:
        catalog = json.loads((ROOT / "tools" / "configurator" / "features.json").read_text())
        entry = get(args.inspect)
        if not entry or not entry.get("path"):
            print("%s is not downloaded" % args.inspect)
            return 1
        info = inspect(ROOT / entry["path"], catalog)
        print("%s: %d of %d catalogue features, %d options not in the pinned release"
              % (args.inspect, info["features_present"], info["features_total"],
                 info["new_define_count"]))
        return 0
    if not args.list:
        ap.print_help()
        return 0
    data = list_versions(refresh=False) if args.offline else list_versions()
    for v in data["versions"]:
        print("%-28s %-13s %-11s %s" % (v["id"], v.get("sha") or "-", v.get("date") or "-",
                                        "downloaded" if v.get("fetched") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
