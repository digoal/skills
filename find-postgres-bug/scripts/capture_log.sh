#!/usr/bin/env bash
# capture_log.sh — print recent server log lines + a filtered
# ERROR/FATAL/PANIC/WARNING view.
#
# Usage: ./capture_log.sh [N=200]   (last N lines of raw log)
#        ./capture_log.sh errors     (only ERROR/FATAL/PANIC)
#        ./capture_log.sh full       (whole log)

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pg_env.sh
source "$HERE/pg_env.sh"

MODE="${1:-tail}"
N="${2:-200}"

if [ ! -f "$PG_LOG" ]; then
  echo "capture_log: $PG_LOG not found" >&2
  exit 1
fi

case "$MODE" in
  tail)
    echo "=== last $N lines of $PG_LOG ==="
    tail -n "$N" "$PG_LOG"
    ;;
  errors)
    echo "=== ERROR/FATAL/PANIC/WARNING (last 200 matches) ==="
    grep -E '^(ERROR|FATAL|PANIC|WARNING):' "$PG_LOG" | tail -n 200
    ;;
  full)
    cat "$PG_LOG"
    ;;
  *)
    echo "usage: $0 [tail|errors|full] [N]" >&2
    exit 2
    ;;
esac
