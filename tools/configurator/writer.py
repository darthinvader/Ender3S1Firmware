#!/usr/bin/env python3
"""Enumerate removable block devices and write a card for one or both processors.

This is the part of the configurator that touches hardware, so it is deliberately
separate from the build engine and deliberately paranoid:

  * only top-level block devices are offered
  * internal disks are refused, even if a caller names one explicitly
  * a device carrying /, /boot, /home or /usr is refused twice over
  * every destructive step is logged, and the card is verified by md5 after the copy

Writing needs root. The service uses passwordless sudo when it is available and
refuses cleanly when it is not, instead of hanging on a password prompt.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAMES = ROOT / "firmware" / "flash-filenames.txt"
SYSTEM_MOUNTS = ("/", "/boot", "/home", "/usr", "/var", "/etc", "/opt", "/mnt/storage")


def _sudo_ok() -> bool:
    if os.geteuid() == 0:
        return True
    return subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0


def run(argv, check=True, timeout=600):
    """Run a privileged command; returns (rc, combined output)."""
    cmd = list(argv) if os.geteuid() == 0 else ["sudo", "-n"] + list(argv)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout or "") + (proc.stderr or "")
    if check and proc.returncode != 0:
        raise RuntimeError("%s failed (%d): %s" % (" ".join(argv), proc.returncode, out.strip()[:400]))
    return proc.returncode, out


def human(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return str(n)


def list_devices(include_loop: bool = True) -> list:
    """Top-level block devices with everything the UI needs to warn properly."""
    rc, out = run(["lsblk", "-J", "-b", "-o", "NAME,SIZE,TYPE,RM,TRAN,MODEL,MOUNTPOINT"], check=False)
    if rc != 0:
        return []
    data = json.loads(out[out.find("{"):])
    devices = []
    for dev in data.get("blockdevices", []):
        if dev.get("type") not in ("disk", "loop"):
            continue
        path = "/dev/" + dev["name"]
        size = int(dev.get("size") or 0)
        children = dev.get("children") or []
        mounts = [c.get("mountpoint") for c in children if c.get("mountpoint")]
        if dev.get("mountpoint"):
            mounts.append(dev["mountpoint"])
        removable = bool(dev.get("rm"))
        is_loop = dev["name"].startswith("loop")
        internal = not removable and not is_loop
        system = any(m in SYSTEM_MOUNTS or m == "/" or m.startswith("/boot") or m.startswith("/home")
                     for m in mounts)
        entry = {
            "path": path,
            "name": dev["name"],
            "size": size,
            "size_human": human(size),
            "model": (dev.get("model") or "").strip() or "unknown",
            "transport": dev.get("tran") or ("loop" if is_loop else "unknown"),
            "removable": removable,
            "loop": is_loop,
            "mounted": mounts,
            "internal": internal,
            "system": system,
            "usable": (not internal) and (not system) and size > 0,
            "why_not": ("internal disk" if internal else
                        "carries a system mount" if system else
                        "no media inserted" if size == 0 else ""),
        }
        if is_loop and not include_loop:
            continue
        devices.append(entry)
    return devices


def used_names() -> set:
    if not NAMES.exists():
        return set()
    names = set()
    for line in NAMES.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.add(line.split()[0].lower())
    return names


def next_filename() -> str:
    used = used_names()
    for _ in range(60):
        candidate = "F1%s%s.bin" % (time.strftime("%d%H"), "%02d" % int(time.time() * 1000 % 100))
        if candidate.lower() not in used:
            return candidate
    raise RuntimeError("could not generate an unused 8.3 filename")


def find_partition(device: str) -> str:
    time.sleep(1)
    rc, out = run(["lsblk", "-ln", "-o", "NAME", device], check=False)
    names = [line.split()[0] for line in out.splitlines() if line.split()]
    if len(names) < 2:
        raise RuntimeError("no partition appeared on %s" % device)
    return "/dev/" + names[1]


def write_card(device: str, parts: list, firmware_bin: Path, screen_os: Path | None,
               screen_assets: Path | None, log) -> dict:
    """Format one card and put the selected payloads on it."""
    if not _sudo_ok():
        raise RuntimeError("writing a card needs root and passwordless sudo is not available; "
                           "start the service with sudo or write the card with scripts/flash-card.sh")

    target = next((d for d in list_devices() if d["path"] == device), None)
    if target is None:
        raise RuntimeError("%s is not a block device this service can see" % device)
    if not target["usable"]:
        raise RuntimeError("refusing %s: %s" % (device, target["why_not"]))

    log("target %s (%s %s, %s)" % (device, target["model"], target["transport"], target["size_human"]))
    for m in target["mounted"]:
        log("unmounting %s" % m)
        run(["umount", m], check=False)
        run(["udisksctl", "unmount", "-b", device], check=False)

    log("wiping %s" % device)
    run(["wipefs", "-a", device], check=False)
    run(["parted", "-s", device, "mklabel", "msdos"])
    run(["parted", "-s", device, "mkpart", "primary", "fat32", "1MiB", "100%"])
    run(["partprobe", device], check=False)

    part = find_partition(device)
    label = "FWFLASH" if "board" in parts else "SCREEN"
    log("formatting %s as FAT32, 4096-byte clusters, label %s" % (part, label))
    run(["mkfs.vfat", "-F", "32", "-s", "8", "-n", label, part])

    mnt = tempfile.mkdtemp(prefix="cfg-card-")
    written = []
    try:
        run(["mount", part, mnt])
        if "board" in parts:
            if not firmware_bin.exists():
                raise RuntimeError("no firmware.bin for that build")
            name = next_filename()
            dest = Path(mnt) / name
            run(["cp", str(firmware_bin), str(dest)])
            a = subprocess.run(["md5sum", str(firmware_bin)], capture_output=True, text=True).stdout.split()[0]
            b = run(["md5sum", str(dest)], check=False)[1].split()[0]
            if a != b:
                raise RuntimeError("mainboard image md5 mismatch after copy (%s != %s)" % (a, b))
            written.append({"what": "mainboard", "file": name, "bytes": dest.stat().st_size, "md5": a})
            log("mainboard: %s (%d B, md5 %s)" % (name, dest.stat().st_size, a))
        if "screen" in parts:
            if screen_os and screen_os.exists():
                dest = Path(mnt) / "firmware.zlib"
                run(["cp", str(screen_os), str(dest)])
                b = run(["md5sum", str(dest)], check=False)[1].split()[0]
                written.append({"what": "screen os", "file": "firmware.zlib", "bytes": dest.stat().st_size, "md5": b})
                log("screen OS: firmware.zlib (%d B)" % dest.stat().st_size)
            if screen_assets and screen_assets.is_dir():
                dst = Path(mnt) / "private"
                if dst.exists():
                    run(["rm", "-rf", str(dst)])
                # a FAT32 card cannot store ownership or mode, so plain -r: -a would fail
                run(["cp", "-r", str(screen_assets), str(dst)])
                n = sum(1 for f in dst.rglob("*") if f.is_file())
                written.append({"what": "screen assets", "files": n})
                log("screen assets: %d files in private/" % n)
        log("syncing")
        run(["sync"])
    finally:
        run(["umount", mnt], check=False)
        shutil.rmtree(mnt, ignore_errors=True)

    return {"device": device, "device_info": target, "parts": parts, "written": written}
