#!/usr/bin/env bash
# collect_context.sh
# 只读方式采集目标库的环境背景信息，供 SQL 上线审查使用。
# 用法: PGPASSWORD=xxx ./collect_context.sh -h HOST -p PORT -U USER -d DBNAME [-t "schema.table1,schema.table2"]
#
# 安全约束：
#   - 全程通过 PGPASSWORD 环境变量传递密码，不接受命令行明文密码参数
#   - 会话级强制只读: SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY
#   - 不执行任何 DDL/DML，不使用 EXPLAIN ANALYZE

set -euo pipefail

HOST=""; PORT="5432"; USER=""; DBNAME=""; TABLES=""

while getopts "h:p:U:d:t:" opt; do
  case $opt in
    h) HOST="$OPTARG" ;;
    p) PORT="$OPTARG" ;;
    U) USER="$OPTARG" ;;
    d) DBNAME="$OPTARG" ;;
    t) TABLES="$OPTARG" ;;
    *) echo "未知参数"; exit 1 ;;
  esac
done

if [[ -z "$HOST" || -z "$USER" || -z "$DBNAME" ]]; then
  echo "缺少必需参数: -h HOST -U USER -d DBNAME (可选 -p PORT -t 表清单)" >&2
  exit 1
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "错误: 请通过环境变量 PGPASSWORD 提供密码，禁止明文传参。" >&2
  exit 1
fi

PSQL="psql -X -q -h $HOST -p $PORT -U $USER -d $DBNAME -v ON_ERROR_STOP=0 -c \"SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;\""

run_sql() {
  local label="$1" sql="$2"
  echo "===== ${label} ====="
  psql -X -h "$HOST" -p "$PORT" -U "$USER" -d "$DBNAME" \
       -v ON_ERROR_STOP=0 \
       -c "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;" \
       -c "$sql"
  echo
}

echo "############ pg-sql-audit 环境背景采集 ############"

run_sql "实例版本" "SELECT version();"

run_sql "关键超时参数" "
SELECT name, setting, unit
FROM pg_settings
WHERE name IN ('statement_timeout','lock_timeout','idle_in_transaction_session_timeout',
               'work_mem','maintenance_work_mem','shared_buffers','max_locks_per_transaction');
"

if [[ -n "$TABLES" ]]; then
  IFS=',' read -ra TBL_ARR <<< "$TABLES"
  for tbl in "${TBL_ARR[@]}"; do
    schema_part="${tbl%%.*}"
    table_part="${tbl##*.}"
    if [[ "$tbl" != *.* ]]; then schema_part="public"; table_part="$tbl"; fi

    run_sql "表统计信息: $tbl" "
SELECT relname, n_live_tup, n_dead_tup, last_analyze, last_autoanalyze,
       last_vacuum, last_autovacuum, seq_scan, idx_scan
FROM pg_stat_user_tables
WHERE schemaname='${schema_part}' AND relname='${table_part}';
"

    run_sql "表大小: $tbl" "
SELECT pg_size_pretty(pg_total_relation_size('${schema_part}.${table_part}'::regclass)) AS total_size,
       pg_size_pretty(pg_relation_size('${schema_part}.${table_part}'::regclass)) AS table_size;
"

    run_sql "索引列表: $tbl" "
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname='${schema_part}' AND tablename='${table_part}';
"

    run_sql "外键依赖: $tbl" "
SELECT conname, confrelid::regclass AS references_table, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = '${schema_part}.${table_part}'::regclass AND contype='f';
"

    run_sql "被引用情况(反向外键): $tbl" "
SELECT conname, conrelid::regclass AS dependent_table, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE confrelid = '${schema_part}.${table_part}'::regclass AND contype='f';
"

    run_sql "依赖的视图/物化视图: $tbl" "
SELECT DISTINCT dependent_ns.nspname AS schema, dependent_view.relname AS view_name, dependent_view.relkind
FROM pg_depend
JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
JOIN pg_class AS dependent_view ON pg_rewrite.ev_class = dependent_view.oid
JOIN pg_class AS source_table ON pg_depend.refobjid = source_table.oid
JOIN pg_namespace dependent_ns ON dependent_view.relnamespace = dependent_ns.oid
WHERE source_table.relname = '${table_part}'
  AND source_table.relnamespace = '${schema_part}'::regnamespace;
"

    run_sql "触发器: $tbl" "
SELECT tgname, tgenabled, pg_get_triggerdef(oid)
FROM pg_trigger
WHERE tgrelid = '${schema_part}.${table_part}'::regclass AND NOT tgisinternal;
"
  done
fi

run_sql "长事务/未提交事务排查" "
SELECT pid, usename, state, xact_start, now()-xact_start AS xact_age,
       left(query,120) AS query_snippet
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start ASC
LIMIT 20;
"

run_sql "当前锁等待情况" "
SELECT locktype, relation::regclass, mode, granted, pid
FROM pg_locks
WHERE NOT granted;
"

echo "############ 采集完成 ############"
