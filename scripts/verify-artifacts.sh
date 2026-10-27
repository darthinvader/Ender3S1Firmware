#!/usr/bin/env bash
#
# verify-artifacts.sh - prove the committed binaries are what they claim to be.
#
#  1. every file listed in firmware/SHA256SUMS and screen/SHA256SUMS matches
#  2. every committed .bin has a plausible ARM Cortex-M vector table for a board
#     with a 28 KiB bootloader (initial SP in SRAM, reset handler at or above
#     the 0x08007000 application base)
#  3. the shipped configuration still carries the features the README claims
#
# Run after cloning, after moving files around, and in CI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
rc=0

printf '\n==> checksums\n'
for sums in firmware/SHA256SUMS screen/SHA256SUMS; do
  if [ ! -f "$sums" ]; then
    printf '    missing %s\n' "$sums" >&2
    rc=1
    continue
  fi
  if (cd "$(dirname "$sums")" && sha256sum -c "$(basename "$sums")" --quiet); then
    printf '    %-22s OK\n' "$sums"
  else
    printf '    %-22s FAILED\n' "$sums" >&2
    rc=1
  fi
done

printf '\n==> vector tables\n'
shopt -s globstar nullglob
for bin in firmware/**/*.bin; do
  if python3 scripts/check-vector-table.py "$bin" >/dev/null; then
    printf '    %-58s OK\n' "$bin"
  else
    printf '    %-58s FAILED\n' "$bin" >&2
    python3 scripts/check-vector-table.py "$bin" | sed 's/^/        /' >&2
    rc=1
  fi
done

printf '\n==> configuration sanity\n'
fail() { printf '    %-34s FAILED: %s\n' "$1" "$2" >&2; rc=1; }
pass() { printf '    %-34s OK\n' "$1"; }
check() {
  if grep -qE "$2" "$1"; then pass "$3"; else fail "$3" "not found in $1"; fi
}

CFG="configs/Ender3S1-F1-v2/Configuration.h"
ADV="configs/Ender3S1-F1-v2/Configuration_adv.h"
check "$CFG" '^[[:space:]]*#define CUSTOM_MACHINE_NAME "Ender3S1-F1-v2"' 'machine identity'
check "$CFG" '^[[:space:]]*#define MOTHERBOARD BOARD_CREALITY_V24S1_301' 'board V24S1_301'
check "$CFG" '^[[:space:]]*#define AUTO_BED_LEVELING_UBL' 'UBL'
check "$CFG" '^[[:space:]]*#define GRID_MAX_POINTS_X 7' '7x7 mesh'
check "$CFG" '^[[:space:]]*#define TEMP_SENSOR_0 1' 'stock thermistor'
check "$CFG" '^[[:space:]]*#define BLTOUCH' 'CR Touch driver'
check "$CFG" '^[[:space:]]*#define NOZZLE_TO_PROBE_OFFSET \{ -31.8, -40.5, 0 \}' 'probe offsets'
check "$ADV" '^[[:space:]]*#define INPUT_SHAPING_X' 'input shaping X'
check "$ADV" '^[[:space:]]*#define LIN_ADVANCE' 'linear advance'
check "$ADV" '^[[:space:]]*#define SMOOTH_LIN_ADVANCE' 'smooth linear advance'
check "$ADV" '^[[:space:]]*#define BINARY_FILE_TRANSFER' 'binary file transfer'

if [ "$rc" -eq 0 ]; then
  printf '\nall checks passed\n'
else
  printf '\nchecks FAILED\n' >&2
fi
exit "$rc"
