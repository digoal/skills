#!/usr/bin/env bash
# pg-perf-insight: 统一只读查询执行入口
#
# 用法：
#   PGPASSWORD='xxx' ./run_analysis.sh -h HOST -p PORT -U USER -d DBNAME -f SQL_FILE \
#     [--schema stat_snapshot] [--start "2026-01-15 14:00:00"] [--end "2026-01-15 16:00:00"]
#
# 说明：
#   - 密码只从环境变量 PGPASSWORD 读取，脚本不接受密码作为命令行参数。
#   - 所有查询在 READ ONLY 事务中执行，任何写操作都会被数据库拒绝。
#   - SQL 文件中的 {schema}/{start_time}/{end_time} 占位符会被替换为实际值。

set -euo pipefail

SCHEMA="stat_snapshot"
HOST=""; PORT="5432"; DBUSER=""; DBNAME=""; SQL_FILE=""; START_TIME=""; END_TIME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h) HOST="$2"; shift 2 ;;
    -p) PORT="$2"; shift 2 ;;
    -U) DBUSER="$2"; shift 2 ;;
    -d) DBNAME="$2"; shift 2 ;;
    -f) SQL_FILE="$2"; shift 2 ;;
    --schema) SCHEMA="$2"; shift 2 ;;
    --start) START_TIME="$2"; shift 2 ;;
    --end) END_TIME="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "错误：请通过环境变量 PGPASSWORD 提供密码，例如 PGPASSWORD='xxx' $0 ..." >&2
  exit 1
fi
if [[ -z "$HOST" || -z "$DBUSER" || -z "$DBNAME" || -z "$SQL_FILE" ]]; then
  echo "错误：-h/-U/-d/-f 均为必填参数" >&2
  exit 1
fi
if [[ ! -f "$SQL_FILE" ]]; then
  echo "错误：SQL 文件不存在: $SQL_FILE" >&2
  exit 1
fi

TMP_SQL="$(mktemp)"
trap 'rm -f "$TMP_SQL"' EXIT

sed -e "s/{schema}/${SCHEMA}/g" \
    -e "s/{start_time}/${START_TIME}/g" \
    -e "s/{end_time}/${END_TIME}/g" \
    "$SQL_FILE" > "$TMP_SQL"

{
  echo "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;"
  cat "$TMP_SQL"
} | psql -h "$HOST" -p "$PORT" -U "$DBUSER" -d "$DBNAME" \
    -v ON_ERROR_STOP=1 --no-password -X -A -F $'\t'
