# Fuzzing PostgreSQL

The fastest way to find crash-class bugs is not to read code — it is to
let a fuzzer generate inputs you would never think to write, against a
poisoned (cassert + cache-discard) build, and collect the cores.

## Why fuzz first

Reading a diff only validates "places you already suspect." A fuzzer
hits the paths you don't suspect — which is where latent bugs actually
live. Historically `sqlsmith` has reported more backend crashes than any
single human reviewer. Reserve hand-written repros for *minimising* a
fuzzer find (the MRE step), not for primary discovery.

## sqlsmith — random valid SQL

`scripts/fuzz_sqlsmith.sh [seconds] [db]` drives it. It generates
syntactically- and type-valid statements from the live catalog and runs
them until the backend crashes.

Key facts:
- **Seed the database first.** sqlsmith is far more effective against a
  populated catalog. Load the regression DB (`make installcheck` once,
  or `pg_regress`'s `regression` db) or create a few tables with mixed
  types, indexes, partitions, and a view or two.
- **Run it long.** A few minutes finds the shallow stuff; an overnight
  run is where the interesting cores show up.
- **It logs the failing query.** When the backend dies, the last query
  sqlsmith sent is in the fuzz log — that is your raw repro to minimise.
- Crashes surface as: a new `core*` under `$PGDATA`, and/or
  `PANIC`/`TRAP:`/"server closed the connection" in the server log.

## Other fuzzers / checkers (when sqlsmith isn't enough)

| Tool | Finds | Note |
| --- | --- | --- |
| SQLancer | **logic** bugs (wrong results, not just crashes) | NoREC/TLP/PQS oracles; complements sqlsmith |
| amcheck / pg_amcheck | index & heap corruption | run after bulk DML; `bt_index_check`, `heapallindexed` |
| pg_dump → restore round-trip | dump/restore asymmetry | dump the fuzzed db, restore into a fresh one, diff |
| `make check-world` under valgrind | uninitialised reads, leaks | slow; catches what asserts miss |

## Targeted fuzzing

If a commit touched a specific area (see `commit_risk_indicators.md`),
narrow the fuzzer's surface:
- Pre-create the object types the commit cares about (e.g. partitioned
  tables for a pruning commit, generated columns for a virtual-column
  commit) so the random queries actually exercise the new code path.
- Set the relevant GUC the commit added/changed in `data.conf` so every
  fuzzed query runs through it.

## After a crash

Go to `triage_and_bisect.md`. Do **not** start theorising about the root
cause or editing C from the fuzz log alone — get a backtrace and a
minimal repro first.
