#!/usr/bin/env bash
# check_already_fixed.sh — screen a candidate commit before investing time.
#
# Answers three questions that, together, decide whether a commit is worth
# probing for a *live* bug:
#   1. Is the commit already in HEAD? (if yes, any bug it FIXES is gone)
#   2. Is the commit itself a fix/revert? (then don't try to reproduce its bug)
#   3. Was it later reverted or re-fixed by a newer commit touching the same files?
#
# Usage:  ./check_already_fixed.sh <commit-ish> [base-ref]
#   base-ref defaults to HEAD.
#
# Exit status:
#   0  candidate looks live-worthy (not obviously already handled)
#   1  candidate is already fixed / reverted / is itself the fix → skip it
#   2  usage / git error

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pg_env.sh
source "$HERE/pg_env.sh" 2>/dev/null || true

HASH="${1:-}"
BASE="${2:-HEAD}"
if [ -z "$HASH" ]; then
  echo "usage: $0 <commit-ish> [base-ref]" >&2
  exit 2
fi
cd "${PG_SRC_DIR:-.}"

if ! git rev-parse --verify "$HASH^{commit}" >/dev/null 2>&1; then
  echo "error: '$HASH' is not a commit in this tree" >&2
  exit 2
fi

FULL="$(git rev-parse "$HASH")"
SUBJECT="$(git log -1 --format='%s' "$HASH")"
verdict_skip=0

echo "== candidate =="
echo "  $FULL"
echo "  $SUBJECT"
echo

# 1. in HEAD?
if git merge-base --is-ancestor "$HASH" "$BASE" 2>/dev/null; then
  echo "[in-HEAD]   YES — this commit is already an ancestor of $BASE."
  IN_HEAD=1
else
  echo "[in-HEAD]   no  — not yet in $BASE."
  IN_HEAD=0
fi

# 2. is it itself a fix / revert?
#    Two signals: (a) the subject reads like a fix, (b) the body carries
#    bug-fix trailers. PG fixes very often have descriptive subjects
#    ("Strip...", "Make ... resilient", "Avoid ..."), so the trailer check
#    catches what the subject prefix misses. NOTE: nearly every PG commit has
#    a "Discussion:" trailer, so that alone is NOT a fix signal — require
#    Reported-by / Backpatch-through / Bug:, which new-feature commits lack.
BODY="$(git log -1 --format='%b' "$HASH")"
IS_FIX=0
fix_reason=""
if printf '%s\n' "$SUBJECT" | grep -qiE '^(fix|revert|undo|repair|correct|avoid|prevent|disallow|re-?fix|make .* resilient|strip|guard)'; then
  IS_FIX=1; fix_reason="subject reads as a fix"
fi
if printf '%s\n' "$BODY" | grep -qiE '^(reported-by|backpatch|bug:|back-?patch)'; then
  IS_FIX=1
  fix_reason="${fix_reason:+$fix_reason; }has bug-fix trailers (Reported-by/Backpatch/Bug)"
fi
if [ "$IS_FIX" = 1 ]; then
  echo "[is-a-fix]  YES — $fix_reason."
  echo "            => the bug it DESCRIBES is already gone at HEAD."
  echo "            => do NOT try to reproduce that bug; probe for a NEW live"
  echo "               crash near this code instead, on the unmodified build."
else
  echo "[is-a-fix]  no  — neither subject nor trailers look like a fix."
  echo "            (heuristic only — the real guard is: it MUST crash on the"
  echo "             unmodified HEAD build, never after reverting anything.)"
fi

# 3. later reverted or re-fixed? (newer commits touching the same files whose
#    subject mentions revert / fix / this hash)
FILES="$(git show --pretty=format: --name-only "$HASH" | sed '/^$/d' | sort -u)"
SHORT="$(git rev-parse --short "$HASH")"
if [ -n "$FILES" ]; then
  # commits after $HASH, reachable from BASE, touching the same files
  LATER="$(git log --format='%H %s' "$HASH..$BASE" -- $FILES 2>/dev/null \
            | grep -iE 'revert|fix|undo|thinko|oversight|'"$SHORT" || true)"
  if [ -n "$LATER" ]; then
    echo "[follow-up] possible later revert/re-fix touching the same files:"
    printf '%s\n' "$LATER" | sed 's/^/            /' | head -8
  else
    echo "[follow-up] none found touching the same files after this commit."
  fi
fi

echo
# Decide a skip verdict: in-HEAD AND (is-a-fix) is the classic "already fixed,
# don't reproduce its bug" case.
if [ "$IN_HEAD" = 1 ] && [ "$IS_FIX" = 1 ]; then
  echo "VERDICT: SKIP reproducing this commit's bug — it is a fix already in $BASE."
  echo "         If you want, hunt for a *different, still-live* crash nearby."
  verdict_skip=1
elif [ "$IN_HEAD" = 1 ]; then
  echo "VERDICT: in HEAD already. Fine to probe its NEW code path for a live"
  echo "         crash, but never by reverting it."
else
  echo "VERDICT: not in HEAD — a normal candidate."
fi

exit "$verdict_skip"
