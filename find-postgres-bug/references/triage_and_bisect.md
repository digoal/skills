# Triage & Bisect

What to do once you have a crash. The discipline here is the whole
point: **don't fix on a guess.** Get a backtrace, minimise to an MRE,
bisect to the commit, then report — in that order.

## 1. Backtrace the core

```bash
scripts/triage_core.sh <core-file>      # lldb on macOS, gdb on Linux
```

Read the **top non-library frames** — that is the failing function and
line. `thread apply all bt full` (gdb) / `bt all` (lldb) gives every
thread plus locals (locals are why you built `-O0`).

If there is no core: the crash may have been an `Assert` trip that
`elog`'d and the postmaster restarted the backend. Then the signal is in
the server log (`TRAP: failed Assert("...")`) plus the failing
`STATEMENT` line just before it.

## 2. Minimise to an MRE (the most important step)

A fuzzer's failing query is huge and full of noise. Reduce it to the
fewest lines that still crash a *fresh* backend:

- Delete clauses/joins/subqueries one at a time; after each cut, re-run
  with `run_repro.sh` and check the server still dies.
- Replace generated identifiers with simple ones (`t1`, `c1`).
- Pull the minimal schema setup into the same file so it is
  self-contained: `CREATE TABLE ...; <crashing query>;`.

You have an MRE when a 3–10 line `.sql` crashes the backend on demand,
from a clean database, every time. **Until then, any root-cause story
you tell is a guess.**

```bash
scripts/run_repro.sh repro/<name>.sql <name>
# exits non-zero and says "SERVER IS DOWN" when the MRE crashes — good.
```

## 3. Bisect to the introducing commit

Only with a deterministic MRE in hand:

```bash
scripts/bisect_run.sh repro/<name>.sql <good-ref> <bad-ref>
```

- `<good-ref>`: a commit/tag where the MRE does **not** crash (try an
  older minor-release tag).
- `<bad-ref>`: where it does (usually `HEAD`).

Each step rebuilds + reinitdb's + runs the MRE; `git bisect run` walks
log2(N) commits automatically. Rebuilds are slow — that's expected.

Confirm the `good` end really is good first: if the MRE crashes at
`<good-ref>` too, the bug is older than your range — widen it. A
mis-chosen good ref makes bisect blame an innocent commit.

When done: `git -C $PG_SRC_DIR bisect reset`.

## 4. Report — do not patch

Finding the commit is **not** an invitation to write the fix. The
valuable artifact is the MRE + backtrace + bisect result; that is what
goes upstream. A maintainer who can see a deterministic reproducer will
diagnose root cause far more reliably than a drive-by patch from someone
who just met the code.

`gen_bug_report.sh` renders the markdown. Post the reproducer to
pgsql-bugs (or `bug_report_template.md`'s web form); leave the fix
direction as a *suggestion* at most, explicitly flagged as unverified.

## Triage decision tree

```
crash observed
  ├─ core dump exists?
  │    ├─ yes → triage_core.sh → read top frames
  │    └─ no  → grep server log for TRAP:/PANIC + last STATEMENT
  ├─ minimise failing query → MRE (run_repro.sh confirms crash on demand)
  │    └─ can't minimise / not deterministic? → it's flaky:
  │         note it, keep the raw query, don't bisect yet
  ├─ MRE deterministic → bisect_run.sh (good=old tag, bad=HEAD)
  │    └─ good ref also crashes? → widen range, bug is older
  └─ gen_bug_report.sh → post MRE upstream (NO self-patch)
```
