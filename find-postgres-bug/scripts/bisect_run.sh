#!/usr/bin/env bash
# bisect_run.sh — git-bisect the commit that introduced a crash, driven by a
# deterministic MRE. Only run this AFTER you have an MRE that reliably crashes
# the backend (triage_core.sh → minimised repro/<name>.sql).
#
# Usage:
#   ./bisect_run.sh <repro.sql> <good-ref> <bad-ref>
#     <good-ref>  a commit/tag where the MRE does NOT crash (e.g. an old tag)
#     <bad-ref>   a commit where it DOES crash (usually HEAD)
#
# How it works: it writes a per-step test that rebuilds, restarts, runs the
# MRE, and reports crash-vs-clean to `git bisect run`. Rebuilds are slow, so
# this can take a while — that's expected; bisect is log2(N) steps.
#
# A "crash" = backend dies (psql loses the connection) OR a new core appears OR
# a PANIC/TRAP is logged. A clean run (even with a plain SQL ERROR) = good.
#
# This script SExits leaving the tree on the first-bad commit (git bisect's
# resting state) and prints it. It does NOT reset the bisect — run
# `git -C $PG_SRC_DIR bisect reset` yourself when done inspecting.

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pg_env.sh
source "$HERE/pg_env.sh"

SQL="${1:?usage: bisect_run.sh <repro.sql> <good-ref> <bad-ref>}"
GOOD="${2:?need a good ref}"
BAD="${3:?need a bad ref}"
SQL="$(cd "$(dirname "$SQL")" && pwd)/$(basename "$SQL")"  # absolutise

[ -f "$SQL" ] || { echo "bisect_run: repro '$SQL' not found" >&2; exit 2; }

cd "$PG_SRC_DIR"
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "bisect_run: working tree is dirty. Commit/stash first — bisect checks out commits." >&2
  exit 2
fi

# Per-step test script. Exit 0 = good (no crash), 1 = bad (crash),
# 125 = skip (build failed → can't judge this commit).
STEP="$(mktemp /tmp/pgbisect-step.XXXXXX.sh)"
cat > "$STEP" <<STEPEOF
#!/usr/bin/env bash
set -uo pipefail
source "$HERE/pg_env.sh"
cd "$PG_SRC_DIR"

# Clean rebuild for this commit. If configure/make fails, skip the commit.
if [ ! -f src/Makefile.global ]; then
  ./configure \$PG_CONFIGURE_OPTS CFLAGS="\$PG_CFLAGS" >/tmp/pgbisect-configure.log 2>&1 || exit 125
fi
make -j"\${JOBS:-4}" -s >/tmp/pgbisect-make.log 2>&1 || { make distclean >/dev/null 2>&1 || true; exit 125; }
make install -s >>/tmp/pgbisect-make.log 2>&1 || exit 125

# Fresh data dir each step — on-disk format changes across commits would
# otherwise wedge initdb/startup.
rm -rf "\$PGDATA"
initdb -D "\$PGDATA" -U "\$PG_USER" --auth=trust --no-locale --encoding=UTF8 >/tmp/pgbisect-initdb.log 2>&1 || exit 125
{
  echo "port = \$PG_PORT"
  echo "unix_socket_directories = '\$PG_SOCK_DIR'"
  echo "listen_addresses = '127.0.0.1'"
  [ "\${PG_POISON_CACHE:-1}" = "1" ] && echo "debug_discard_caches = 1"
} >> "\$PGDATA/postgresql.conf"

ulimit -c unlimited 2>/dev/null || true
pg_ctl -D "\$PGDATA" -o "-p \$PG_PORT -k \$PG_SOCK_DIR" -w -t 60 start >/tmp/pgbisect-start.log 2>&1 || exit 125

# Run the MRE. We care only whether the SERVER survived.
psql -h "\$PG_SOCK_DIR" -p "\$PG_PORT" -U "\$PG_USER" -d postgres -X -v ON_ERROR_STOP=0 \
     -f "$SQL" >/tmp/pgbisect-psql.log 2>&1
# Did the server survive? A crash makes pg_isready fail.
if pg_isready -h "\$PG_SOCK_DIR" -p "\$PG_PORT" -q; then
  VERDICT=0   # good: server still up
else
  VERDICT=1   # bad: server died
fi
# Also treat logged PANIC/TRAP as bad even if it auto-restarted.
if grep -qE 'PANIC|TRAP:|was terminated by signal' "\$PGDATA"/log/*.log 2>/dev/null; then
  VERDICT=1
fi

pg_ctl -D "\$PGDATA" -m immediate stop >/dev/null 2>&1 || true
exit \$VERDICT
STEPEOF
chmod +x "$STEP"

echo "==> git bisect start (bad=$BAD good=$GOOD)"
git bisect reset >/dev/null 2>&1 || true
git bisect start "$BAD" "$GOOD"

echo "==> git bisect run (each step rebuilds — be patient)"
git bisect run "$STEP" | tee /tmp/pgbisect-run.log

echo
echo "=== first-bad commit ==="
grep -E 'is the first bad commit' -A 20 /tmp/pgbisect-run.log || true
echo
echo "Tree is parked on the bisect result. When done:"
echo "    git -C $PG_SRC_DIR bisect reset"
echo "Step script kept at: $STEP  (per-step logs in /tmp/pgbisect-*.log)"
