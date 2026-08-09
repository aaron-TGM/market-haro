#!/usr/bin/env bash
# Daily sync + dashboard. Point cron at this.
#   0 8 * * *  /path/to/gundam-price-radar/scripts/run_daily.sh >> /tmp/radar.log 2>&1
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "=== radar run $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
python -m radar run "$@"
