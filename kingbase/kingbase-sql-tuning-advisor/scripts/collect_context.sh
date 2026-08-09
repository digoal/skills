#!/usr/bin/env bash
#
# collect_context.sh —— 采集 KingbaseES（金仓）SQL 调优上下文（psql 通道）
# 与 collect_context.py 结果等价。
#
# 采集内容:
#   1. 实例版本 / database_mode / config_file
#   2. 关键 GUC 参数（内存/代价模型/并行/开关/JIT）
#   3. 每张表的列定义、索引、约束、relpages/reltuples、大小、pg_stat_user_tables 统计
#   4. 关心列的 pg_stats 统计
#   5. sys_stat_statements 可用性与已记录语句量
#
# 用法:
#   export PGPASSWORD='xxx'
#   ./collect_context.sh [-h HOST] [-p PORT] [-U USER] [-d DBNAME] \
#       -t "schema1.table1,schema1.table2" [-c "col1,col2"]
#
# 连接参数解析优先级: 命令行 > 环境变量(PGHOST/PGPORT/PGUSER/PGDBNAME/PGDATABASE/PGPASSWORD 及 KINGBASE* 变体) > 缺省值
#   缺省值: 127.0.0.1:5432 kingbase/kingbase/123456

set -euo pipefail

ARG_HOST=""; ARG_PORT=""; ARG_USER=""; ARG_DB=""; TABLES=""; COLS=""

while getopts "h:p:U:d:t:c:" opt; do
  case $opt in
    h) ARG_HOST="$OPTARG" ;;
    p) ARG_PORT="$OPTARG" ;;
    U) ARG_USER="$OPTARG" ;;
    d) ARG_DB="$OPTARG" ;;
    t) TABLES="$OPTARG" ;;
    c) COLS="$OPTARG" ;;
    *) echo "未知参数"; exit 1 ;;
  esac
done

HOST="${ARG_HOST:-${PGHOST:-${KINGBASEHOST:-${KINGBASE_HOST:-127.0.0.1}}}}"
PORT="${ARG_PORT:-${PGPORT:-${KINGBASEPORT:-${KINGBASE_PORT:-5432}}}}"
USER="${ARG_USER:-${PGUSER:-${KINGBASEUSER:-${KINGBASE_USER:-kingbase}}}}"
DBNAME="${ARG_DB:-${PGDBNAME:-${PGDATABASE:-${KINGBASEDBNAME:-${KINGBASE_DBNAME:-${KINGBASE_DATABASE:-kingbase}}}}}}"

if [[ -z "${PGPASSWORD:-}" ]]; then
  PGPASSWORD="${KINGBASEPASSWORD:-${KINGBASE_PASSWORD:-123456}}"
  export PGPASSWORD
fi

if command -v psql >/dev/null 2>&1; then
  CLIENT="psql"
elif command -v ksql >/dev/null 2>&1; then
  CLIENT="ksql"
else
  echo "未找到 psql 或 ksql 客户端。请安装 PostgreSQL 客户端或使用 collect_context.py（python 通道）。" >&2
  exit 1
fi

PSQL=("$CLIENT" "host=${HOST} port=${PORT} user=${USER} dbname=${DBNAME} sslmode=prefer" -X -A -t)

echo "===== 1. 实例信息 ====="
"${PSQL[@]}" -c "SELECT 'version: ' || version();" -c "SELECT 'database_mode: ' || current_setting('database_mode');" -c "SELECT 'config_file: ' || current_setting('config_file');" -c "SELECT 'server_version_num: ' || current_setting('server_version_num');"

echo "===== 2. 关键 GUC 参数 ====="
"${PSQL[@]}" -c "SELECT name || ' = ' || setting || COALESCE(' ' || unit, '') FROM pg_settings WHERE name IN (
  'work_mem','shared_buffers','effective_cache_size','maintenance_work_mem',
  'random_page_cost','seq_page_cost','cpu_tuple_cost','cpu_index_tuple_cost','effective_io_concurrency',
  'max_parallel_workers_per_gather','max_parallel_workers','parallel_setup_cost','parallel_tuple_cost','min_parallel_table_scan_size',
  'enable_seqscan','enable_indexscan','enable_indexonlyscan','enable_bitmapscan','enable_nestloop','enable_hashjoin','enable_mergejoin','enable_material','enable_sort',
  'jit','jit_above_cost','default_statistics_target',
  'statement_timeout','lock_timeout','idle_in_transaction_session_timeout','max_connections'
) ORDER BY name;"

