#!/usr/bin/env bash
# analyze_commit.sh — show stat + readable diff slice for one commit.
# Usage: ./analyze_commit.sh <commit-hash> [max-diff-lines=400]

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pg_env.sh
source "$HERE/pg_env.sh"

COMMIT="${1:?usage: analyze_commit.sh <commit> [max-diff-lines]}"
MAX="${2:-400}"

cd "$PG_SRC_DIR"

echo "=== commit ==="
git show --no-patch --pretty=fuller "$COMMIT"
echo
echo "=== files ==="
git show --stat --format='' "$COMMIT" | head -50
echo
echo "=== diff (first $MAX lines) ==="
git show --color=never --format='' "$COMMIT" | head -n "$MAX"
