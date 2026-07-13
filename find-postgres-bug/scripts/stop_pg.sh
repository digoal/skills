#!/usr/bin/env bash
# stop_pg.sh — explicit teardown. NOT called by any other script in this
# skill. Use only when you are done testing.

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pg_env.sh
source "$HERE/pg_env.sh"

if pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
  pg_ctl -D "$PGDATA" -m fast stop
  echo "stopped."
else
  echo "not running."
fi
