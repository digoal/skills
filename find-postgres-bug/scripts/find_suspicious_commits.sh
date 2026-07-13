#!/usr/bin/env bash
# find_suspicious_commits.sh — list recent commits on a branch, biased
# toward code paths (parser, planner, executor, replication, GUCs,
# extensions, etc.) that historically yield latent bugs.
#
# Usage:
#   ./find_suspicious_commits.sh [N=30] [BRANCH=HEAD]
#
# Output: tab-separated rows: HASH  DATE  AUTHOR  FILES  INSERTIONS  DELETIONS  SUBJECT
# where FILES is the count of code (non-doc, non-test) files touched.

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pg_env.sh
source "$HERE/pg_env.sh"

N="${1:-30}"
BRANCH="${2:-HEAD}"

cd "$PG_SRC_DIR"

echo "# Recent commits on $BRANCH (skips merges + tests + docs + config + catalogue):"
echo

# Path patterns we want to focus on (where bugs hide). Excluded patterns
# (docs, tests, config, catalogue) are negated at the end.
INCLUDE_REGEX='^src/(backend|pl|bin|port|test|fe_utils|interfaces|include)/|^contrib/|^src/interfaces/'

git log --no-merges --first-parent -n "$N" "$BRANCH" \
  --pretty=format:'COMMIT_START%x09%H%x09%ad%x09%an%x09%s' \
  --date=short \
  --shortstat -- . \
  | awk '
    BEGIN { FS="\t" }
    /^COMMIT_START/ {
      # split into 5 fields; remainder is subject
      n = split($0, a, "\t")
      hash = a[2]; date = a[3]; author = a[4]
      subj = ""
      for (i = 5; i <= n; i++) subj = subj (i==5?"":"\t") a[i]
      # strip the COMMIT_START prefix
      sub(/^COMMIT_START\t/, "")
      gsub(/^\t/, "")
      cur_hash = hash; cur_date = date; cur_author = author; cur_subj = subj
      have_stat = 0
      next
    }
    /^ [0-9]+ files? changed/ {
      files = $1; ins = ""; del_ = ""
      for (i = 1; i <= NF; i++) {
        if ($i ~ /insertions?/) { ins = $(i-1) }
        if ($i ~ /deletions?/) { del_ = $(i-1) }
      }
      have_stat = 1
      printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n", cur_hash, cur_date, cur_author, files, ins+0, del_+0, cur_subj
      next
    }
  ' \
  | head -n "$N"
