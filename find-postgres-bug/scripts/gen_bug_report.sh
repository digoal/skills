#!/usr/bin/env bash
# gen_bug_report.sh — render a markdown bug report from a YAML inputs
# file using assets/bug_report.md.template.
#
# Usage:
#   ./gen_bug_report.sh <inputs.yaml>  [output.md]
#
# If output.md is omitted, the report is written to
#   <cwd>/markdown/find_postgres_bug-<title-slug>-<date>.md
# (creates markdown/ if missing).
#
# Required inputs (all strings; long fields can use YAML `|` blocks):
#   title, commit, branch, area, summary, why_bug, fix, severity,
#   repro_path, repro_sql, actual, expected, log_path, log_snippet_lines

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pg_env.sh
source "$HERE/pg_env.sh"

INPUT="${1:?usage: gen_bug_report.sh <inputs.yaml> [output.md]}"
OUTPUT="${2:-}"

if [ ! -f "$INPUT" ]; then
  echo "gen_bug_report: $INPUT not found" >&2
  exit 2
fi

# --- Environment block --------------------------------------------------------
OS_NAME="$(uname -s)"
OS_VER="$(uname -r)"
case "$OS_NAME" in
  Darwin) OS_DISTRO="$(sw_vers -productName) $(sw_vers -productVersion) (build $(sw_vers -buildVersion))" ;;
  Linux)  OS_DISTRO="$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-Linux}")" ;;
  *)      OS_DISTRO="$OS_NAME" ;;
esac
CC_VER="$(${CC:-cc} --version 2>/dev/null | head -1 || echo unknown)"

PG_VERSION_STR="$("$PGBIN/pg_config" --version 2>/dev/null | awk '{print $2}' || true)"
[ -z "$PG_VERSION_STR" ] && PG_VERSION_STR="(not built yet — run build_and_start_pg.sh)"
PG_COMMIT="$(git -C "$PG_SRC_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
PG_DESCRIBE="$(git -C "$PG_SRC_DIR" describe --always --dirty 2>/dev/null || echo unknown)"

REPORT_DATE="$(date +%Y-%m-%d)"

# --- Output path --------------------------------------------------------------
# Pull title + log_path early so we can build a sensible output filename.
eval "$(python3 - "$INPUT" <<'PY'
import sys, yaml
with open(sys.argv[1]) as f: d = yaml.safe_load(f) or {}
title = (d.get("title") or "report").splitlines()[0]
print("YAML_TITLE=" + repr(title))
print("YAML_LOG_PATH=" + repr(d.get("log_path") or ""))
PY
)"

if [ -z "$OUTPUT" ]; then
  SLUG="$(printf '%s' "$YAML_TITLE" | tr '[:upper:] ' '[:lower:]-' | tr -cs 'a-z0-9-' '-' | sed 's/^-//;s/-$//' | cut -c1-60)"
  [ -z "$SLUG" ] && SLUG="report"
  OUTDIR="$PWD/markdown"
  mkdir -p "$OUTDIR"
  OUTPUT="$OUTDIR/find_postgres_bug-${SLUG}-${REPORT_DATE}.md"
fi

# --- Render -------------------------------------------------------------------
TEMPLATE="$HERE/../assets/bug_report.md.template"
[ -f "$TEMPLATE" ] || { echo "template missing: $TEMPLATE" >&2; exit 3; }

# Pipe YAML + template + env block to a single python process. Python reads
# the YAML, builds the substitution map, and writes the rendered file.
python3 - "$TEMPLATE" "$OUTPUT" <<PY
import sys, os
tmpl_path, out_path = sys.argv[1], sys.argv[2]
with open(tmpl_path) as f: tmpl = f.read()

import yaml
with open("${INPUT}") as f: d = yaml.safe_load(f) or {}
def g(k, default=""):
    v = d.get(k)
    return default if v is None else str(v)

log_path = g("log_path")
log_lines = int(g("log_snippet_lines", "80") or "80")
log_snippet = ""
if log_path and os.path.exists(log_path):
    with open(log_path) as f:
        log_snippet = "".join(f.readlines()[-log_lines:])
elif log_path and os.path.exists(os.path.join("${PGDATA}", log_path)):
    p = os.path.join("${PGDATA}", log_path)
    with open(p) as f:
        log_snippet = "".join(f.readlines()[-log_lines:])
else:
    log_snippet = f"(log not found at {log_path})"

subst = {
    "TITLE":       g("title"),
    "OS_NAME":     "${OS_NAME}",
    "OS_DISTRO":   "${OS_DISTRO}",
    "OS_VER":      "${OS_VER}",
    "CC_VER":      "${CC_VER}",
    "PG_VERSION":  "${PG_VERSION_STR}",
    "PG_COMMIT":   "${PG_COMMIT}",
    "PG_DESCRIBE": "${PG_DESCRIBE}",
    "BRANCH":      g("branch"),
    "COMMIT":      g("commit"),
    "AREA":        g("area"),
    "SEVERITY":    g("severity"),
    "REPORT_DATE": "${REPORT_DATE}",
    "SUMMARY":     g("summary"),
    "WHY_BUG":     g("why_bug"),
    "FIX":         g("fix"),
    "REPRO_PATH":  g("repro_path"),
    "REPRO_SQL":   g("repro_sql"),
    "ACTUAL":      g("actual"),
    "EXPECTED":    g("expected"),
    "LOG_PATH":    log_path,
    "LOG_SNIPPET": log_snippet,
}
out = tmpl
for k, v in subst.items():
    out = out.replace("{{" + k + "}}", v)
with open(out_path, "w") as f: f.write(out)
print("wrote", out_path)
PY
