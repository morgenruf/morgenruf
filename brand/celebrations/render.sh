#!/usr/bin/env bash
# Renders banners.html to out/<id>.png: 1200x600 CSS pixels at 2x (2400x1200).
# Pass ids, or none for all.
set -uo pipefail
cd "$(dirname "$0")"
mkdir -p out
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ids=("$@")
[ ${#ids[@]} -eq 0 ] && ids=(birthday-{1..8} anniversary-{1..8})
for b in "${ids[@]}"; do
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files --virtual-time-budget=8000 \
    --force-device-scale-factor=2 --window-size=1200,600 --screenshot="out/$b.png" "file://$PWD/banners.html?b=$b" 2>/dev/null
done
