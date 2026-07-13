# Live-at-HEAD rule: don't chase already-fixed or reverted bugs

The single most common way this skill wastes time: "finding" a bug that
HEAD already fixed, often by reverting the fix to make it crash. A crash
that only appears on a modified tree is **not a bug report** — it is a
re-creation of a bug the maintainers already closed.

This file explains the gate (Step 0), how to screen a commit, and the
distinction between *finding a bug* and *verifying a fix*.

## Table of contents
- [The one rule](#the-one-rule)
- [Step 0: clean-tree gate](#step-0-clean-tree-gate)
- [Screening a candidate commit](#screening-a-candidate-commit)
- [Revert-to-reproduce is worthless](#revert-to-reproduce-is-worthless)
- [Fix-verification vs bug-find](#fix-verification-vs-bug-find)
- [When the tree is dirty](#when-the-tree-is-dirty)

## The one rule

> A finding only counts if it crashes the **unmodified `postgres` binary
> built from the tree exactly as committed at HEAD**.

If you changed a source file (reverted a fix, applied a patch, toggled a
`#define` not part of the build) to get the crash, it is not a finding.

## Step 0: clean-tree gate

Before building or investing in a candidate:

```bash
cd "$PG_SRC_DIR"
git status --short      # any M / MM / A / D? tree is NOT as-committed
git stash list          # stashed diffs hide reverts too
git log -1 --oneline    # know exactly what HEAD is
```

- A clean tree (`git status --short` prints nothing) is required before
  any crash you find can be trusted as live.
- `MM file` means the file differs in *both* the index and the worktree —
  a classic sign someone staged a revert. Inspect with
  `git diff --cached <file>` (staged) and `git diff <file>` (unstaged).

## Screening a candidate commit

When the user says "test this commit", or you pick one from
`find_suspicious_commits.sh`, screen it first:

```bash
./scripts/check_already_fixed.sh <hash>
# exit 0 = normal candidate    exit 1 = skip (already a fix in HEAD)
```

It reports three things:
1. **in-HEAD** — `git merge-base --is-ancestor <hash> HEAD`. If yes, any
   bug the commit *fixes* is already gone.
2. **is-a-fix** — subject prefix (`Fix`/`Revert`/`Avoid`/`Strip`/…) or
   bug-fix trailers (`Reported-by:` / `Backpatch-through:` / `Bug:`).
   `Discussion:` alone does **not** count — almost every PG commit has it.
3. **follow-up** — later commits touching the same files that look like a
   revert or re-fix (the bug may have been re-broken or the fix tweaked).

A commit that is **in-HEAD AND is-a-fix** is the trap: its bug is closed.
Don't reproduce that bug. The productive move is to treat the fix as a
*fragility hint* and hunt for a **different, still-live** crash nearby —
new GUC, new code path, adjacent untested branch — that reproduces on the
unmodified HEAD build.

## Revert-to-reproduce is worthless

It is tempting to "validate the harness" by reverting a fix and watching it
crash. That is fine **only** as a throwaway sanity check of your tooling,
and only if you immediately restore the tree and never report the result.
Pitfalls:
- The crash proves the fix works, not that a bug exists.
- It is easy to forget to restore, leaving a dirty tree (or worse, commit
  the revert) that re-introduces the bug.
- If you must do it, restore immediately and verify:
  `git checkout -- <file>` then `git status --short` is empty.

Prefer not to do it at all. If the goal is "does HEAD crash?", just build
HEAD and run the input.

## Fix-verification vs bug-find

These are different deliverables — label them correctly:

| Task | Build | Success looks like | Output |
| --- | --- | --- | --- |
| **Bug find** | unmodified HEAD | crash on HEAD | pgsql-bugs report |
| **Fix verify** | HEAD (fix present) | the input does **not** crash | short note, not a bug report |

If you ended up confirming a fix, write
`markdown/find_postgres_bug-no-new-bug-<slug>-<date>.md` summarising what
was ruled out. Do **not** run `gen_bug_report.sh` for it — that template is
for live, reportable crashes only.

## When the tree is dirty

If Step 0 finds uncommitted changes (especially a staged revert of a fix):
- **Stop and surface it to the user.** Show `git status --short` and a
  one-line diffstat. Explain that a `git commit` could re-introduce a
  fixed bug.
- **Never** `git commit`, `git checkout`, `git restore`, `git stash`, or
  otherwise discard the user's changes without explicit permission.
- Ask whether to (a) test as-is (accepting it is not pure HEAD), or
  (b) wait while they resolve it. Do not silently build on top of it.
