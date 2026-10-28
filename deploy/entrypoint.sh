#!/usr/bin/env bash
set -euo pipefail

cd /app

if [ ! -f build/Ender3V2S1/Marlin/Configuration.h ]; then
  if [ "${SKIP_BOOTSTRAP:-0}" = "1" ]; then
    echo "entrypoint: no pinned tree and SKIP_BOOTSTRAP=1 - serving the UI only"
  else
    echo "entrypoint: first run, bootstrapping the pinned tree (a few minutes)"
    ./scripts/bootstrap.sh
  fi
fi

exec python3 tools/configurator/server.py
