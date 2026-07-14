#!/usr/bin/env bash
# run_repro.sh — execute a .sql repro file against the running instance,
# capture stdout, then dump the most recent ERROR/FATAL/PANIC/WARNING
# lines from the server log.
#
# Usage: ./run_repro.sh <file.sql> [label]
#
# Returns non-zero if psql returned non-zero OR if any ERROR/FATAL/PANIC
# appeared in the log during/after the run. This is intentional: a
# successful run means "no bug observed on this input".

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pg_env.sh
source "$HERE/pg_env.sh"

SQL="${1:?usage: run_repro.sh <file.sql> [label]}"
LABEL="${2:-$(basename "$SQL" .sql)}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$PGDATA/repro-${LABEL}-${STAMP}.log"

if [ ! -f "$SQL" ]; then
  echo "run_repro: $SQL not found" >&2
  exit 2
fi

# Mark the log so we know where this run starts.
LOG_MARK="REPRO_START_${LABEL}_${STAMP}"
echo "==> $LOG_MARK"
echo "$LOG_MARK" >> "$PG_LOG"

echo "==> psql $SQL  →  $OUT"
set +e
psql -h "$PG_SOCK_DIR" -p "$PG_PORT" -U "$PG_USER" -d postgres -X -e \
     -v ON_ERROR_STOP=0 -f "$SQL" 2>&1 | tee "$OUT"
PSQL_RC=$?
set -e

# Append mark so we can scope log capture
END_MARK="REPRO_END_${LABEL}_${STAMP}"
echo "$END_MARK" >> "$PG_LOG"

echo
echo "=== server log slice for this run ==="
awk -v start="$LOG_MARK" -v end="$END_MARK" \
  'index($0, start) {p=1; next} index($0, end) {p=0} p' \
  "$PG_LOG" 2>/dev/null | grep -E '^(ERROR|FATAL|PANIC|WARNING|STATEMENT|LOG:)' | tail -80 \
  || true

# Did the backend crash? For crash-class bugs this is the real signal —
# the server going away matters more than any single ERROR line.
if ! pg_isready -h "$PG_SOCK_DIR" -p "$PG_PORT" -q; then
  echo
  echo "!!! SERVER IS DOWN after this repro — likely a crash. Look for a core:"
  echo "    find $PGDATA -maxdepth 1 -name 'core*'"
  echo "    then: $HERE/triage_core.sh <core>"
  exit 1
fi
if awk -v s="$LOG_MARK" 'index($0,s){p=1} p' "$PG_LOG" 2>/dev/null \
     | grep -qE 'PANIC|TRAP:|was terminated by signal'; then
  echo
  echo "!!! PANIC/TRAP/signal in log for this run — crash-class bug. Triage the core."
  exit 1
fi

if [ "$PSQL_RC" -ne 0 ]; then
  echo
  echo "psql returned $PSQL_RC"
  exit "$PSQL_RC"
fi
