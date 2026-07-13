#!/usr/bin/env bash
# fuzz_sqlsmith.sh — point sqlsmith at the running cassert instance and let it
# generate syntactically-valid random SQL until it crashes the backend.
#
# This is the PRIMARY discovery engine. A fuzzer hits code paths you would
# never think to write a repro for. Run it for a long time (overnight) against
# the poisoned build, then triage the core dumps it leaves behind.
#
# Usage:
#   ./fuzz_sqlsmith.sh [SECONDS=3600] [DB=postgres]
#
# Requires sqlsmith on PATH (https://github.com/anse1/sqlsmith). If it is not
# installed this script prints install hints and exits 3 — it does NOT try to
# build sqlsmith for you.
#
# Crashes are detected two ways:
#   1. new core files under $PGDATA (core dump → triage_core.sh)
#   2. PANIC/"server closed the connection"/"terminating connection" in the log
#
# The instance is left running. Nothing here stops it.

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pg_env.sh
source "$HERE/pg_env.sh"

DURATION="${1:-3600}"
DB="${2:-postgres}"

if ! command -v sqlsmith >/dev/null 2>&1; then
  cat >&2 <<EOF
fuzz_sqlsmith: sqlsmith not found on PATH.

Install it (build from source — it links against libpq):
  git clone https://github.com/anse1/sqlsmith
  cd sqlsmith && autoreconf -i && ./configure && make
  # then put ./sqlsmith on PATH, or run this script with PATH including it

Alternative fuzzers if sqlsmith is unavailable:
  - SQLancer (https://github.com/sqlancer/sqlancer) — finds logic bugs, not just crashes
  - pg_amcheck / amcheck on a populated db — finds index/heap corruption
EOF
  exit 3
fi

if ! pg_isready -h "$PG_SOCK_DIR" -p "$PG_PORT" -q; then
  echo "fuzz_sqlsmith: instance not ready on port $PG_PORT — run build_and_start_pg.sh first" >&2
  exit 2
fi

# Snapshot existing cores so we only report NEW ones.
BEFORE_CORES="$(find "$PGDATA" -maxdepth 1 -name 'core*' 2>/dev/null | sort)"
STAMP="$(date +%Y%m%d-%H%M%S)"
FUZZ_LOG="$PGDATA/fuzz-${STAMP}.log"
LOG_MARK="FUZZ_START_${STAMP}"
echo "$LOG_MARK" >> "$PG_LOG"

# sqlsmith connects via libpq env / conninfo. Build a conninfo string.
CONNINFO="host=$PG_SOCK_DIR port=$PG_PORT user=$PG_USER dbname=$DB"

echo "==> sqlsmith fuzzing '$DB' for ${DURATION}s  (log: $FUZZ_LOG)"
echo "==> conninfo: $CONNINFO"
echo "    Tip: seed the db with tables first — sqlsmith is far more effective"
echo "         against a populated catalog (e.g. load the regression db)."

# --max-queries is unbounded by default; we bound by wall-clock with timeout.
# --exclude-catalog keeps it from spinning purely on catalog tables.
set +e
timeout "$DURATION" sqlsmith \
    --target="$CONNINFO" \
    --seed=1 \
    --verbose 2>&1 | tee "$FUZZ_LOG"
RC=$?
set -e
echo "FUZZ_END_${STAMP}" >> "$PG_LOG"

echo
echo "=== fuzz summary ==="
echo "sqlsmith exit: $RC  (124 = hit time limit, normal)"

# 1. New core dumps?
AFTER_CORES="$(find "$PGDATA" -maxdepth 1 -name 'core*' 2>/dev/null | sort)"
NEW_CORES="$(comm -13 <(printf '%s\n' "$BEFORE_CORES") <(printf '%s\n' "$AFTER_CORES") | grep -v '^$' || true)"
if [ -n "$NEW_CORES" ]; then
  echo
  echo "!!! NEW CORE DUMP(S) — backend crashed. Triage each:"
  while IFS= read -r c; do
    [ -n "$c" ] && echo "    $HERE/triage_core.sh '$c'"
  done <<< "$NEW_CORES"
fi

# 2. Crash markers in the server log for this window?
echo
echo "=== crash markers in server log (this run) ==="
awk -v s="$LOG_MARK" 'index($0,s){p=1} p' "$PG_LOG" 2>/dev/null \
  | grep -E 'PANIC|TRAP:|server closed the connection|terminating connection|was terminated by signal' \
  | tail -40 || echo "(none — no crash markers logged this run)"

if [ -z "$NEW_CORES" ]; then
  echo
  echo "No new cores. Either nothing crashed, or core dumps are disabled."
  echo "Check: ulimit -c  (should be 'unlimited'); on Linux see"
  echo "       /proc/sys/kernel/core_pattern. sqlsmith also logs the failing"
  echo "       query in $FUZZ_LOG — grep it for 'error' to find assertion trips."
fi
