#!/usr/bin/env bash
# Publish the site and its build function to Cloudflare Pages.
#
#   CLOUDFLARE_API_TOKEN=... scripts/deploy-cloudflare-pages.sh
#   CLOUDFLARE_API_TOKEN=... GH_TOKEN=... scripts/deploy-cloudflare-pages.sh
#
# The token needs Account -> Cloudflare Pages: Edit. GH_TOKEN (optional here) is
# the repository-scoped GitHub token the function uses to dispatch the workflow;
# without it, published selections still answer, but new ones cannot build.
set -euo pipefail

: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN (Account -> Cloudflare Pages: Edit)}"
PROJECT="${PROJECT:-ender3s1-firmware}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -d functions ] || [ ! -d docs/cloud ]; then
  echo "run this from the repository: functions/ and docs/cloud/ must exist" >&2
  exit 1
fi

echo "== account =="
curl -fsS -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  https://api.cloudflare.com/client/v4/accounts \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print('  ', a['id'], a['name']) for a in d.get('result', [])]"

echo "== project =="
npx --yes wrangler@latest pages project create "$PROJECT" --production-branch=main \
  --compatibility-date=2026-10-01 2>&1 | tail -3 || true

echo "== deploy =="
npx --yes wrangler@latest pages deploy docs --project-name "$PROJECT" --branch main \
  --commit-dirty=true 2>&1 | tail -6

if [ -n "${GH_TOKEN:-}" ]; then
  echo "== secret =="
  printf '%s' "$GH_TOKEN" | npx --yes wrangler@latest pages secret put GH_TOKEN --project-name "$PROJECT" 2>&1 | tail -3
fi

echo "== check =="
sleep 5
curl -s -o /dev/null -w "  site  /cloud/ : %{http_code}\n" "https://$PROJECT.pages.dev/cloud/"
curl -s -o /dev/null -w "  api   /build : %{http_code}\n" "https://$PROJECT.pages.dev/api/build/build-000000000000"

