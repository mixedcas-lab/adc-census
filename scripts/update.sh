#!/usr/bin/env bash
# Collect new papers and publish them to GitHub Pages.
# Meant for a daily cron job on the lab server: while the initial sweep is running it uses
# the daily API budget, afterwards it only does work every 28 days (monthly update).
#
#   17 6 * * *  /path/to/adc-census/scripts/update.sh >> /path/to/adc-census/logs/update.log 2>&1
set -uo pipefail
cd "$(dirname "$0")/.."

if [ -f "$HOME/.config/adc-census/env" ]; then
  set -a; . "$HOME/.config/adc-census/env"; set +a
fi

echo "=== $(date '+%F %T') ==="
git pull --rebase --quiet origin main || { echo "git pull failed"; exit 1; }

python3 collector/collect.py --min-interval-days "${MIN_INTERVAL_DAYS:-28}" "$@"
status=$?   # 0 = ok, 3 = daily API budget used up (progress saved), anything else = error

git add data/papers.json data/meta.json data/state.json
if ! git diff --cached --quiet; then
  n=$(python3 -c "import json;print(json.load(open('data/meta.json')).get('total',0))")
  git commit --quiet -m "data: update $(date +%F) ($n papers)"
  git push --quiet origin main && echo "pushed ($n papers)"
else
  echo "no changes"
fi

[ "$status" -eq 3 ] && exit 0
exit "$status"
