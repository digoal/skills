---
name: find-postgres-bug
description: >
  Find latent bugs in a local PostgreSQL source tree (REL_xx_STABLE
  branch or HEAD) the way a core hacker does: build a heavily-poisoned
  debug instance (cassert + cache-discard + -O0/-ggdb3 + core dumps),
  fuzz it (sqlsmith) until the backend crashes, triage the core into a
  minimal reproducer (MRE), git-bisect the introducing commit, and
  render a community-style pgsql-bugs markdown report. The instance
  never auto-shuts-down. Use when the user says "find a bug in
  postgres", "fuzz postgres", "hunt for a crash", "test a recent
  commit", "write a repro", "bisect this crash", "把 PG 跑起来找 bug",
  "fuzz 一下 postgres", "看看这个 commit 会不会出问题", etc. Triggers
  whenever the user points at a PG source dir and wants to hunt bugs.
---

# Find Postgres Bug

## Overview

Crash-first bug-hunting pipeline for a local PostgreSQL source tree.
The order matters and is the whole point:

```
poison the build  →  fuzz it  →  triage the core  →  minimise to an MRE
                  →  bisect the commit  →  report (do NOT self-patch)
```

The leverage is front-loaded. A poisoned build does ~90% of the work by
turning latent bugs into immediate crashes; the fuzzer then finds inputs
no human would hand-write. Reading commits by eye is a *secondary*,
targeted probe — used to aim the fuzzer, not as the primary search.

**Source layout assumed:** the standard PG tree (`src/backend/`,
`src/include/`, `contrib/`, `src/test/`, …) at `$PG_SRC_DIR`.

**Three hard rules:**
1. The skill **never** auto-stops the instance. Run `scripts/stop_pg.sh`
   explicitly when done.
2. **Never write a patch.** The deliverable is an MRE + backtrace +
   bisect result, posted upstream. A drive-by fix from someone who just
   met the code is worth less than a clean reproducer.
3. **A finding only counts if it crashes at HEAD, with the tree exactly
   as committed.** Never revert a fix (or commit a staged revert) to make
   something crash and call it a bug — that just re-creates an
   already-fixed bug and is worthless. Before investing in any candidate,
   run the pre-flight in Step 0. See
   [references/already_fixed.md](references/already_fixed.md).

---

## Quick start

```bash
export PG_SRC_DIR=/path/to/postgres

# 1. POISON: configure+build+initdb+start with cassert, cache-discard,
#    -O0 -ggdb3, core dumps enabled. The 90% lever.
./scripts/build_and_start_pg.sh

# 2. SEED + FUZZ: load some tables, then let sqlsmith run (overnight is best)
psql -h /tmp -p 55432 -d postgres -f your_schema.sql   # populate the catalog
./scripts/fuzz_sqlsmith.sh 3600 postgres               # 1h; use 28800 overnight

# 3. TRIAGE: a crash leaves a core under $PGDATA
./scripts/triage_core.sh /path/to/$PGDATA/core.NNNN

# 4. MINIMISE: cut the failing query down, confirm it crashes on demand
$EDITOR repro/mybug.sql
./scripts/run_repro.sh repro/mybug.sql mybug          # "SERVER IS DOWN" = good

# 5. BISECT: find the commit that introduced it
./scripts/bisect_run.sh repro/mybug.sql REL_17_STABLE HEAD

# 6. REPORT: render markdown for pgsql-bugs (no patch)
$EDITOR /tmp/bug.yaml
./scripts/gen_bug_report.sh /tmp/bug.yaml

# when finished:
./scripts/stop_pg.sh
```

If a real crash surfaces, the markdown is ready for [pgsql-bugs]. If the
fuzzer runs clean, broaden the seed schema / run longer / switch branch.

---

## Workflow

Each step has a **success criterion** to verify before moving on.

### Step 0 — Pre-flight: clean tree & live-at-HEAD gate (do this first)

Before building or investing in any candidate, rule out the two biggest
time-wasters: a dirty working tree, and a "bug" that HEAD already fixed.

```bash
cd "$PG_SRC_DIR"
git status --short            # any M/MM/A? the tree is NOT as-committed
git stash list               # stashed reverts hide here too
```

