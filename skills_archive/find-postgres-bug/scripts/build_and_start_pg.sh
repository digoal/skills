#!/usr/bin/env bash
# build_and_start_pg.sh — build PostgreSQL from source and start a local
# instance. Idempotent. The instance is INTENTIONALLY left running when
# this script exits; use stop_pg.sh to tear it down.
#
# Steps (skipped if already done):
#   1. ./configure (debug + cassert + debug-symbols)
#   2. make -j
#   3. make install (into $PG_PREFIX)
#   4. initdb (if $PGDATA/PG_VERSION missing)
#   5. configure listen + port + log
#   6. pg_ctl start
#
# Override defaults by exporting them before calling this script, e.g.:
#   PG_SRC_DIR=/path/to/pg PG_PORT=55432 ./build_and_start_pg.sh

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pg_env.sh
source "$HERE/pg_env.sh"

JOBS="${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || echo 4)}"

echo "==> Source:   $PG_SRC_DIR"
echo "==> Prefix:   $PG_PREFIX"
echo "==> Data:     $PGDATA"
echo "==> Port:     $PG_PORT"
echo "==> User:     $PG_USER"
echo "==> Configure: $PG_CONFIGURE_OPTS"
echo "==> CFLAGS:    $PG_CFLAGS"

cd "$PG_SRC_DIR"

# 0. Decide the cache-poisoning mechanism by grepping the source tree itself
#    (never assume by version number — let the tree tell us).
#      - PG14+ : runtime GUC  debug_discard_caches = 1
#      - older : compile-time -DCLOBBER_CACHE_ALWAYS
POISON_MODE="none"
if [ "${PG_POISON_CACHE:-1}" = "1" ]; then
  if grep -rq "debug_discard_caches" "$PG_SRC_DIR/src/backend/utils/cache/" 2>/dev/null; then
    POISON_MODE="guc"
  elif grep -rq "CLOBBER_CACHE_ALWAYS" "$PG_SRC_DIR/src/include/" 2>/dev/null; then
    POISON_MODE="macro"
  else
    POISON_MODE="guc"   # default for unrecognised modern trees
  fi
fi
echo "==> Cache poison: $POISON_MODE"

# 1. configure (only if Makefile.global missing)
if [ ! -f "$PG_SRC_DIR/src/Makefile.global" ]; then
  echo "==> ./configure ..."
  EXTRA_CPPFLAGS=""
  [ "$POISON_MODE" = "macro" ] && EXTRA_CPPFLAGS="-DCLOBBER_CACHE_ALWAYS"
  # shellcheck disable=SC2086
  ./configure $PG_CONFIGURE_OPTS CFLAGS="$PG_CFLAGS" ${EXTRA_CPPFLAGS:+CPPFLAGS="$EXTRA_CPPFLAGS"}
fi

# 2. build
echo "==> make -j$JOBS"
make -j"$JOBS" -s

# 3. install
echo "==> make install"
make install -s

# 4. initdb (only if not already initialised)
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  echo "==> initdb"
  mkdir -p "$PGDATA"
  initdb -D "$PGDATA" -U "$PG_USER" --auth=trust --no-locale --encoding=UTF8
fi

# 5. write minimal postgresql.conf overrides (idempotent — uses include_if_exists)
cat > "$PG_PREFIX/data.conf" <<EOF
# managed by find-postgres-bug
port = $PG_PORT
unix_socket_directories = '$PG_SOCK_DIR'
listen_addresses = '127.0.0.1'
shared_preload_libraries = ''
log_destination = 'stderr'
logging_collector = on
log_directory = 'log'
log_filename = 'server.log'
log_min_messages = debug1
log_min_error_statement = debug1
log_statement = 'all'
log_line_prefix = '%m [%p] %q%u@%d from %h '
EOF
# Runtime cache poisoning for PG14+ (the macro path is compiled in instead).
if [ "$POISON_MODE" = "guc" ]; then
  echo "debug_discard_caches = 1" >> "$PG_PREFIX/data.conf"
fi
# Make sure postgresql.conf ends with our include
if ! grep -q "include_if_exists = '$PG_PREFIX/data.conf'" "$PG_CONF" 2>/dev/null; then
  echo "" >> "$PG_CONF"
  echo "include_if_exists = '$PG_PREFIX/data.conf'" >> "$PG_CONF"
fi

# 5b. Enable core dumps so a crash leaves an artifact for triage_core.sh.
#     ulimit only affects children started from THIS shell's pg_ctl.
ulimit -c unlimited 2>/dev/null || true

# 6. start (idempotent — skip if already running)
if pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
  echo "==> PG already running (pid: $(pg_ctl -D "$PGDATA" status | awk '/PID/ {print $NF}'))"
else
  echo "==> pg_ctl start"
  pg_ctl -D "$PGDATA" -l "$PG_LOG" -o "-p $PG_PORT -k $PG_SOCK_DIR" start
  # wait for readiness
  for i in $(seq 1 30); do
    if pg_isready -h /tmp -p "$PG_PORT" -q; then break; fi
    sleep 0.5
  done
fi

echo
echo "==> PG UP on port $PG_PORT  (log: $PG_LOG)"
echo "    Connect:  psql -h /tmp -p $PG_PORT -U $PG_USER -d postgres"
echo "    Fuzz:     $HERE/fuzz_sqlsmith.sh"
echo "    Stop:     $HERE/stop_pg.sh"
if [ "$POISON_MODE" = "none" ]; then
  echo
  echo "    NOTE: cache poisoning is OFF (PG_POISON_CACHE=0). You will find"
  echo "          far fewer bugs. Re-run with PG_POISON_CACHE=1 to enable it."
fi
