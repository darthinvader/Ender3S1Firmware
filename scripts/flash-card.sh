#!/usr/bin/env bash
#
# flash-card.sh - prepare a FAT32 SD card for a Creality bootloader flash.
#
# The card layout the bootloader insists on: MBR partition table, FAT32,
# 4096-byte clusters, exactly one .bin in the root, under a filename that has
# never been used on this machine before.
#
# Usage:
#   ./scripts/flash-card.sh --list
#   ./scripts/flash-card.sh --next-name
#   ./scripts/flash-card.sh --device /dev/sdX --bin firmware/Ender3S1-F1-v2-20260730.bin
#   ./scripts/flash-card.sh --device /dev/sdX --bin firmware/... --yes
#
# Without --yes the script only prints the plan and changes nothing. With
# --yes it requires you to type the device path, then wipes the device.
#
# The device must be removable. An internal disk is refused even if you name
# one explicitly, and a device carrying the root filesystem is refused before
# anything is unmounted.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAMES="$ROOT/firmware/flash-filenames.txt"

MODE="plan"
DEVICE=""
IMAGE=""
TARGET_NAME=""
CONFIRMED=0
USE_SUDO=0

say()  { printf "\n==> %s\n" "$*"; }
note() { printf "    %s\n" "$*"; }
die()  { printf "error: %s\n" "$*" >&2; exit 1; }
usage() { sed -n "3,22p" "$0" | sed "s/^# \{0,1\}//"; exit 0; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --list)      MODE="list"; shift ;;
    --next-name) MODE="name"; shift ;;
    --device)    DEVICE="$2"; shift 2 ;;
    --bin)       IMAGE="$2"; shift 2 ;;
    --name)      TARGET_NAME="$2"; shift 2 ;;
    --yes)       CONFIRMED=1; shift ;;
    -h|--help)   usage ;;
    *)           die "unknown argument: $1" ;;
  esac
done

used_names() {
  [ -f "$NAMES" ] || return 0
  grep -vE "^[[:space:]]*#" "$NAMES" | awk "NF { print tolower(\$1) }"
}

next_name() {
  local candidate attempt
  for attempt in $(seq 1 40); do
    candidate="F1$(date +%d%H)$(printf "%02d" "$((RANDOM % 100))").bin"
    if ! used_names | grep -qx "$candidate"; then
      printf "%s\n" "$candidate"
      return 0
    fi
  done
  die "could not generate an unused filename"
}

case "$MODE" in
  name)
    next_name
    exit 0
    ;;
  list)
    say "removable block devices"
    lsblk -d -o NAME,SIZE,RM,MODEL,TRAN | awk 'NR==1 || $3==1'
    printf "\n    RM=1 means the kernel reports the device as removable\n"
    exit 0
    ;;
esac

########################################################################
# plan mode
[ -n "$DEVICE" ] || die "no device given (use --device /dev/sdX; --list shows candidates)"
[ -n "$IMAGE" ]  || die "no image given (use --bin firmware/<build>.bin)"
[ -f "$IMAGE" ]  || die "image not found: $IMAGE"
[ -b "$DEVICE" ] || die "not a block device: $DEVICE"

BASE="$(basename "$(readlink -f "$DEVICE")")"
SYSBLOCK="/sys/block/$BASE"
[ -d "$SYSBLOCK" ] || die "$DEVICE is not a whole disk (expected /sys/block/$BASE)"

# refuses to touch internal disks
if [ -r "$SYSBLOCK/removable" ] && [ "$(cat "$SYSBLOCK/removable")" != "1" ]; then
  die "$DEVICE reports removable=0; refusing to write an internal disk"
fi

