#!/usr/bin/env python3
"""HTTP service for the Ender 3 S1 firmware configurator.

Endpoints
  GET  /                          the picker page
  GET  /static/<file>             page assets
  GET  /api/catalog               feature catalogue + build-tree status
  POST /api/build                 {"machine": "...", "on": [...], "off": [...]} -> job id
  GET  /api/build/<id>            status, log tail, predicted vs measured result
  GET  /api/build/<id>/firmware.bin
  GET  /api/build/<id>/manifest.json
  GET  /api/builds                recent jobs

One build runs at a time: PlatformIO owns the whole tree, and two concurrent
compiles in the same tree would corrupt it. Jobs queue.

Binds to 127.0.0.1 by default. This service runs a compiler; do not expose it
to a network you do not control.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.configurator import writer, sources  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "tools" / "configurator" / "features.json"
WEB = ROOT / "tools" / "configurator" / "web"
TREE = ROOT / "build" / "Ender3V2S1"
PIO = ROOT / "build" / ".venv" / "bin" / "platformio"
JOBS = ROOT / "build" / "configurator" / "jobs"
APPLY = ROOT / "tools" / "configurator" / "apply_features.py"

FLASH_RE = re.compile(r"Flash:\s*\[[^\]]*\]\s*([\d.]+)% \(used (\d+) bytes from (\d+) bytes\)")
RAM_RE = re.compile(r"RAM:\s*\[[^\]]*\]\s*([\d.]+)% \(used (\d+) bytes from (\d+) bytes\)")

lock = threading.Lock()
work = queue.Queue()
jobs = {}


def now() -> float:
    return time.time()


def tree_ready() -> dict:
    return {
        "tree": TREE.exists(),
        "platformio": PIO.exists(),
        "toolchain_ready": TREE.exists() and PIO.exists(),
        "hint": "" if (TREE.exists() and PIO.exists())
                else "run ./scripts/bootstrap.sh once; the configurator reuses that tree",
    }


def log_line(job, text):
    stamp = time.strftime("%H:%M:%S")
    with lock:
        job["log"].append("[%s] %s" % (stamp, text.rstrip()))
        if len(job["log"]) > 500:
            del job["log"][:-500]


def run_streaming(job, argv, cwd):
    log_line(job, "$ " + " ".join(str(a) for a in argv))
    proc = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        log_line(job, line.rstrip())
    proc.wait()
    return proc.returncode


def resolve_source(source_id):
    """Map a version id to (tree, label, tolerant, measured_baseline)."""
    if not source_id or source_id == "pinned":
        return TREE, "pinned", False, True
    entry = sources.get(source_id)
    if entry is None:
        raise RuntimeError("unknown firmware version %r" % source_id)
    if not entry.get("path"):
        raise RuntimeError("%s has not been downloaded yet" % entry.get("label", source_id))
    path = ROOT / entry["path"]
    if not (path / "Marlin" / "Configuration.h").exists():
        raise RuntimeError("%s is incomplete on disk" % entry.get("label", source_id))
    return path, entry.get("label", source_id), True, False


def fetch_job(job):
    """Download one firmware version."""
    jobdir = JOBS / job["id"]
    jobdir.mkdir(parents=True, exist_ok=True)

    def log(msg):
        log_line(job, msg)

    with lock:
        job.update(status="running", phase="downloading", started=now())
    try:
        info = sources.fetch(job["source"], log=log)
    except Exception as exc:
        with lock:
            job.update(status="failed", phase="download failed", error=str(exc)[:300], finished=now())
        return
    catalog = json.loads(CATALOG.read_text())
    try:
        inspection = sources.inspect(ROOT / info["path"], catalog)
    except Exception as exc:
        inspection = {"error": str(exc)[:200]}
    log("catalogue features present: %d of %d" % (inspection.get("features_present", 0),
                                                   inspection.get("features_total", 0)))
    log("defines this version has that the pinned tree does not: %d" % inspection.get("new_define_count", 0))
    with lock:
        job.update(status="succeeded", phase="downloaded", finished=now(),
                   result={"source": info, "inspection": inspection})


def build_job(job):
    jobdir = JOBS / job["id"]
    jobdir.mkdir(parents=True, exist_ok=True)
    ready = tree_ready()
    if not ready["toolchain_ready"]:
        with lock:
            job.update(status="failed", phase="no build tree", error=ready["hint"], finished=now())
        return

    source_id = job.get("source") or "pinned"
    try:
        tree, source_label, tolerant, measured = resolve_source(source_id)
    except Exception as exc:
        with lock:
            job.update(status="failed", phase="unknown firmware version", error=str(exc)[:300], finished=now())
        return

    with lock:
        job.update(status="running", phase="configuring", started=now(), source_label=source_label)
    sel = {"machine": job["machine"], "on": job["on"], "off": job["off"]}
    sel_path = jobdir / "selection.json"
    sel_path.write_text(json.dumps(sel, indent=2))

    apply_cmd = [sys.executable, str(APPLY),
                 "--catalog", str(CATALOG),
                 "--tree", str(tree),
                 "--config-dir", str(ROOT / "configs" / "Ender3S1-F1-v2"),
                 "--selection", "@" + str(sel_path),
                 "--out", str(jobdir / "predicted.json"),
                 "--source-label", source_label]
    if job.get("allow_overflow"):
        apply_cmd.append("--allow-overflow")
    if tolerant:
        apply_cmd.append("--tolerant")
    if not measured:
        apply_cmd.append("--no-predict")
    if job.get("mesh"):
        apply_cmd += ["--mesh", str(job["mesh"])]
    rc = run_streaming(job, apply_cmd, ROOT)
    if rc != 0:
        with lock:
            job.update(status="failed", phase="configuration rejected", error="apply_features failed", finished=now())
        return

    predicted = json.loads((jobdir / "predicted.json").read_text())
    with lock:
        job.update(phase="compiling", predicted=predicted["predicted"])

    env = None
    try:
        catalog = json.loads(CATALOG.read_text())
        machine = next(m for m in catalog["machines"] if m["id"] == job["machine"])
        env = machine["platformio_env"]
    except Exception:
        env = "STM32F103RC_creality"

    rc = run_streaming(job, [str(PIO), "run", "-e", env], tree)
    build_log = "".join(job["log"])

    flash = FLASH_RE.search(build_log)
    ram = RAM_RE.search(build_log)
    binpath = None
    produce = tree / ".pio" / "build" / env
    candidates = sorted(produce.glob("firmware-*.bin"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates and (produce / "firmware.bin").exists():
        candidates = [produce / "firmware.bin"]

    if rc != 0 or not candidates or not flash:
        overflow = re.search(r"region .FLASH. overflowed by (\d+) bytes", build_log)
        detail = "PlatformIO returned %d" % rc
        if overflow:
            detail = ("link failed: FLASH overflowed by %s bytes - the catalogue undersold a feature, "
                      "so the measured cost has to replace the estimate" % overflow.group(1))
        with lock:
            job.update(status="failed", phase="build failed", error=detail, finished=now())
        return

    binpath = candidates[0]
    out = jobdir / "firmware.bin"
    shutil.copyfile(binpath, out)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()

    check = subprocess.run([sys.executable, str(ROOT / "scripts" / "check-vector-table.py"), str(out)],
                           capture_output=True, text=True)
    vector_ok = check.returncode == 0
    if not vector_ok:
        log_line(job, "vector table check FAILED: " + (check.stdout or check.stderr).strip()[:300])

    catalog_now = json.loads(CATALOG.read_text())
    defaults = {f["id"]: bool(f["on_by_default"]) for f in catalog_now["features"]}
    # the API receives overrides, not a full list: anything not named keeps its default
    chosen = {}
    for fid, default in defaults.items():
        if fid in job["off"]:
            chosen[fid] = False
        elif fid in job["on"]:
            chosen[fid] = True
        else:
            chosen[fid] = default
    added = sorted(fid for fid in chosen if chosen[fid] and not defaults[fid])
    removed = sorted(fid for fid in chosen if not chosen[fid] and defaults[fid])
    risky = sorted(f["id"] for f in catalog_now["features"]
                   if f.get("risk") == "high" and chosen.get(f["id"]) != defaults[f["id"]])

    manifest = {
        "job": job["id"],
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "machine": job["machine"],
        "selection": {"on": job["on"], "off": job["off"]},
        "diff_vs_shipped": {"added": added, "removed": removed},
        "warnings": (["changes a safety or recovery affordance: " + ", ".join(risky)] if risky else [])
                    + (["artifact failed the ARM vector-table check - do not flash it"] if not vector_ok else []),
        "predicted": predicted["predicted"],
        "measured": {
            "flash_used": int(flash.group(2)),
            "flash_region": int(flash.group(3)),
            "flash_percent": float(flash.group(1)),
            "ram_used": int(ram.group(2)) if ram else None,
            "ram_total": int(ram.group(3)) if ram else None,
            "file_size": out.stat().st_size,
            "sha256": digest,
            "vector_table_ok": vector_ok,
        },
        "machine_name": predicted.get("machine_name_stamped"),
        "upstream": predicted.get("upstream"),
        "changed": predicted.get("changed"),
        "mesh": predicted.get("mesh") or ({"size": job.get("mesh")} if job.get("mesh") else None),
        "skipped": predicted.get("skipped", []),
        "auto_added": predicted.get("auto_added", []),
        "auto_removed": predicted.get("auto_removed", []),
        "screen": {
            "os": job.get("screen_os"),
            "assets": job.get("screen_assets"),
            "note": "the panel's menus come from the mainboard defines above; these two files are what "
                    "you write to the screen's own card",
        },
    }
    (jobdir / "manifest.json").write_text(json.dumps(manifest, indent=2) + chr(10))

    with lock:
        job.update(status="succeeded", phase="done", finished=now(),
                   result=manifest["measured"], manifest=str(jobdir / "manifest.json"),
                   diff=manifest["diff_vs_shipped"], warnings=manifest["warnings"])
    log_line(job, "built %d bytes, sha256 %s" % (out.stat().st_size, digest[:16]))


def write_job(job):
    """Format the selected device and put the selected payloads on it."""
    parts = job["parts"]
    jobdir = JOBS / job["id"]
    jobdir.mkdir(parents=True, exist_ok=True)
    with lock:
        job.update(status="running", phase="preparing the card", started=now())

    def log(msg):
        log_line(job, msg)

    firmware = None
    os_path = assets_path = None
    build_id = job.get("build_id") or ""
    os_id, assets_id = job.get("screen_os"), job.get("screen_assets")
    manifest_path = JOBS / build_id / "manifest.json"
    if manifest_path.exists():
        screen = json.loads(manifest_path.read_text()).get("screen", {})
        os_id = os_id or screen.get("os")
        assets_id = assets_id or screen.get("assets")
    catalog = json.loads(CATALOG.read_text())
    o = next((x for x in catalog.get("screen", {}).get("os", []) if x["id"] == os_id), None)
    a = next((x for x in catalog.get("screen", {}).get("assets", []) if x["id"] == assets_id), None)
    os_path = (ROOT / o["path"]) if o else None
    assets_path = (ROOT / a["path"]) if a else None
    if "screen" in parts and (os_path is None or assets_path is None):
        with lock:
            job.update(status="failed", phase="no screen package",
                       error="no screen OS/asset pack was resolved for this write", finished=now())
        return
    if "board" in parts:
        firmware = JOBS / build_id / "firmware.bin"
        if not firmware.exists():
            with lock:
                job.update(status="failed", phase="no firmware",
                           error="build %s has no artifact to write" % build_id, finished=now())
            return

    need = 0
    if firmware is not None:
        need += firmware.stat().st_size
    if os_path is not None and os_path.exists():
        need += os_path.stat().st_size
    if assets_path is not None and assets_path.is_dir():
        need += sum(f.stat().st_size for f in assets_path.rglob("*") if f.is_file())
    target = next((d for d in writer.list_devices() if d["path"] == job["device"]), None)
    if target and target["size"] and need > target["size"] * 0.97:
        with lock:
            job.update(status="failed", phase="payload too large",
                       error="the payload needs %d bytes and %s holds %d"
                             % (need, job["device"], target["size"]), finished=now())
        return

    try:
        result = writer.write_card(job["device"], parts, firmware, os_path, assets_path, log)
    except Exception as exc:
        with lock:
            job.update(status="failed", phase="write failed", error=str(exc)[:400], finished=now())
        return

    (jobdir / "write-manifest.json").write_text(json.dumps(result, indent=2) + chr(10))
    name = next((w["file"] for w in result["written"] if w["what"] == "mainboard"), None)
    if name:
        with open(ROOT / "firmware" / "flash-filenames.txt", "a") as fh:
            fh.write("    %-17s %s  written by the configurator\n" % (name, time.strftime("%Y-%m-%d")))
    log("card ready: %s" % ", ".join(w["what"] for w in result["written"]))
    with lock:
        job.update(status="succeeded", phase="card written", finished=now(),
                   result={"device": job["device"], "parts": parts, "written": result["written"]})


def worker():
    while True:
        job = work.get()
        try:
            if job.get("kind") == "write":
                write_job(job)
            elif job.get("kind") == "fetch":
                fetch_job(job)
            else:
                build_job(job)
        except Exception as exc:  # keep the worker alive
            with lock:
                job.update(status="failed", phase="exception", error=repr(exc), finished=now())
        finally:
            work.task_done()


JOB_ID_RE = __import__("re").compile(r"^[0-9a-f]{12}$")
STATIC_RE = __import__("re").compile(r"^[A-Za-z0-9._-]+$")
MAX_BODY = 64 * 1024


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_HEAD(self):
        """Answer HEAD like GET, without the body: link checkers and curl -I use it."""
        path = urlparse(self.path).path
        if path in ("/", "/index.html", "/static/app.js", "/static/style.css") or path.startswith("/api/"):
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        try:
            return self._get()
        except Exception as exc:  # never leave a request without an answer
            sys.stderr.write("GET %s failed: %r\n" % (self.path, exc))
            return self._json({"error": "internal error: %s" % str(exc)[:200]}, 500)

    def do_POST(self):
        try:
            return self._post()
        except Exception as exc:
            sys.stderr.write("POST %s failed: %r\n" % (self.path, exc))
            return self._json({"error": "internal error: %s" % str(exc)[:200]}, 500)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, indent=2))

    def _file(self, path: Path, ctype="application/octet-stream"):
        if not path.exists():
            return self._json({"error": "not found"}, 404)
        self._send(200, path.read_bytes(), ctype)

    def _get(self):
        parts = urlparse(self.path)
        path = parts.path
        if path in ("/", "/index.html"):
            return self._file(WEB / "index.html", "text/html; charset=utf-8")
        if path.startswith("/static/"):
            name = path.split("/static/", 1)[1]
            if not STATIC_RE.match(name) or name.startswith("."):
                return self._json({"error": "not found"}, 404)
            ctype = ("text/css" if name.endswith(".css")
                     else "application/json" if name.endswith(".json")
                     else "application/javascript")
            return self._file(WEB / name, ctype)
        if path == "/api/catalog":
            catalog = json.loads(CATALOG.read_text())
            catalog["build"] = tree_ready()
            return self._json(catalog)
        if path == "/api/versions":
            try:
                data = sources.list_versions(refresh="refresh=1" in self.path)
                return self._json(data)
            except Exception as exc:
                return self._json({"error": str(exc)[:300]}, 500)
        if path == "/api/versions/inspect":
            query = parse_qs(urlparse(self.path).query)
            version_id = (query.get("id") or [""])[0]
            entry = sources.get(version_id)
            if entry is None or not entry.get("path"):
                return self._json({"error": "that version is not downloaded yet"}, 404)
            try:
                catalog = json.loads(CATALOG.read_text())
                return self._json(sources.inspect(ROOT / entry["path"], catalog))
            except Exception as exc:
                return self._json({"error": str(exc)[:300]}, 500)
        if path == "/api/devices":
            try:
                devices = writer.list_devices()
                return self._json({"devices": devices, "sudo": writer._sudo_ok()})
            except Exception as exc:
                return self._json({"error": str(exc)[:300]}, 500)
        if path == "/api/builds":
            with lock:
                items = sorted(jobs.values(), key=lambda j: j["created"], reverse=True)[:20]
                return self._json([{k: j.get(k) for k in
                                    ("id", "status", "phase", "machine", "created", "finished")}
                                   for j in items])
        if path.startswith("/api/build/"):
            rest = path[len("/api/build/"):].strip("/")
            head = rest.split("/", 1)[0]
            if head and not JOB_ID_RE.match(head):
                return self._json({"error": "not found"}, 404)
            if rest.endswith("/firmware.bin"):
                jid = rest[:-len("/firmware.bin")]
                return self._file(JOBS / jid / "firmware.bin")
            if rest.endswith("/manifest.json"):
                jid = rest[:-len("/manifest.json")]
                return self._file(JOBS / jid / "manifest.json")
            if rest.endswith("/bundle.zip"):
                jid = rest[:-len("/bundle.zip")]
                return self._bundle(jid)
            with lock:
                job = jobs.get(rest)
                if not job:
                    return self._json({"error": "unknown job"}, 404)
                view = {k: job.get(k) for k in
                        ("id", "status", "phase", "machine", "created", "finished",
                         "predicted", "result", "error", "manifest", "diff", "warnings",
                         "screen_os", "screen_assets", "kind", "device", "parts",
                         "source", "source_label", "mesh")}
                view["on"] = job.get("on", [])
                view["off"] = job.get("off", [])
                view["log"] = job["log"][-60:]
                return self._json(view)
        return self._json({"error": "not found"}, 404)

    def _bundle(self, jid):
        """Everything needed to flash both processors, in one honest zip."""
        jobdir = JOBS / jid
        if not (jobdir / "firmware.bin").exists():
            return self._json({"error": "no firmware for that job"}, 404)
        catalog = json.loads(CATALOG.read_text())
        manifest = json.loads((jobdir / "manifest.json").read_text()) if (jobdir / "manifest.json").exists() else {}
        screen = catalog.get("screen", {})
        # the screen package is independent of the compiled image, so the download may name its own
        query = parse_qs(urlparse(self.path).query)
        os_id = (query.get("os") or [manifest.get("screen", {}).get("os")])[0]
        assets_id = (query.get("assets") or [manifest.get("screen", {}).get("assets")])[0]
        os_entry = next((x for x in screen.get("os", []) if x["id"] == os_id), None)
        assets_entry = next((x for x in screen.get("assets", []) if x["id"] == assets_id), None)
        if (os_id and os_entry is None) or (assets_id and assets_entry is None):
            return self._json({"error": "unknown screen package %r / %r" % (os_id, assets_id)}, 400)
        if assets_entry and assets_entry.get("pairs_with") != "custom":
            return self._json({"error": "%s pairs with stock firmware, not this build" % assets_entry["label"]}, 400)

        instructions = [
            "Ender 3 S1 - flash both processors",
            "",
            "1. MAINBOARD",
            "   - write firmware.bin to a FAT32 card (MBR, 4096-byte clusters) with a filename",
            "     this printer has never used - see firmware/flash-filenames.txt in the repo",
            "   - printer off, USB unplugged, card into the FRONT slot, power on, wait 60 s",
            "   - power off, card out, USB back, power on",
            "   - verify: M115 at 250000 baud reports Ender3S1-CFG",
            "",
            "2. SCREEN (only if you are changing the screen firmware)",
        ]
        if os_entry:
            instructions.append("   - OS image:   %s (%d bytes, md5 %s)" % (
                os_entry["label"], os_entry["bytes"], os_entry.get("md5", "?")))
        else:
            instructions.append("   - OS image:   none selected - the panel keeps what it has")
        if assets_entry:
            instructions.append("   - assets:     %s (%d bytes)" % (assets_entry["label"], assets_entry["bytes"]))
        instructions += [
            "   - card: MBR + FAT32 + 4096-byte clusters, 8 GB or less",
            "   - copy screen/firmware.zlib and the screen/private folder to the card ROOT",
            "   - power off, open the front panel, card into the SCREEN's microSD slot, power on",
            "   - the panel flashes blue/orange for about a minute, then power off and reassemble",
            "   - first boot after a screen flash holds the logo about 30 s: wait",
            "",
            "3. PAIRING RULE - the reason this panel was bricked once",
            "   custom mainboard firmware  <->  mriscoc assets",
            "   stock Creality firmware    <->  Creality assets",
            "   Never mix them. Never flash dcboot.bin. Never flash the mriscoc firmware.zlib.",
            "",
            "Full procedures: docs/FLASHING.md and docs/SCREEN.md in the repository.",
            "",
            "This bundle was produced by tools/configurator/server.py job " + jid + ".",
        ]

        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(jobdir / "firmware.bin", "firmware.bin")
            if (jobdir / "manifest.json").exists():
                z.write(jobdir / "manifest.json", "manifest.json")
            z.writestr("FLASH-THIS.txt", chr(10).join(instructions) + chr(10))
            if os_entry:
                src = ROOT / os_entry["path"]
                if src.exists():
                    z.write(src, "screen/firmware.zlib")
            if assets_entry:
                src = ROOT / assets_entry["path"]
                if src.is_dir():
                    for f in sorted(src.rglob("*")):
                        if f.is_file():
                            z.write(f, "screen/private/" + str(f.relative_to(src)))
        body = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="ender3s1-bundle-%s.zip"' % jid)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _fetch_version(self):
        """POST /api/versions/fetch - download one firmware version."""
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json({"error": "request too large"}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json({"error": "bad json"}, 400)
        version_id = body.get("id") or ""
        entry = sources.get(version_id)
        if entry is None:
            return self._json({"error": "unknown version %r" % version_id}, 400)
        if entry.get("kind") == "pinned":
            return self._json({"error": "the pinned tree is already here"}, 400)
        if entry.get("path"):
            return self._json({"id": None, "status": "already", "path": entry["path"]}, 200)

        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "kind": "fetch", "status": "queued", "phase": "queued",
               "source": version_id, "created": now(), "log": [], "result": None}
        with lock:
            jobs[jid] = job
        work.put(job)
        return self._json({"id": jid, "status": "queued"}, 202)

    def _write(self):
        """POST /api/write - format a device and put the selected payloads on it."""
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json({"error": "request too large"}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json({"error": "bad json"}, 400)

        device = body.get("device", "")
        parts = [p for p in body.get("parts", []) if p in ("board", "screen")]
        build_id = body.get("build_id", "")
        if not parts:
            return self._json({"error": "say what to write: board, screen, or both"}, 400)
        if not device.startswith("/dev/"):
            return self._json({"error": "a device path is required"}, 400)

        devices = writer.list_devices()
        target = next((d for d in devices if d["path"] == device), None)
        if target is None:
            return self._json({"error": "%s is not a block device this service can see" % device}, 404)
        if not target["usable"]:
            return self._json({"error": "refusing %s: %s" % (device, target["why_not"])}, 400)
        if "board" in parts:
            if not build_id or not (JOBS / build_id / "firmware.bin").exists():
                return self._json({"error": "the mainboard part needs a finished build"}, 400)
        catalog = json.loads(CATALOG.read_text())
        screen = catalog.get("screen", {})
        defaults = screen.get("defaults", {})
        os_id = body.get("screen_os") or defaults.get("os")
        assets_id = body.get("screen_assets") or defaults.get("assets")
        if "screen" in parts:
            if not any(x["id"] == os_id for x in screen.get("os", [])):
                return self._json({"error": "unknown screen OS %r" % os_id}, 400)
            if not any(x["id"] == assets_id for x in screen.get("assets", [])):
                return self._json({"error": "unknown screen asset pack %r" % assets_id}, 400)
        if not writer._sudo_ok():
            return self._json({"error": "writing needs root and passwordless sudo is not available; "
                                        "start the service with sudo"}, 409)

        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "kind": "write", "status": "queued", "phase": "queued",
               "device": device, "parts": parts, "build_id": build_id,
               "screen_os": os_id, "screen_assets": assets_id,
               "created": now(), "log": [], "result": None}
        with lock:
            jobs[jid] = job
        work.put(job)
        return self._json({"id": jid, "status": "queued"}, 202)

    def _post(self):
        path = urlparse(self.path).path
        if path == "/api/versions/fetch":
            return self._fetch_version()
        if path == "/api/write":
            return self._write()
        if path != "/api/build":
            return self._json({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json({"error": "request too large"}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json({"error": "bad json"}, 400)

        catalog = json.loads(CATALOG.read_text())
        known = {f["id"] for f in catalog["features"]}
        machine = body.get("machine", "ender3s1-f103")
        m = next((x for x in catalog["machines"] if x["id"] == machine), None)
        if not m or not m.get("supported"):
            return self._json({"error": "unsupported machine"}, 400)
        on = [f for f in body.get("on", []) if f in known]
        off = [f for f in body.get("off", []) if f in known]

        screen = catalog.get("screen", {})
        defaults = screen.get("defaults", {})
        os_id = body.get("screen_os") or defaults.get("os")
        assets_id = body.get("screen_assets") or defaults.get("assets")
        os_entry = next((x for x in screen.get("os", []) if x["id"] == os_id), None)
        assets_entry = next((x for x in screen.get("assets", []) if x["id"] == assets_id), None)
        if os_entry is None:
            return self._json({"error": "unknown screen OS %r" % os_id}, 400)
        if assets_entry is None:
            return self._json({"error": "unknown screen asset pack %r" % assets_id}, 400)
        if assets_entry.get("pairs_with") != "custom":
            return self._json({
                "error": ("%s pairs with %s mainboard firmware, and this builder only produces custom "
                          "firmware. Flashing a mismatched pack is what bricked this panel."
                          % (assets_entry["label"], assets_entry.get("pairs_with")))
            }, 400)
        if not assets_entry.get("bundled"):
            return self._json({"error": "%s is documented but not shipped (too large for the panel partition)"
                                        % assets_entry["label"]}, 400)

        mesh = body.get("mesh")
        if mesh is not None:
            spec = catalog.get("mesh") or {}
            lo, hi = int(spec.get("min", 3)), int(spec.get("max", 5))
            try:
                mesh = int(mesh)
            except (TypeError, ValueError):
                return self._json({"error": "mesh must be a number"}, 400)
            if not (lo <= mesh <= hi):
                return self._json({
                    "error": ("%d is outside the mesh sizes this firmware can build (%d..%d). %s"
                              % (mesh, lo, hi, spec.get("matrix_note", "")))
                }, 400)

        if len(work.queue) > 3:
            return self._json({"error": "queue full, try again shortly"}, 429)

        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "kind": "build", "status": "queued", "phase": "queued", "machine": machine,
               "on": on, "off": off, "screen_os": os_id, "screen_assets": assets_id,
               "allow_overflow": bool(body.get("allow_overflow")),
               "mesh": mesh,
               "source": body.get("source") or "pinned",
               "created": now(), "log": [], "predicted": None, "result": None}
        with lock:
            jobs[jid] = job
        work.put(job)
        return self._json({"id": jid, "status": "queued"}, 202)


def main():
    host = os.environ.get("CONFIGURATOR_HOST", "127.0.0.1")
    port = int(os.environ.get("CONFIGURATOR_PORT", "8787"))
    JOBS.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    srv = ThreadingHTTPServer((host, port), Handler)
    ready = tree_ready()
    print("configurator on http://%s:%d" % (host, port))
    print("  catalog : %s (%d features)" % (CATALOG, len(json.loads(CATALOG.read_text())["features"])))
    print("  tree    : %s" % ("ready" if ready["toolchain_ready"] else "NOT READY - " + ready["hint"]))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")


if __name__ == "__main__":
    main()
