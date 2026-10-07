#!/bin/bash
# Daily: rebuild the shop pages and catalog.csv from the live Etsy listings,
# and publish only if something changed. Run by launchd
# (~/Library/LaunchAgents/com.kirwana.mirrors-catalog.plist); log in tools/sync.log.
cd "$(dirname "$0")/.." || exit 1
echo "== $(date '+%Y-%m-%d %H:%M')"
/usr/bin/git pull -q --rebase || echo "pull failed; building on what is here"
/usr/bin/python3 tools/build_catalog.py || { echo "build failed"; exit 1; }
if [ -z "$(/usr/bin/git status --porcelain -- p shop.html catalog.csv)" ]; then
  echo "no change"
  exit 0
fi
/usr/bin/git add -A p shop.html catalog.csv
/usr/bin/git commit -q -m "Shop: synced with Etsy $(date '+%Y-%m-%d')"
/usr/bin/git push -q && echo "published" || echo "push failed"
