#!/usr/bin/env bash
# Start the firmware configurator with one command.
#
#   ./scripts/configurator.sh                 # start it, open the browser
#   ./scripts/configurator.sh --no-open       # start it, print the URL only
#   ./scripts/configurator.sh --port=9000     # another port
#   ./scripts/configurator.sh --no-bootstrap  # fail instead of bootstrapping
#
# The first run bootstraps the pinned tree and PlatformIO (a few minutes); after
# that it starts in about a second. Ctrl+C stops the service.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${CONFIGURATOR_PORT:-8787}"
OPEN=1
BOOTSTRAP=1

for arg in "$@"; do
  case "$arg" in
    --port=*)        PORT="${arg#*=}" ;;
    --no-open)       OPEN=0 ;;
    --no-bootstrap)  BOOTSTRAP=0 ;;
    -h|--help)
      sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      echo "unknown option: $arg (try --help)" >&2
      exit 2 ;;
  esac
done

URL="http://127.0.0.1:$PORT"

probe() {
  if command -v curl >/dev/null 2>&1; then
    curl -sf -m 2 -o /dev/null "$URL/api/catalog"
  else
    python3 - "$URL" <<'PY'
import sys, urllib.request
try:
    urllib.request.urlopen(sys.argv[1] + "/api/catalog", timeout=2).read(1)
except Exception:
    sys.exit(1)
PY
  fi
}

if probe; then
  echo "already running at $URL"
  exit 0
fi

if [ ! -x build/.venv/bin/platformio ]; then
  if [ "$BOOTSTRAP" = 1 ]; then
    echo "first run: bootstrapping the pinned tree and PlatformIO (this takes a few minutes)"
    ./scripts/bootstrap.sh
  else
    echo "no toolchain yet - run ./scripts/bootstrap.sh first, or drop --no-bootstrap" >&2
    exit 1
  fi
fi

echo "starting the configurator on $URL"
CONFIGURATOR_PORT="$PORT" python3 tools/configurator/server.py &
SERVER=$!

cleanup() {
  kill "$SERVER" 2>/dev/null || true
  wait "$SERVER" 2>/dev/null || true
}
trap cleanup INT TERM

for _ in $(seq 1 40); do
  if probe; then break; fi
  if ! kill -0 "$SERVER" 2>/dev/null; then
    echo "the service exited - see the log above" >&2
    exit 1
  fi
  sleep 0.5
done

if ! probe; then
  echo "the service did not answer on $URL after 20 s" >&2
  exit 1
fi

if [ "$OPEN" = 1 ]; then
  for opener in xdg-open gio open; do
    if command -v "$opener" >/dev/null 2>&1; then
      if [ "$opener" = gio ]; then gio open "$URL" >/dev/null 2>&1 || true
      else "$opener" "$URL" >/dev/null 2>&1 || true; fi
      break
    fi
  done
fi

cat <<EOF

  configurator : $URL
  catalogue    : 71 features, measured costs
  build tree   : ready
  stop with    : Ctrl+C

EOF

wait "$SERVER"

