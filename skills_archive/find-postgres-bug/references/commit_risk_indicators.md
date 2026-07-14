# Commit Risk Indicators

Heuristics for picking which commits are most likely to harbour a
latent bug. Apply when reading `find_suspicious_commits.sh` output.

**Where this fits:** commit-reading is the *secondary*, targeted probe —
use it to aim the fuzzer (see `fuzzing.md` → "Targeted fuzzing") or to
write a focused repro for a specific new code path. The poisoned build +
fuzzer (Steps 1–2 of the skill) is the primary discovery engine. Don't
read commits hoping to spot a bug by eye; read them to decide *what to
make the fuzzer exercise*.

## Use the commit log as a regression signal, not reading material

- **A repeatedly-touched area is an unstable foundation.** If the last
  few months show several commits to the same file/function — especially
  `Fix ...`, `Harden ...`, `Avoid ...`, `Undo thinko in commit <hash>`,
  or `back-patch` — that area very likely still has sibling bugs the last
  fix didn't cover. The same mistake is rarely made exactly once.
- **Diff two refs with the test suite, don't eyeball.** Run
  `make check-world` (or `installcheck`) at `HEAD~N` and at `HEAD`; a new
  assertion failure or newly-flaky test between them is a free lead.
- **Back-patches on `REL_xx_STABLE` are prime suspects** — a fix written
  against `master` and cherry-picked back can be mis-merged or mis-scoped
  for the older branch.

## Where to look first (high-yield paths)

| Path | Why it hides bugs |
| --- | --- |
| `src/backend/executor/` | Many code paths, type-specific nodes, NULL/empty handling |
| `src/backend/optimizer/` | Planner cost + selectivity + join ordering; combinatorial inputs |
| `src/backend/parser/parse_*.c` | Syntax tree construction; missing clauses silently accepted |
| `src/backend/commands/` | DDL path; race with concurrent DDL/DML |
| `src/backend/storage/` | Buffer / WAL / FSM / VM; locking, eviction, fsync semantics |
| `src/backend/replication/` | Logical decoding, walsender timing, failover |
| `src/backend/access/{heap,index,gin,gist,brin,hash,nbtree}/` | Page-level invariants, write-ahead logging |
| `src/backend/catalog/` | Cache invalidation, dependency tracking |
| `src/backend/utils/adt/` | Built-in type functions; numeric overflow, encoding, NaN, locale |
| `src/backend/nodes/` | Node copy / outfuncs / equal; new field = must add to all three |
| `src/timezone/` | tzdata version handling, leap seconds, DST edge cases |
| `src/interfaces/libpq/` | Protocol parsing, pipeline mode, async callback order |
| `src/fe_utils/` | psql, pg_dump, pg_basebackup side channels |
| `contrib/*/sql` and `contrib/*/*.c` | Extensions often have thinner test coverage |

## Heuristics — read the diff, not just the message

A commit is **higher risk** when its diff has any of:

- **New `if` branch added to an error path** — easy to invert the
  condition, miss the cleanup, or leave a state half-initialised.
- **Removed `Assert` / `elog(ERROR, ...)`** — almost always a sign
  that someone is "tidying up" something that was load-bearing.
- **Lock order change** — `LockBuffer`, `LWLockAcquire`, even
  reordering them. New deadlocks often only show up under load.
- **`ereport` changed from `ERROR` to `WARNING`** — real bugs
  frequently masquerade as "make this message friendlier" commits.
- **New GUC** — no `check_GUC_value` boundary test, no
  `assign_xxx` reset path, no docs cross-ref.
- **`palloc` replaced with `palloc0`** (or vice versa) without
  auditing the rest of the function.
- **`snprintf` without `(errcode, ...)`** truncation handling.
- **Modifying a function with many callers** but no regression test
  updated — a strong signal of "fixed locally, broke elsewhere".
- **A `git log --follow` predecessor that already had a `XXX` or
  `FIXME` comment near the change site**.
- **Touches `pgstat.c`, `xlog.c`, `bufmgr.c`, `sinval.c`,
  `relcache.c`** — these are global state; very high blast radius.
- **Touches `pg_upgrade` support code** — often interacts with
  on-disk format changes.

## Heuristics — commit metadata

- **First-parent lineage on a stable branch (`REL_xx_STABLE`)** —
  this is the most likely place for backported fixes; backports
  can be missed or merged with conflicts.
- **No test file in the commit** for code that has business logic
  (parser, planner, executor) — strong signal.
- **Subject starts with `WIP:`, `tmp:`, `fix typo`** but the diff is
  hundreds of lines — almost always a real change hiding behind a
  benign title.
- **Author = committer = same person, no reviewer on the
  `git log -1 --format=%B`** — many latent bugs.
- **Commit message mentions "per report from" / "per bug #XXXX"
  but the linked bug is about a different code path** — the
  backport may have been mis-scoped.

## Cross-check before testing

```bash
# when was this file last touched? often a bug is a regression.
git blame -L <start>,<end> src/backend/executor/...

# are there open discussions? check the mailing list for the commit hash
git log --all --oneline | grep <hash>
```

## Anti-patterns to skip

- Pure `doc/src/sgml/**` changes.
- Changes that only update `pg_stat_statements` counters, `pg_locks`
  views, or add metrics — usually safe, low payoff.
- Pure refactors that do not change behaviour (renames, comment
  edits, white-space) — skip unless the area is already suspect.