# refuses to touch whatever carries the system
MOUNTS="$(lsblk -n -o MOUNTPOINT "$DEVICE" 2>/dev/null | sed "/^$/d" || true)"
for m in $MOUNTS; do
  case "$m" in
    /|/home|/home/*|/boot|/boot/*|/usr|/usr/*)
      die "$DEVICE carries $m; refusing to wipe a device with system mounts" ;;
  esac
done

if [ -z "$TARGET_NAME" ]; then
  TARGET_NAME="$(next_name)"
fi
TARGET_UPPER="$(printf "%s" "$TARGET_NAME" | tr "[:lower:]" "[:upper:]")"

NAME_LEN="$(printf "%s" "$TARGET_UPPER" | wc -c)"
[ "$NAME_LEN" -eq 12 ] || die "filename must be 8 characters plus .bin, got: $TARGET_NAME"
case "$TARGET_UPPER" in *.BIN) ;; *) die "filename must end in .bin" ;; esac
if used_names | grep -qx "$TARGET_NAME"; then
  die "filename $TARGET_NAME has already been used (the bootloader would ignore it)"
fi

say "plan"
note "device      $DEVICE  ($(lsblk -dno SIZE,MODEL "$DEVICE" | tr -s " "))"
note "image       $IMAGE"
note "image md5   $(md5sum "$IMAGE" | cut -d" " -f1)"
note "image size  $(stat -c %s "$IMAGE") bytes"
note "card name   $TARGET_UPPER"
note "layout      MBR + FAT32 + 4096-byte clusters, label FWFLASH, one .bin in the root"
printf "\n    This ERASES the entire device:\n"
note "  1. unmount every partition of $DEVICE"
note "  2. wipefs -a $DEVICE"
note "  3. parted mklabel msdos, one FAT32 partition from 1 MiB"
note "  4. mkfs.vfat -F 32 -s 8 -n FWFLASH"
note "  5. copy $TARGET_UPPER, sync, verify the md5 from the card"
note "  6. unmount and power the reader off"
note "  7. append $TARGET_UPPER to firmware/flash-filenames.txt"

if [ "$CONFIRMED" -ne 1 ]; then
  printf "\n    dry run - nothing was changed. Re-run with --yes to execute.\n"
  exit 0
fi

[ -t 0 ] || die "refusing to run destructively without a terminal to confirm on"
if [ "$(id -u)" -ne 0 ]; then
  sudo -n true 2>/dev/null || die "needs root and passwordless sudo is not available"
  USE_SUDO=1
fi
run() {
  if [ "$USE_SUDO" -eq 1 ]; then sudo -n "$@"; else "$@"; fi
}

printf "\nType the device path (%s) to confirm: " "$DEVICE"
read -r typed
[ "$typed" = "$DEVICE" ] || die "confirmation did not match; nothing was changed"

say "unmounting"
for part in $(lsblk -ln -o NAME "$DEVICE" | tail -n +2); do
  if [ -n "$(lsblk -no MOUNTPOINT /dev/$part | sed "/^$/d")" ]; then
    run umount "/dev/$part" || true
  fi
done

say "wiping $DEVICE"
run wipefs -a "$DEVICE"
run parted -s "$DEVICE" mklabel msdos
run parted -s "$DEVICE" mkpart primary fat32 1MiB 100%
run partprobe "$DEVICE" 2>/dev/null || sleep 1

PART="/dev/$BASE"1
[ -b "$PART" ] || PART="/dev/$(lsblk -ln -o NAME "$DEVICE" | tail -n +2 | head -n 1)"
[ -b "$PART" ] || die "could not find the new partition"

say "formatting $PART"
run mkfs.vfat -F 32 -s 8 -n FWFLASH "$PART"

MNT="$(mktemp -d)"
cleanup() { run umount "$MNT" 2>/dev/null || true; rmdir "$MNT" 2>/dev/null || true; }
trap cleanup EXIT

say "copying"
run mount "$PART" "$MNT"
run cp "$IMAGE" "$MNT/$TARGET_UPPER"
run sync
SRC_MD5="$(md5sum "$IMAGE" | cut -d" " -f1)"
DST_MD5="$(run md5sum "$MNT/$TARGET_UPPER" | cut -d" " -f1)"
[ "$SRC_MD5" = "$DST_MD5" ] || die "md5 mismatch after copy: $SRC_MD5 != $DST_MD5"
note "md5 verified: $SRC_MD5"
run ls -l "$MNT"

cleanup
trap - EXIT

say "powering the reader off"
run udisksctl power-off -b "$DEVICE" 2>/dev/null || note "power-off not available; unplug when the LED stops"

printf "%s      %s  written by scripts/flash-card.sh\n" "$TARGET_UPPER" "$(date +%Y-%m-%d)" >> "$NAMES"

say "done"
cat <<'NEXT'
Next, on the printer:

  1. power off, wait 15 s, unplug USB
  2. insert the card into the MAINBOARD slot (front of the printer)
  3. power on and wait up to 60 s - the screen shows nothing, that is normal
  4. power off, remove the card, reconnect USB, power on
  5. verify over serial at 250000 baud:

       M115        -> must report Ender3S1-F1-v2

  Full procedure and the failure ladder: docs/FLASHING.md
NEXT