if [[ -z "$TABLES" ]]; then
  echo "(未提供 -t 参数，跳过表级上下文采集。如需要请用 -t \"schema.table1,schema.table2\")"
  exit 0
fi

IFS=',' read -r -a TABLE_ARRAY <<< "$TABLES"
for T in "${TABLE_ARRAY[@]}"; do
  T="$(echo "$T" | xargs)"
  SCHEMA="${T%%.*}"
  TABLE="${T##*.}"
  echo ""
  echo "===== 3. 表上下文: ${SCHEMA}.${TABLE} ====="
  echo "--- 3.1 列定义 ---"
  "${PSQL[@]}" -c "SELECT a.attnum, a.attname, format_type(a.atttypid, a.atttypmod) AS type,
       CASE WHEN a.attnotnull THEN 'NOT NULL' ELSE '' END AS notnull,
       COALESCE(pg_get_expr(d.adbin, d.adrelid), '') AS default_val
  FROM pg_attribute a
  LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
  WHERE a.attrelid = format('%I.%I', '$SCHEMA', '$TABLE')::regclass AND a.attnum > 0 AND NOT a.attisdropped
  ORDER BY a.attnum;"
  echo "--- 3.2 索引 ---"
  "${PSQL[@]}" -c "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = '$SCHEMA' AND tablename = '$TABLE';"
  echo "--- 3.3 约束 ---"
  "${PSQL[@]}" -c "SELECT conname, contype, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = format('%I.%I', '$SCHEMA', '$TABLE')::regclass ORDER BY contype, conname;"
  echo "--- 3.4 表大小 / relpages / reltuples ---"
  "${PSQL[@]}" -c "SELECT 'total_size: ' || pg_size_pretty(pg_total_relation_size(format('%I.%I', '$SCHEMA', '$TABLE')::regclass));" \
                 -c "SELECT 'relpages: ' || relpages || ', reltuples: ' || reltuples || ', relkind: ' || relkind FROM pg_class WHERE oid = format('%I.%I', '$SCHEMA', '$TABLE')::regclass;"
  echo "--- 3.5 pg_stat_user_tables 统计 ---"
  "${PSQL[@]}" -c "SELECT 'n_live_tup: ' || n_live_tup || ', n_dead_tup: ' || n_dead_tup || ', last_vacuum: ' || COALESCE(last_vacuum::text,'-') || ', last_autovacuum: ' || COALESCE(last_autovacuum::text,'-') || ', last_analyze: ' || COALESCE(last_analyze::text,'-') || ', last_autoanalyze: ' || COALESCE(last_autoanalyze::text,'-') FROM pg_stat_user_tables WHERE schemaname = '$SCHEMA' AND relname = '$TABLE';"
  echo "--- 3.6 pg_stats（关心列，未给 -c 则全部列） ---"
  if [[ -n "$COLS" ]]; then
    # 将 aid,bid,abalance 转为 ('aid','bid','abalance') 安全字面量列表
    COL_LIST="($(echo "$COLS" | tr ',' '\n' | sed "s/[^']*/'&'/g" | tr '\n' ',' | sed 's/,$//'))"
    "${PSQL[@]}" -c "SELECT attname, null_frac, n_distinct, most_common_vals, most_common_freqs, histogram_bounds FROM pg_stats WHERE schemaname = '$SCHEMA' AND tablename = '$TABLE' AND attname IN $COL_LIST ORDER BY attname;"
  else
    "${PSQL[@]}" -c "SELECT attname, null_frac, n_distinct, most_common_vals, most_common_freqs, histogram_bounds FROM pg_stats WHERE schemaname = '$SCHEMA' AND tablename = '$TABLE' ORDER BY attname;"
  fi
done

echo ""
echo "===== 4. sys_stat_statements 可用性 ====="
"${PSQL[@]}" -c "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_class WHERE relname = 'sys_stat_statements') THEN 'available, rows=' || (SELECT count(*) FROM sys_stat_statements) ELSE 'NOT available (请确认 sys_stat_statements 是否加载)' END;"
