#!/usr/bin/env bash
# Serve the configurator to the public.
#
# Starts the local service, opens a Cloudflare quick tunnel (no account needed),
# and writes the tunnel URL to docs/cloud/backend.json so the Pages build page
# talks to this machine instead of asking visitors for a GitHub account.
#
#   scripts/serve-public.sh            start, print the URL
#   scripts/serve-public.sh --stop     stop the tunnel
#
# The URL belongs to this machine: if the machine sleeps or the script restarts,
# the hostname changes and the page falls back to its offline notice.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${CONFIGURATOR_PORT:-8787}"
CLOUDFLARED="${CLOUDFLARED:-$HOME/.local/bin/cloudflared}"
STATE="$ROOT/docs/cloud/backend.json"

if [ "${1:-}" = "--stop" ]; then
  pkill -f "cloudflared tunnel --url http://127.0.0.1:$PORT" 2>/dev/null || true
  printf '{}\n' > "$STATE"
  echo "tunnel stopped; the page will show the builder as offline"
  exit 0
fi

if [ ! -x "$CLOUDFLARED" ]; then
  echo "cloudflared is missing: downloading it once to ~/.local/bin" >&2
  mkdir -p "$(dirname "$CLOUDFLARED")"
  curl -fsSL -o "$CLOUDFLARED" \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x "$CLOUDFLARED"
fi

if ! curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/catalog"; then
  echo "starting the configurator on 127.0.0.1:$PORT" >&2
  ( cd "$ROOT" && CONFIGURATOR_PORT="$PORT" python3 tools/configurator/server.py > "$ROOT/build/configurator-public.log" 2>&1 & )
  for _ in $(seq 1 40); do
    curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/catalog" && break
    sleep 0.5
  done
fi

LOG="$(mktemp)"
"$CLOUDFLARED" tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate > "$LOG" 2>&1 &
TUNNEL_PID=$!
trap 'kill $TUNNEL_PID 2>/dev/null || true' EXIT

URL=""
for _ in $(seq 1 60); do
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOG" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] || { echo "the tunnel did not come up; see $LOG" >&2; exit 1; }

python3 - "$URL" "$STATE" <<'PY'
import json, sys, datetime
url, state = sys.argv[1], sys.argv[2]
open(state, "w").write(json.dumps({
    "url": url,
    "started": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "note": "open while this machine serves; the page hides the builder when it is gone",
}, indent=2) + "\n")
PY

echo "serving: $URL"
echo "the page uses it as soon as docs/cloud is published"
echo "leave this running; Ctrl+C stops the tunnel"
wait $TUNNEL_PID

