#!/usr/bin/env bash
# Collect new papers and publish them to GitHub Pages.
# Meant for a daily cron job on the lab server: while the initial sweep is running it uses
# the daily API budget, afterwards it only does work every 28 days (monthly update).
#
#   17 6 * * *  /path/to/adc-census/scripts/update.sh >> /path/to/adc-census/logs/update.log 2>&1
#
# Environment (optional): PYTHON (default python3), MIN_INTERVAL_DAYS (default 28).
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"

if [ -f "$HOME/.config/adc-census/env" ]; then
  set -a; . "$HOME/.config/adc-census/env"; set +a
fi

echo "=== $(date '+%F %T') ==="
git pull --rebase --quiet origin main || { echo "git pull failed"; exit 1; }

"$PY" collector/collect.py --min-interval-days "${MIN_INTERVAL_DAYS:-28}" "$@"
status=$?   # 0 = ok, 3 = daily API budget used up (progress saved), anything else = error

# Murmann survey for the plots (GitHub download, refreshed when the local copy is over a week old)
"$PY" collector/murmann.py || echo "murmann survey refresh failed; keeping the previous data/murmann.json"

git add data/papers.json data/meta.json data/state.json data/murmann.json
if ! git diff --cached --quiet; then
  n=$("$PY" -c "import json;print(json.load(open('data/meta.json')).get('total',0))")
  git commit --quiet -m "data: update $(date +%F) ($n papers)"
  # someone may have edited annotations.csv on the web meanwhile: rebase once and retry
  if git push --quiet origin main || { git pull --rebase --quiet origin main && git push --quiet origin main; }; then
    echo "pushed ($n papers)"
  else
    echo "git push failed"; status=1
  fi
else
  echo "no changes"
fi

[ "$status" -eq 3 ] && exit 0
exit "$status"
