# PG Build Options for Bug Hunting

Configure flags used by `build_and_start_pg.sh` (override via
`PG_CONFIGURE_OPTS` / `PG_CFLAGS` / `PG_POISON_CACHE`). Defaults are
tuned for finding bugs fast, not for production.

**The build is the single highest-yield lever.** A plain
`./configure && make` (`-O2`, no asserts, no cache poisoning) catches
almost nothing — the bugs are there but stay latent. The poisoned build
below is what turns them into immediate crashes. Spend your effort here
before you spend it reading code.

## Recommended defaults

```
--enable-debug --enable-cassert --enable-debug-symbols --enable-tap-tests
CFLAGS="-O0 -ggdb3 -fno-omit-frame-pointer"
+ cache poisoning (see below)
```

- **`--enable-cassert`** — enables `Assert()` in the backend. Many
  latent bugs trip an `Assert` long before they produce a user-visible
  crash. **The single most useful configure flag.**
- **`--enable-debug` / `--enable-debug-symbols`** — debug aids + symbols
  so a crash produces a usable core / backtrace.
- **`CFLAGS="-O0 -ggdb3"`** — no optimisation means gdb/lldb show real
  variable values and an un-inlined stack. The difference between a
  triagable core and "value optimized out" everywhere.
- **`--enable-tap-tests`** — needed for `make check-world` (used as a
  regression diff across commits).
- **`--prefix=$PG_SRC_DIR/install`** — isolates the build from system PG.

## Cache poisoning — the second-highest lever

Forces catcache/relcache invalidation on *every* lookup, so
cache-invalidation bugs (dangling pointers, stale catalog rows) crash
immediately instead of once-in-a-blue-moon. Costs 1–2 orders of
magnitude in speed — irrelevant for a hunting instance.

Two mechanisms, depending on branch. **Don't assume by version number —
let the tree tell you** (`build_and_start_pg.sh` greps the source to pick):

| Branch | Mechanism | How it's enabled |
| --- | --- | --- |
| PG14+ | runtime GUC | `debug_discard_caches = 1` in postgresql.conf |
| pre-PG14 | compile-time | `CPPFLAGS=-DCLOBBER_CACHE_ALWAYS` at configure |

Set `PG_POISON_CACHE=0` to disable (much faster, far fewer bugs).

`debug_discard_caches` also accepts higher values (2, 3) for recursive
invalidation — heavier still, used to chase the deepest cache bugs.

## Heavier instrumentation (turn on when chasing memory bugs)

- **Valgrind** — run the backend under `valgrind --leak-check=no` with
  `USE_VALGRIND` defined (`src/include/pg_config_manual.h`) to catch
  uninitialised reads and out-of-bounds access that asserts miss. Slow;
  best for `make installcheck` rather than interactive fuzzing.
- **`-DMEMORY_CONTEXT_CHECKING`** — sentinel/clobber on palloc chunks;
  catches buffer overruns within a memory context.
- **`-DRELCACHE_FORCE_RELEASE`** — drops relcache refs eagerly; catches
  use-after-free of relation descriptors.
- **AddressSanitizer** — `CFLAGS="-O0 -ggdb3 -fsanitize=address"`; very
  effective on heap bugs but needs `shared_buffers` tuned down and can
  conflict with PG's own memory tricks. Use when valgrind is too slow.

Grep `src/include/pg_config_manual.h` in your tree to see which of these
macros the branch actually supports before relying on one.

## Build & install lifecycle

```bash
cd $PG_SRC_DIR
./configure $PG_CONFIGURE_OPTS CFLAGS="$PG_CFLAGS"   # one-time
make -j$(nproc)                                      # incremental rebuilds
make install                                         # install into $PG_PREFIX
initdb -D $PGDATA                                    # one-time per data dir
pg_ctl -D $PGDATA -l $PG_LOG start                   # idempotent start
```

`build_and_start_pg.sh` runs all of the above, picks the cache-poison
mechanism, enables core dumps (`ulimit -c unlimited`), and skips steps
already done, so it is safe to re-run after editing C code.

## Common pitfalls

- **`make` after editing headers** — run `make clean` only if you
  changed `src/include/`. The build is otherwise incremental.
- **Stale `config.status`** — if you change `./configure` flags,
  delete `src/Makefile.global` and re-run `./configure`.
- **No core dump appears** — check `ulimit -c` (must be `unlimited`); on
  Linux check `/proc/sys/kernel/core_pattern` (a `|` pipe sends cores to
  a handler like systemd-coredump, not `$PGDATA`). On macOS cores land
  in `/cores/` by default unless `ulimit` + the cwd allow `$PGDATA`.
- **OpenSSL headers missing** — on macOS: `brew install openssl`,
  then `--with-openssl` will pick it up.
- **`/usr/bin/psql` shadowing** — the script prepends `$PGBIN` to
  `PATH`. If you don't `source pg_env.sh`, `psql` may hit the system one.
