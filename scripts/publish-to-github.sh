#!/usr/bin/env bash
# Publish this repository to GitHub.
#
# Usage:  scripts/publish-to-github.sh [--private]
#
# Idempotent: creates the repository when it is missing, pushes main when it is
# not. It never force-pushes and never rewrites history.
set -euo pipefail

REPO_SLUG="darthinvader/Ender3S1Firmware"
DESCRIPTION="Ender 3 S1 firmware: mriscoc ProUI build, exact configs, measured feature budget and a local configurator that compiles and writes the card."
VISIBILITY="--public"
if [ $# -gt 0 ] && [ "$1" = "--private" ]; then VISIBILITY="--private"; fi

cd "$(dirname "$0")/.."

echo "== repository =="
git remote get-url origin >/dev/null 2>&1 || git remote add origin "git@github.com:$REPO_SLUG.git"
git remote set-url origin "git@github.com:$REPO_SLUG.git"
git remote -v | head -2

echo
echo "== GitHub CLI =="
if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
  echo "authenticated as $(gh api user --jq .login)"
  if ! gh repo view "$REPO_SLUG" >/dev/null 2>&1; then
    echo "creating $REPO_SLUG ..."
    gh repo create "$REPO_SLUG" $VISIBILITY --description "$DESCRIPTION" --source . --remote origin --disable-wiki
  else
    echo "$REPO_SLUG already exists"
  fi
  echo "pushing main ..."
  git push -u origin main
  gh repo edit "$REPO_SLUG" --add-topic 3d-printing --add-topic marlin --add-topic firmware \
    --add-topic ender3s1 --add-topic platformio --add-topic stm32f103 || true
  echo "done: https://github.com/$REPO_SLUG"
  exit 0
fi

echo "gh is not authenticated (or not installed), so the repository cannot be created here."
if git ls-remote "git@github.com:$REPO_SLUG.git" >/dev/null 2>&1; then
  echo "the repository exists: pushing"
  git push -u origin main
  echo "done: https://github.com/$REPO_SLUG"
  exit 0
fi

cat <<'MSG'

Two ways forward, pick one:

  A. create the empty repository in the browser, then re-run this script
     https://github.com/new?name=Ender3S1Firmware
     (leave it COMPLETELY empty: no README, no .gitignore, no licence)

  B. authenticate the GitHub CLI once, then re-run this script
     gh auth login
     it will create the repository, set the description and topics, and push

Nothing is pushed until one of those is done; this script only reads state.
MSG
exit 1
