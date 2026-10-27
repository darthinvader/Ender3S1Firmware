#!/usr/bin/env bash
#
# build.sh - compile one firmware variant and stage the binary in build/out/.
#
# Usage:
#   ./scripts/build.sh [variant]
#
# Requires ./scripts/bootstrap.sh to have run first.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VARIANT="Ender3S1-F1-v2"
if [ "$#" -ge 1 ]; then VARIANT="$1"; fi
BUILD="$ROOT/build"
PIO="$BUILD/.venv/bin/platformio"
ENVNAME="STM32F103RC_creality"

[ -d "$BUILD/Ender3V2S1" ] || { echo "error: no build tree, run ./scripts/bootstrap.sh first" >&2; exit 1; }
[ -x "$PIO" ] || { echo "error: no PlatformIO virtualenv, run ./scripts/bootstrap.sh first" >&2; exit 1; }

mkdir -p "$BUILD/logs"
printf '\n==> building %s (env %s)\n' "$VARIANT" "$ENVNAME"
(cd "$BUILD/Ender3V2S1" && "$PIO" run -e "$ENVNAME") 2>&1 | tee "$BUILD/logs/build-$VARIANT.log"

BINDIR="$BUILD/Ender3V2S1/.pio/build/$ENVNAME"
LATEST="$(ls -1t "$BINDIR"/firmware-*.bin 2>/dev/null | head -n 1 || true)"
[ -n "$LATEST" ] || LATEST="$BINDIR/firmware.bin"
[ -f "$LATEST" ] || { echo "error: no firmware binary produced" >&2; exit 1; }

mkdir -p "$BUILD/out"
OUT="$BUILD/out/$VARIANT-$(date +%Y%m%d-%H%M%S).bin"
cp "$LATEST" "$OUT"

printf '\n==> staged %s\n' "$OUT"
printf '    size    %s bytes\n' "$(stat -c %s "$OUT")"
printf '    md5     %s\n' "$(md5sum "$OUT" | cut -d" " -f1)"
printf '    sha256  %s\n' "$(sha256sum "$OUT" | cut -d" " -f1)"
printf '    vector table:\n'
python3 "$ROOT/scripts/check-vector-table.py" "$OUT" | sed 's/^/    /'
printf '\nReminder: binaries embed the build date/time, so compare a rebuild by\n'
printf 'flash size and M115 output, not by hash. See docs/BUILD.md.\n'
