# PG Version & Commit Helpers

Quick commands for filling the "Environment" block of a bug report.

## Version

```bash
$PGBIN/pg_config --version          # PostgreSQL 16.3
$PGBIN/pg_config --version | awk '{print $2}'

# server-side, after the instance is up:
psql -h /tmp -p $PG_PORT -U $PG_USER -d postgres -c "SHOW server_version;"
psql -h /tmp -p $PG_PORT -U $PG_USER -d postgres -c "SHOW server_version_num;"
```

`server_version_num` is the integer `160003` for 16.3. Use it for
machine-parseable comparison.

## Commit / branch / describe

```bash
git -C $PG_SRC_DIR rev-parse HEAD             # full SHA
git -C $PG_SRC_DIR rev-parse --short HEAD     # short SHA
git -C $PG_SRC_DIR rev-parse --abbrev-ref HEAD   # REL_16_STABLE
git -C $PG_SRC_DIR describe --always --dirty  # REL_16_STABLE-12-gabc1234
```

`git describe` is the most useful single string: branch + commits
since last tag + short SHA. If the tree is dirty, `--dirty` adds `-dirty`.

## Compiler + build flags

```bash
$CC --version | head -1                # Apple clang 16.0.0
$PGBIN/pg_config --configure           # the exact flags passed to ./configure
$PGBIN/pg_config --cc                  # compiler path
$PGBIN/pg_config --cflags              # -O0 -g ... whatever was used
$PGBIN/pg_config --ldflags
```

## OS / kernel

```bash
# macOS
sw_vers                                # ProductName, Version, BuildVersion
uname -a                               # Darwin kernel + arch

# Linux
. /etc/os-release && echo "$PRETTY_NAME"   # Ubuntu 24.04 LTS, etc.
uname -r
```

`build_and_start_pg.sh` runs all of the above indirectly and the
bug report template embeds the results.

## Verifying you're on the right tree

```bash
git -C $PG_SRC_DIR status -s
git -C $PG_SRC_DIR log -1 --oneline
$PGBIN/postgres --version
```

All three should agree on the source tree. A mismatch (e.g. you
rebuilt the source but the running server is the old binary) is a
classic source of "the bug went away" / "I can't reproduce" reports.
