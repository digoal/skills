#!/usr/bin/env bash
# triage_core.sh — turn a backend core dump into a readable backtrace, the
# first step of triage. The point is to get a stack so you can find the
# failing query and minimise it into an MRE (minimal reproducible example).
#
# Usage:
#   ./triage_core.sh <core-file> [backend-binary]
#
# Defaults the backend binary to $PGBIN/postgres. Uses lldb on macOS, gdb on
# Linux (both produce a full backtrace of all threads).
#
# Rule of triage: do NOT theorise about the root cause from the backtrace
# alone, and do NOT start editing C. The backtrace tells you WHERE; you still
# need a minimal SQL that reproduces it on demand before any fix discussion.

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pg_env.sh
source "$HERE/pg_env.sh"

CORE="${1:?usage: triage_core.sh <core-file> [backend-binary]}"
BIN="${2:-$PGBIN/postgres}"

[ -f "$CORE" ] || { echo "triage_core: core '$CORE' not found" >&2; exit 2; }
[ -x "$BIN" ]  || { echo "triage_core: backend binary '$BIN' not found" >&2; exit 2; }

echo "==> core:    $CORE"
echo "==> binary:  $BIN"
echo

OS="$(uname -s)"
if [ "$OS" = "Darwin" ]; then
  if ! command -v lldb >/dev/null 2>&1; then
    echo "triage_core: lldb not found (install Xcode command line tools)" >&2
    exit 3
  fi
  echo "=== lldb backtrace (all threads) ==="
  lldb -c "$CORE" "$BIN" \
    -o "bt all" \
    -o "frame variable" \
    -o "quit" 2>&1
else
  if ! command -v gdb >/dev/null 2>&1; then
    echo "triage_core: gdb not found (apt/yum install gdb)" >&2
    exit 3
  fi
  echo "=== gdb backtrace (all threads) ==="
  gdb -batch -nx \
    -ex "set pagination off" \
    -ex "thread apply all bt full" \
    -ex "quit" \
    "$BIN" "$CORE" 2>&1
fi

cat <<'EOF'

=== next steps (triage, not fixing) ===
1. Read the top non-library frames — that is the failing function + line.
2. Find the query that triggered it: grep the fuzz log / server log near the
   crash timestamp for the last STATEMENT before the PANIC/TRAP.
3. Minimise it into an MRE: strip the query down to the fewest lines that still
   crash a fresh backend. Save it as repro/<name>.sql and confirm with
   run_repro.sh that it crashes on demand.
4. Only once you have a deterministic MRE: bisect_run.sh to find the commit,
   then gen_bug_report.sh. Do NOT write a patch — report the MRE upstream.
EOF
