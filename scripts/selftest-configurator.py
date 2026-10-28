#!/usr/bin/env python3
"""Behavioural self-test for the configurator service.

Starts the server on a free port, asks it real questions, stops it. Catches the
classes of bug that static checks cannot: a route that 500s, a path that escapes
its directory, an endpoint that starts accepting nonsense.

  python3 scripts/selftest-configurator.py        # 0 = all good

Deliberately does not compile anything: builds are minutes, this is seconds, and
it runs as part of "make verify".
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "tools" / "configurator" / "server.py"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def call(port: int, path: str, method: str = "GET", body: bytes | None = None):
    """Return (status, headers, body-bytes). Never raises for HTTP errors."""
    url = "http://127.0.0.1:%d%s" % (port, path)
    req = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()
    except Exception as exc:  # connection refused while the server is still starting
        raise SystemExit("could not reach %s: %r" % (url, exc))


def wait_ready(port: int, proc: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit("the server exited with %s" % proc.returncode)
        try:
            status, _, _ = call(port, "/api/catalog")
            if status == 200:
                return
        except SystemExit:
            pass
        time.sleep(0.2)
    raise SystemExit("the server did not answer within %.0f s" % timeout)


def main() -> int:
    port = free_port()
    env = dict(os.environ, CONFIGURATOR_PORT=str(port))
    proc = subprocess.Popen([sys.executable, str(SERVER)], env=env, cwd=str(ROOT),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    checks = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    try:
        wait_ready(port, proc)

        status, _, body = call(port, "/")
        check("index answers", status == 200 and b"Ender 3 S1 firmware" in body, "status %s" % status)

        status, headers, body = call(port, "/", "HEAD")
        check("HEAD answers", status == 200, "status %s" % status)

        status, _, body = call(port, "/static/app.js")
        check("app.js is served", status == 200 and b"renderMesh" in body, "status %s" % status)

        status, _, _ = call(port, "/static/../../../../etc/passwd")
        check("static path cannot escape", status == 404, "status %s" % status)

        status, _, _ = call(port, "/api/build/../../../../etc/passwd/firmware.bin")
        check("job path cannot escape", status == 404, "status %s" % status)

        status, _, body = call(port, "/api/build/ffffffffffff")
        check("unknown job is a JSON 404",
              status == 404 and b"error" in body, "status %s" % status)

        status, _, body = call(port, "/api/catalog")
        catalog = json.loads(body) if status == 200 else {}
        check("catalogue has the features", len(catalog.get("features", [])) >= 60,
              "%d features" % len(catalog.get("features", [])))
        mesh = catalog.get("mesh") or {}
        check("catalogue declares mesh bounds",
              mesh.get("min") == 3 and mesh.get("max") == 9 and mesh.get("default") == 7,
              json.dumps({k: mesh.get(k) for k in ("min", "max", "default")}))

        status, _, body = call(port, "/api/versions")
        versions = (json.loads(body).get("versions") if status == 200 else []) or []
        check("version list leads with the pin",
              bool(versions) and versions[0].get("kind") == "pinned",
              "%d versions" % len(versions))

        payload = json.dumps({"machine": "ender3s1-f103", "mesh": 12}).encode()
        status, _, body = call(port, "/api/build", "POST", payload)
        check("mesh above the ceiling is refused",
              status == 400 and b"9" in body and b"precompiled" in body,
              "status %s" % status)

        payload = json.dumps({"machine": "nope"}).encode()
        status, _, _ = call(port, "/api/build", "POST", payload)
        check("unknown machine is refused", status == 400, "status %s" % status)

        payload = json.dumps({"id": "tag:does-not-exist"}).encode()
        status, _, _ = call(port, "/api/versions/fetch", "POST", payload)
        check("unknown version cannot be fetched", status in (400, 404), "status %s" % status)

        payload = b'{"pad": "' + b"x" * (70 * 1024) + b'"}'
        status, _, _ = call(port, "/api/build", "POST", payload)
        check("oversized request is refused", status in (400, 413), "status %s" % status)

        status, _, body = call(port, "/api/does-not-exist")
        check("unknown route is JSON", status == 404 and b"error" in body, "status %s" % status)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    failed = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print("%s %-34s %s" % ("ok  " if ok else "FAIL", name, detail))
    print("\n%d checks, %d failed" % (len(checks), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