- **Dirty tree → stop and ask.** Uncommitted edits (especially a *staged
  revert* of a fix) mean you are no longer testing HEAD. A `git commit`
  could re-introduce a fixed bug. Surface this to the user and do not
  build on top of it. Never `git commit`, `git checkout`, `git restore`,
  or `git stash` away the user's changes without explicit permission.
- **Always build and test the tree exactly as committed.** Do not revert
  a fix to "reproduce" a bug. If you ever need to confirm a fix works,
  that is a *fix-verification* task, not a bug find — label it as such and
  do not report it as a new bug.

When the target is a specific commit (the user said "test this commit" or
you picked one in Step 6), check it is not already superseded:

```bash
./scripts/check_already_fixed.sh <hash>   # is it in HEAD? any later "Fix"/revert touching the same files?
```

**Success:** `git status` is clean (or the user has explicitly accepted a
dirty tree), and the candidate commit is confirmed *not* already fixed or
reverted upstream. Only then proceed to Step 1. Details and edge cases:
[references/already_fixed.md](references/already_fixed.md).

### Step 1 — Poison the build & start (the 90% lever)

```bash
export PG_SRC_DIR=/path/to/postgres
./scripts/build_and_start_pg.sh
```

Runs `./configure --enable-debug --enable-cassert
--enable-debug-symbols --enable-tap-tests` with `CFLAGS="-O0 -ggdb3"`,
auto-detects the cache-poison mechanism by **grepping the tree** (PG14+:
`debug_discard_caches=1` GUC; older: `-DCLOBBER_CACHE_ALWAYS`), enables
core dumps, and starts on port `${PG_PORT:-55432}`. Idempotent.

Read [references/pg_build_options.md](references/pg_build_options.md) for
what each flag buys and how to add valgrind / ASan / `RELCACHE_FORCE_RELEASE`
when chasing memory bugs.

**Success:** `pg_isready -p $PG_PORT` returns 0; the start banner shows
`Cache poison: guc` (or `macro`), **not** `none`. If it says `none`,
poisoning was disabled — you'll find far fewer bugs.

### Step 2 — Seed & fuzz (primary discovery)

```bash
# populate the catalog first — sqlsmith is far better against real tables
psql -h /tmp -p $PG_PORT -d postgres -f some_schema.sql
./scripts/fuzz_sqlsmith.sh 3600 postgres
```

