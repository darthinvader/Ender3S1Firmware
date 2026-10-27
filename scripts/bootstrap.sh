#!/usr/bin/env bash
#
# bootstrap.sh - create the from-scratch build tree for one firmware variant.
#
# Clones the two pinned upstream repositories into ./build/, copies this
# repository's configuration files into the Marlin tree, applies the source
# patches and prepares a Python virtualenv with the exact PlatformIO release
# that produced the shipped binaries.
#
# Usage:
#   ./scripts/bootstrap.sh [variant]
#
#   variant  Ender3S1-F1-v2                  (default, the shipped build)
#            Ender3S1-F1-UBL-IS-LA-MPC-BFT    (previous build, restore point)
#
# Requires: git, python3 (>=3.8), network access for the clone and the
# PlatformIO package download.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VARIANT="Ender3S1-F1-v2"
if [ "$#" -ge 1 ]; then VARIANT="$1"; fi
BUILD="$ROOT/build"

MARLIN_REPO="https://github.com/mriscoc/Ender3V2S1.git"
MARLIN_SHA="ffe684b68bc5ce7d273079df4da7730065277e70"
CFG_REPO="https://github.com/mriscoc/Special_Configurations.git"
CFG_SHA="0d422ac4425d12f7f0e1acf41f76ec308aa5b684"
PIO_VERSION="6.1.19"

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

case "$VARIANT" in
  Ender3S1-F1-v2|Ender3S1-F1-UBL-IS-LA-MPC-BFT) ;;
  *) die "unknown variant: $VARIANT (see configs/ for the available sets)" ;;
esac

for tool in git python3; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is required but not installed"
done

say "build tree: $BUILD"
mkdir -p "$BUILD"

clone_pinned() {
  local url="$1" sha="$2" dir="$3"
  if [ -d "$dir/.git" ]; then
    local have
    have="$(git -C "$dir" rev-parse HEAD)"
    if [ "$have" = "$sha" ]; then
      say "$(basename "$dir") already pinned at $sha"
      return
    fi
    say "$(basename "$dir") present, checking out $sha"
    git -C "$dir" fetch --quiet origin
    git -C "$dir" checkout --quiet --force "$sha"
    git -C "$dir" clean -qfdx -e .pio
  else
    say "cloning $(basename "$dir")"
    git clone --quiet "$url" "$dir"
    git -C "$dir" checkout --quiet "$sha"
  fi
}

clone_pinned "$MARLIN_REPO" "$MARLIN_SHA" "$BUILD/Ender3V2S1"
clone_pinned "$CFG_REPO" "$CFG_SHA" "$BUILD/Special_Configurations"

say "installing configuration set: $VARIANT"
for f in Configuration.h Configuration_adv.h Version.h; do
  cp "$ROOT/configs/$VARIANT/$f" "$BUILD/Ender3V2S1/Marlin/$f"
  printf '    Marlin/%-20s <- configs/%s/%s\n' "$f" "$VARIANT" "$f"
done

say "applying source patches"
for p in "$ROOT"/configs/patches/0002-*.patch; do
  [ -e "$p" ] || continue
  if git -C "$BUILD/Ender3V2S1" apply --reverse --check "$p" >/dev/null 2>&1; then
    printf '    %s already applied\n' "$(basename "$p")"
  else
    git -C "$BUILD/Ender3V2S1" apply "$p"
    printf '    %s applied\n' "$(basename "$p")"
  fi
done

say "preparing PlatformIO $PIO_VERSION in build/.venv"
if [ ! -x "$BUILD/.venv/bin/platformio" ]; then
  python3 -m venv "$BUILD/.venv"
  "$BUILD/.venv/bin/python" -m pip install --quiet --upgrade pip
  "$BUILD/.venv/bin/python" -m pip install --quiet "platformio==$PIO_VERSION"
fi
"$BUILD/.venv/bin/platformio" --version

say "ready"
cat <<'NOTE'
Next:

    ./scripts/build.sh [variant]     compile the firmware
    ./scripts/verify-artifacts.sh    verify the committed binaries

The build tree lives in ./build/ and is ignored by git.
NOTE
