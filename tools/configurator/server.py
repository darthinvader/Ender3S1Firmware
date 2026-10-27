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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

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


def build_job(job):
    jobdir = JOBS / job["id"]
    jobdir.mkdir(parents=True, exist_ok=True)
    ready = tree_ready()
    if not ready["toolchain_ready"]:
        with lock:
            job.update(status="failed", phase="no build tree", error=ready["hint"], finished=now())
        return

    with lock:
        job.update(status="running", phase="configuring", started=now())
    sel = {"machine": job["machine"], "on": job["on"], "off": job["off"]}
    sel_path = jobdir / "selection.json"
    sel_path.write_text(json.dumps(sel, indent=2))

    rc = run_streaming(job, [sys.executable, str(APPLY),
                             "--catalog", str(CATALOG),
                             "--tree", str(TREE),
                             "--config-dir", str(ROOT / "configs" / "Ender3S1-F1-v2"),
                             "--selection", "@" + str(sel_path),
                             "--out", str(jobdir / "predicted.json")], ROOT)
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

    rc = run_streaming(job, [str(PIO), "run", "-e", env], TREE)
    build_log = "".join(job["log"])

    flash = FLASH_RE.search(build_log)
    ram = RAM_RE.search(build_log)
    binpath = None
    produce = TREE / ".pio" / "build" / env
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
    }
    (jobdir / "manifest.json").write_text(json.dumps(manifest, indent=2) + chr(10))

    with lock:
        job.update(status="succeeded", phase="done", finished=now(),
                   result=manifest["measured"], manifest=str(jobdir / "manifest.json"),
                   diff=manifest["diff_vs_shipped"], warnings=manifest["warnings"])
    log_line(job, "built %d bytes, sha256 %s" % (out.stat().st_size, digest[:16]))


def worker():
    while True:
        job = work.get()
        try:
            build_job(job)
        except Exception as exc:  # keep the worker alive
            with lock:
                job.update(status="failed", phase="exception", error=repr(exc), finished=now())
        finally:
            work.task_done()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

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

    def do_GET(self):
        parts = urlparse(self.path)
        path = parts.path
        if path in ("/", "/index.html"):
            return self._file(WEB / "index.html", "text/html; charset=utf-8")
        if path.startswith("/static/"):
            name = path.split("/static/", 1)[1]
            ctype = "text/css" if name.endswith(".css") else "application/javascript"
            return self._file(WEB / name, ctype)
        if path == "/api/catalog":
            catalog = json.loads(CATALOG.read_text())
            catalog["build"] = tree_ready()
            return self._json(catalog)
        if path == "/api/builds":
            with lock:
                items = sorted(jobs.values(), key=lambda j: j["created"], reverse=True)[:20]
                return self._json([{k: j.get(k) for k in
                                    ("id", "status", "phase", "machine", "created", "finished")}
                                   for j in items])
        if path.startswith("/api/build/"):
            rest = path[len("/api/build/"):].strip("/")
            if rest.endswith("/firmware.bin"):
                jid = rest[:-len("/firmware.bin")]
                return self._file(JOBS / jid / "firmware.bin")
            if rest.endswith("/manifest.json"):
                jid = rest[:-len("/manifest.json")]
                return self._file(JOBS / jid / "manifest.json")
            with lock:
                job = jobs.get(rest)
                if not job:
                    return self._json({"error": "unknown job"}, 404)
                view = {k: job.get(k) for k in
                        ("id", "status", "phase", "machine", "created", "finished",
                         "predicted", "result", "error", "manifest", "diff", "warnings")}
                view["on"] = job["on"]
                view["off"] = job["off"]
                view["log"] = job["log"][-60:]
                return self._json(view)
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/build":
            return self._json({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length") or 0)
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
        if len(work.queue) > 3:
            return self._json({"error": "queue full, try again shortly"}, 429)

        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "status": "queued", "phase": "queued", "machine": machine,
               "on": on, "off": off, "created": now(), "log": [], "predicted": None, "result": None}
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
