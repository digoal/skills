#!/usr/bin/env bash
# kingbase-perf-insight: 统一只读查询执行入口（psql 方式）
#
# 用法：
#   export PGPASSWORD='xxx'
#   ./run_analysis.sh -h HOST -p PORT -U USER -d DBNAME -f SQL_FILE \
#     [--schema stat_snapshot] [--start "2026-01-15 14:00:00"] [--end "2026-01-15 16:00:00"] \
#     [--snap-begin 100] [--snap-end 101]
#
# 连接信息解析优先级（与 SKILL.md 一致）：
#   1. 命令行参数 -h/-p/-U/-d
#   2. 环境变量 PGHOST/PGPORT/PGUSER/PGDBNAME（兼容 PGDATABASE）
#   3. 缺省值：PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGDBNAME=kingbase PGPASSWORD=123456
#
# 说明：
#   - 密码只从环境变量 PGPASSWORD 读取，脚本不接受密码作为命令行参数。
#   - 所有查询在 READ ONLY 事务中执行，任何写操作都会被数据库拒绝。
#   - SQL 文件中的 {schema}/{start_time}/{end_time}/:snap_begin_id/:snap_end_id 占位符会被替换为实际值。
#   - 若只有 ksql 没有 psql，把下面的 PSQL_BIN 改为 ksql 即可（语法兼容）。

set -euo pipefail

PSQL_BIN="${PSQL_BIN:-psql}"

SCHEMA="stat_snapshot"
HOST=""; PORT=""; DBUSER=""; DBNAME=""; SQL_FILE=""; START_TIME=""; END_TIME=""
SNAP_BEGIN=""; SNAP_END=""

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
    --snap-begin) SNAP_BEGIN="$2"; shift 2 ;;
    --snap-end) SNAP_END="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

# ---- 连接信息解析 ----
HOST="${HOST:-${PGHOST:-127.0.0.1}}"
PORT="${PORT:-${PGPORT:-5432}}"
DBUSER="${DBUSER:-${PGUSER:-kingbase}}"
DBNAME="${DBNAME:-${PGDBNAME:-${PGDATABASE:-kingbase}}}"

if [[ -z "${PGPASSWORD:-}" ]]; then
  PGPASSWORD="123456"   # 缺省值，仅在用户未提供密码且未设环境变量时使用
fi

if [[ -z "$SQL_FILE" ]]; then
  echo "错误：-f 为必填参数" >&2
  exit 1
fi
if [[ ! -f "$SQL_FILE" ]]; then
  echo "错误：SQL 文件不存在: $SQL_FILE" >&2
  exit 1
fi
# 若 SQL 引用了快照ID占位符但调用方未提供，直接报错而不是静默传空
# （静默会让 psql 把 :snap_begin_id 当字面量传给数据库，报出难懂的语法错误）。
if grep -q ':snap_begin_id' "$SQL_FILE" && [[ -z "$SNAP_BEGIN" ]]; then
  echo "错误：SQL 引用了 :snap_begin_id，但未提供 --snap-begin" >&2
  exit 1
fi
if grep -q ':snap_end_id' "$SQL_FILE" && [[ -z "$SNAP_END" ]]; then
  echo "错误：SQL 引用了 :snap_end_id，但未提供 --snap-end" >&2
  exit 1
fi

TMP_SQL="$(mktemp)"
trap 'rm -f "$TMP_SQL"' EXIT

# ---- 占位符替换 ----
sed -e "s/{schema}/${SCHEMA}/g" \
    -e "s|{start_time}|${START_TIME}|g" \
    -e "s|{end_time}|${END_TIME}|g" \
    "$SQL_FILE" > "$TMP_SQL"

PSQL_VARS=(-v ON_ERROR_STOP=1)
[[ -n "$SNAP_BEGIN" ]] && PSQL_VARS+=(-v snap_begin_id="$SNAP_BEGIN")
[[ -n "$SNAP_END" ]] && PSQL_VARS+=(-v snap_end_id="$SNAP_END")

{
  echo "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;"
  cat "$TMP_SQL"
} | PGPASSWORD="$PGPASSWORD" "$PSQL_BIN" -h "$HOST" -p "$PORT" -U "$DBUSER" -d "$DBNAME" \
    --no-password -X -A -F $'\t' "${PSQL_VARS[@]}"
