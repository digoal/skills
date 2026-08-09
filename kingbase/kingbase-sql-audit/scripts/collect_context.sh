#!/usr/bin/env bash
# collect_context.sh
# 只读方式采集金仓（KingbaseES）目标库的环境背景信息，供 SQL 上线审查使用。
# 用法: PGPASSWORD=xxx ./collect_context.sh [-h HOST] [-p PORT] [-U USER] [-d DBNAME] [-t "schema.table1,schema.table2"]
#
# 连接参数解析优先级（与 SKILL.md 一致）:
#   1. 命令行参数 -h/-p/-U/-d
#   2. 环境变量 PGHOST PGPORT PGUSER PGDBNAME(PGDATABASE) PGPASSWORD
#      （兼容金仓手册风格的 KINGBASEHOST/KINGBASE_HOST 等 KINGBASE_* 变体）
#   3. 缺省值: 127.0.0.1 / 5432 / kingbase / kingbase / 123456
#
# 安全约束（金仓实测要点）:
#   - 全程通过 PGPASSWORD 环境变量传递密码，不接受命令行明文密码参数
#   - 每条查询包裹在 BEGIN; SET TRANSACTION READ ONLY; ...; ROLLBACK; 中执行
#     （金仓与 PG 相同: SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY 不影响当前事务，
#      必须用 SET TRANSACTION READ ONLY 才能真正拦截写入，本脚本已实测可拦截 CREATE TABLE）
#   - 不执行任何 DDL/DML，不使用 EXPLAIN ANALYZE，不使用 EXPLAIN BUFFERS

set -euo pipefail

ARG_HOST=""; ARG_PORT=""; ARG_USER=""; ARG_DB=""; TABLES=""

while getopts "h:p:U:d:t:" opt; do
  case $opt in
    h) ARG_HOST="$OPTARG" ;;
    p) ARG_PORT="$OPTARG" ;;
    U) ARG_USER="$OPTARG" ;;
    d) ARG_DB="$OPTARG" ;;
    t) TABLES="$OPTARG" ;;
    *) echo "未知参数"; exit 1 ;;
  esac
done

# 优先级: 命令行 > 环境变量(PG*/KINGBASE*) > 缺省值
HOST="${ARG_HOST:-${PGHOST:-${KINGBASEHOST:-${KINGBASE_HOST:-127.0.0.1}}}}"
PORT="${ARG_PORT:-${PGPORT:-${KINGBASEPORT:-${KINGBASE_PORT:-5432}}}}"
USER="${ARG_USER:-${PGUSER:-${KINGBASEUSER:-${KINGBASE_USER:-kingbase}}}}"
DBNAME="${ARG_DB:-${PGDBNAME:-${PGDATABASE:-${KINGBASEDBNAME:-${KINGBASE_DBNAME:-${KINGBASE_DATABASE:-kingbase}}}}}}"

# 密码优先级: PGPASSWORD > KINGBASEPASSWORD/KINGBASE_PASSWORD > 缺省值 123456（与 SKILL.md 连接约定一致）
if [[ -z "${PGPASSWORD:-}" ]]; then
  PGPASSWORD="${KINGBASEPASSWORD:-${KINGBASE_PASSWORD:-123456}}"
  export PGPASSWORD
  if [[ "$PGPASSWORD" == "123456" && -z "${KINGBASEPASSWORD:-}" && -z "${KINGBASE_PASSWORD:-}" ]]; then
    echo "[提示] 未检测到 PGPASSWORD/KINGBASE* 密码环境变量，使用缺省密码 123456（开发/测试环境默认值）。" >&2
  fi
fi

run_sql() {
  local label="$1" sql="$2"
  echo "===== ${label} ====="
  psql -X -h "$HOST" -p "$PORT" -U "$USER" -d "$DBNAME" \
       -v ON_ERROR_STOP=0 \
       -c "BEGIN; SET TRANSACTION READ ONLY; $sql; ROLLBACK;"
  echo
}

echo "############ kingbase-sql-audit 环境背景采集 ############"
echo "目标实例: $HOST:$PORT/$DBNAME (user=$USER)"
echo

run_sql "实例版本与兼容模式" "
SELECT version();
SELECT name, setting FROM pg_settings
WHERE name IN ('database_mode','server_version','hba_file','config_file');
"

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

run_sql "sys_stat_statements(金仓版pg_stat_statements) 可用性" "
SELECT count(*) AS recorded_queries
FROM sys_stat_statements;
"

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
