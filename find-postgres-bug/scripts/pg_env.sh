# pg_env.sh — sourceable env for find-postgres-bug.
#
# All other scripts in this skill source this file. Override defaults
# BEFORE sourcing, e.g.:
#
#   PG_SRC_DIR=/path/to/postgres PG_PORT=55432 source pg_env.sh
#
# Defaults are tuned for: local source tree + local install + non-default
# port (so the system PG on 5432 is never touched).

# --- Source tree (required) ----------------------------------------------------
: "${PG_SRC_DIR:=$HOME/postgres}"

# --- Install + data layout -----------------------------------------------------
: "${PG_PREFIX:=$PG_SRC_DIR/install}"
: "${PGBIN:=$PG_PREFIX/bin}"
: "${PGDATA:=$PG_PREFIX/data}"
: "${PG_LOG:=$PG_PREFIX/data/server.log}"
: "${PG_CONF:=$PG_PREFIX/data/postgresql.conf}"
: "${PG_SOCK_DIR:=/tmp}"

# --- Port + auth ---------------------------------------------------------------
# Default to a non-standard port to avoid clashing with the system PG.
: "${PG_PORT:=55432}"
: "${PG_USER:=$(id -un)}"

# --- Build options (passed to ./configure) -------------------------------------
# These defaults favour bug-hunting: assertions, debug symbols, no optimisation.
# -O0 -ggdb3 makes gdb backtraces of a core dump actually readable. This is the
# single highest-yield change — a plain -O2 build catches almost nothing.
: "${PG_CONFIGURE_OPTS:=--enable-debug --enable-cassert --enable-debug-symbols --enable-tap-tests --prefix=$PG_PREFIX}"
: "${PG_CFLAGS:=-O0 -ggdb3 -fno-omit-frame-pointer}"

# --- Cache poisoning ----------------------------------------------------------
# Force catcache/relcache invalidation on every lookup so cache-invalidation
# bugs crash immediately instead of lurking. Pre-PG14 this is the build-time
# macro -DCLOBBER_CACHE_ALWAYS; PG14+ replaces it with a runtime GUC
# (debug_discard_caches = 1). build_and_start_pg.sh auto-detects which the tree
# supports by grepping the source. Set PG_POISON_CACHE=0 to skip (much faster
# build/run, but far fewer bugs found).
: "${PG_POISON_CACHE:=1}"

# --- Export everything --------------------------------------------------------
export PG_SRC_DIR PG_PREFIX PGBIN PGDATA PG_LOG PG_CONF PG_SOCK_DIR
export PG_CFLAGS PG_POISON_CACHE
export PGPORT=$PG_PORT PGUSER=$PG_USER
export PATH="$PGBIN:$PATH"

# --- Sanity check -------------------------------------------------------------
if [ ! -d "$PG_SRC_DIR" ]; then
  echo "pg_env: PG_SRC_DIR=$PG_SRC_DIR does not exist." >&2
  echo "       Set PG_SRC_DIR to your postgres source root before sourcing." >&2
  return 1 2>/dev/null || exit 1
fi
if [ ! -f "$PG_SRC_DIR/GNUmakefile" ] && [ ! -f "$PG_SRC_DIR/src/Makefile" ]; then
  echo "pg_env: $PG_SRC_DIR does not look like a PostgreSQL source tree." >&2
  return 1 2>/dev/null || exit 1
fi