The fuzzer generates valid random SQL until the backend crashes. Read
[references/fuzzing.md](references/fuzzing.md) for seeding strategy,
targeted fuzzing (aim it at a specific commit's new objects/GUC), and
alternatives (SQLancer for logic bugs, amcheck for corruption).

**Success:** either a new `core*` appears under `$PGDATA` (→ Step 3), or
the run is clean — in which case broaden the seed schema, run longer, or
switch to a riskier branch/area (see Step 6).

### Step 3 — Triage the core

```bash
./scripts/triage_core.sh <core-file>
```

Produces a full backtrace (lldb on macOS, gdb on Linux). Read the top
non-library frames for the failing function + line. If there's no core,
the crash was likely an `Assert` trip — find `TRAP:` and the last
`STATEMENT` in the server log. See
[references/triage_and_bisect.md](references/triage_and_bisect.md).

**Success:** you can name the failing function and the query that
triggered it.

### Step 4 — Minimise to an MRE

Reduce the fuzzer's giant query to the fewest self-contained lines that
crash a fresh backend every time. Save as `repro/<name>.sql`.

```bash
./scripts/run_repro.sh repro/<name>.sql <name>
```

`run_repro.sh` now detects a crash (server gone / PANIC / TRAP), not just
SQL ERRORs — it prints `SERVER IS DOWN` and exits non-zero when the MRE
works. Patterns by subsystem are in
[references/repro_patterns.md](references/repro_patterns.md); log reading
in [references/log_indicators.md](references/log_indicators.md).

**Success:** a 3–10 line `.sql` crashes the backend deterministically
from a clean database. **Until this holds, do not theorise about root
cause — it's a guess.**

### Step 5 — Bisect the introducing commit

```bash
./scripts/bisect_run.sh repro/<name>.sql <good-ref> <bad-ref>
```

Drives `git bisect run`: each step rebuilds, re-initdbs, runs the MRE,
and reports crash-vs-clean. Confirm `<good-ref>` is genuinely clean
first, or bisect will blame an innocent commit. Details + decision tree
in [references/triage_and_bisect.md](references/triage_and_bisect.md).

**Success:** `git bisect` names a first-bad commit; the MRE crashes at
that commit and not at its parent.

### Step 6 — Targeted commit probe (when fuzzing comes up dry)

If overnight fuzzing finds nothing, aim it. List recent risky commits:

```bash
./scripts/find_suspicious_commits.sh 30 HEAD
```

Read [references/commit_risk_indicators.md](references/commit_risk_indicators.md):
bias toward parser/planner/executor/storage/replication paths and toward
repeatedly-fixed areas (`Fix`/`Undo thinko`/`back-patch`). Then
**pre-create the objects that commit cares about** and re-fuzz, or
hand-write a focused repro for its new code path.

```bash
./scripts/analyze_commit.sh <hash> 600   # message + diff slice
```

**Before spending any time on a candidate, screen it (Step 0 rule 3):**

```bash
./scripts/check_already_fixed.sh <hash>
```

- A commit whose message starts with `Fix`/`Revert`/`Undo` is *itself the
  fix* — the bug it describes is already gone at HEAD. Don't try to
  reproduce that bug; the repro will pass and you'll have proven nothing.
- The useful probe is the **opposite**: treat a recent fix as a hint that
  the surrounding code is fragile, and hunt for a *new, still-live* crash
  near it — one that still reproduces on the unmodified HEAD build.
- **Never** revert the fix (or any commit) to make it crash. A crash that
  only appears after you undo a committed fix is not a finding.

**Success:** you reproduced a crash on the **unmodified HEAD** build, or
confirmed the candidate path is clean for the inputs you exercised. A
crash that needs a reverted fix does **not** count.

### Step 7 — Render the bug report (no patch)

Fill [references/bug_report_template.md](references/bug_report_template.md)
into YAML, then:

```bash
./scripts/gen_bug_report.sh /tmp/<name>.yaml
```

Writes `./markdown/find_postgres_bug-<slug>-<date>.md` with environment,
MRE, actual/expected, backtrace/log tail, why-it's-a-bug, and bisect
result. Leave "suggested fix" as an explicitly-unverified direction at
most.

**Success:** the markdown has all required blocks (Environment / Summary
/ Repro / Actual / Why / Fix) and a log/backtrace snippet containing the
`TRAP:`/`PANIC`/`ERROR:` line.

**Only render a bug report for a crash that reproduces on the unmodified
HEAD build.** If the investigation ended in "already fixed", "already
reverted", or "only crashes after I undid a committed fix", do **not**
produce a pgsql-bugs report — write a short findings note instead
(`markdown/find_postgres_bug-no-new-bug-<slug>-<date>.md`) stating what was
ruled out and why. Reporting an already-fixed bug upstream wastes
maintainers' time.

### Step 8 — Tear down (only when done)

```bash
./scripts/stop_pg.sh
```

The **only** script that stops the instance. Nothing else will.

---

## Output format

One markdown file per bug:
`markdown/find_postgres_bug-<slug>-<YYYY-MM-DD>.md`. Template in
[assets/bug_report.md.template](assets/bug_report.md.template); field
reference in
[references/bug_report_template.md](references/bug_report_template.md).

Required sections (pgsql-bugs expectations):

1. **Environment** — OS / kernel / compiler / PG version / branch /
   commit / build flags (incl. cache-poison mode).
2. **Summary** — 1–3 factual sentences, no judgement.
3. **Reproduction** — the MRE: file path + inline `.sql`.
4. **Actual vs expected** — verbatim crash/output vs expected, plus a
   backtrace or server-log tail.
5. **Why is this a bug** — the spec / docs / invariant it violates.
6. **Suggested fix** — optional, flagged unverified. "I have a reliable
   reproducer but no fix" is a perfectly good report.

---

## Script reference

| Script | Purpose |
| --- | --- |
| `scripts/pg_env.sh` | Sourceable env (paths, port, `PG_CFLAGS`, `PG_POISON_CACHE`) |
| `scripts/build_and_start_pg.sh` | Poisoned configure+make+install+initdb+start; **idempotent, never auto-stops** |
| `scripts/fuzz_sqlsmith.sh` | Drive sqlsmith at the instance; detect new cores + crash markers |
| `scripts/triage_core.sh` | Backtrace a core (lldb/gdb) |
| `scripts/run_repro.sh` | Run a `.sql`; detect crash (server-down/PANIC/TRAP), capture log slice |
| `scripts/bisect_run.sh` | `git bisect run` an MRE across good..bad, rebuilding each step |
| `scripts/find_suspicious_commits.sh` | List recent risky commits (targeted probe) |
| `scripts/check_already_fixed.sh` | Screen a commit: is it in HEAD / itself a Fix / later reverted-or-refixed? |
| `scripts/analyze_commit.sh` | Show stat + diff slice for one commit |
| `scripts/capture_log.sh` | Grep `$PG_LOG` (tail / errors / full) |
| `scripts/gen_bug_report.sh` | Render markdown from a YAML inputs file |
| `scripts/stop_pg.sh` | Explicit teardown |

Override any default by exporting before running:

```bash
PG_PORT=55433 PG_POISON_CACHE=1 ./scripts/build_and_start_pg.sh
```

---

## Reference index

Load only what you need; each file is self-contained.

- [references/pg_build_options.md](references/pg_build_options.md) —
  poisoned-build flags, cache-discard mechanisms, valgrind/ASan, pitfalls.
- [references/fuzzing.md](references/fuzzing.md) — sqlsmith usage,
  seeding, targeted fuzzing, SQLancer/amcheck alternatives.
- [references/triage_and_bisect.md](references/triage_and_bisect.md) —
  backtrace reading, MRE minimisation discipline, `git bisect run`, the
  "report don't patch" rule, triage decision tree.
- [references/commit_risk_indicators.md](references/commit_risk_indicators.md) —
  commit-log-as-regression-signal + where bugs hide, for the targeted probe.
- [references/already_fixed.md](references/already_fixed.md) —
  the live-at-HEAD rule: clean-tree gate, screening a commit, why
  revert-to-reproduce is worthless, fix-verification vs bug-find.
- [references/repro_patterns.md](references/repro_patterns.md) —
  minimal repro patterns by subsystem.
- [references/log_indicators.md](references/log_indicators.md) —
  severities, greps, multi-line patterns (asserts, backtraces, context).
- [references/bug_report_template.md](references/bug_report_template.md) —
  YAML fields + how to post to pgsql-bugs.
- [references/pg_version_helpers.md](references/pg_version_helpers.md) —
  version / commit / compiler / OS one-liners for the report.

---

## What this skill does *not* do

- It does **not** write or submit a patch. MRE + backtrace + bisect,
  posted as a markdown draft for the human to send. This is deliberate.
- It does **not** build sqlsmith for you — if it's missing,
  `fuzz_sqlsmith.sh` prints install hints and exits.
- It does **not** shut the instance down. Explicit teardown only.
- It does **not** guess the root cause before there's a deterministic
  MRE. Triage produces a backtrace; minimisation produces the proof.

---

## Decision tree (TL;DR)

```
PG source dir?
  ├─ NO  → ask for it; suggest $HOME/postgres
  └─ YES → git status --short  (Step 0 pre-flight)
            ├─ dirty / staged revert? → STOP, ask the user; never commit it
            └─ clean → build_and_start_pg.sh  (poisoned: cassert+cache-discard+-O0)
            ├─ banner says "Cache poison: none"? → re-enable PG_POISON_CACHE=1
            └─ up → seed schema → fuzz_sqlsmith.sh (long run)
                     ├─ crash (new core / PANIC)?
                     │    ├─ reproduces on UNMODIFIED HEAD? ── no ─→ not a finding
                     │    ├─ triage_core.sh → backtrace
                     │    ├─ minimise → MRE (run_repro.sh: "SERVER IS DOWN")
                     │    ├─ bisect_run.sh good..bad → first-bad commit
                     │    └─ gen_bug_report.sh → post upstream (NO patch)
                     └─ clean → targeted probe:
                          find_suspicious_commits → check_already_fixed.sh (skip if fixed)
                          → seed those objects → re-fuzz / focused repro on HEAD
                          (NEVER revert a fix to reproduce); or run longer / switch branch
```
