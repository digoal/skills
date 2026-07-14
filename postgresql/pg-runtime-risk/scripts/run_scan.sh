#!/usr/bin/env bash
# pg-runtime-risk / run_scan.sh
#
# 只读运行时风险扫描脚本。所有查询均在只读事务中执行，不做任何写操作。
#
# 依赖：psql（PostgreSQL client）
# 凭据：仅通过环境变量 PGPASSWORD 传递密码，绝不接受命令行密码参数、
#       绝不写入日志、绝不落盘明文密码文件。
#
# 用法：
#   PGPASSWORD='xxx' ./run_scan.sh -h <host> -p <port> -U <user> -d <database> [-o <output_dir>]
#
# 输出：
#   在 <output_dir>（默认 ./pg_runtime_risk_output_<timestamp>）下生成一系列
#   .txt / .csv 文件，每个文件对应报告中的一个检查项。Agent 读取这些文件后
#   按照 SKILL.md 中的分级阈值与报告模板生成最终中文报告。

set -uo pipefail

HOST=""
PORT="5432"
USER=""
DB="postgres"
OUTDIR=""

usage() {
  echo "用法: PGPASSWORD='***' $0 -h <host> -p <port> -U <user> -d <database> [-o <output_dir>]" >&2
  exit 1
}

while getopts "h:p:U:d:o:" opt; do
  case "$opt" in
    h) HOST="$OPTARG" ;;
    p) PORT="$OPTARG" ;;
    U) USER="$OPTARG" ;;
    d) DB="$OPTARG" ;;
    o) OUTDIR="$OPTARG" ;;
    *) usage ;;
  esac
done

if [[ -z "$HOST" || -z "$USER" ]]; then
  usage
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "错误：未检测到 PGPASSWORD 环境变量。请通过 PGPASSWORD='xxx' 传递密码，不要作为命令行参数传递。" >&2
  exit 2
fi

if [[ -z "$OUTDIR" ]]; then
  OUTDIR="./pg_runtime_risk_output_$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "$OUTDIR"

PSQL_BASE=(psql -X -q -v ON_ERROR_STOP=0 -h "$HOST" -p "$PORT" -U "$USER" -d "$DB")

# 每条语句前统一加上只读事务声明，杜绝任何写操作可能性。
run_query() {
  local outfile="$1"
  local sql="$2"
  {
    echo "BEGIN;"
    echo "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;"
    echo "SET statement_timeout = '30s';"
    echo "$sql"
    echo "COMMIT;"
  } | "${PSQL_BASE[@]}" --csv > "$OUTDIR/$outfile" 2> "$OUTDIR/$outfile.err"
  if [[ -s "$OUTDIR/$outfile.err" ]]; then
    echo "[提示] $outfile 执行时有告警/错误，详见 $outfile.err（常见原因：权限不足、扩展未安装，属预期内的优雅降级）" >&2
  fi
}

echo "==> 输出目录: $OUTDIR"

# ---------- 第零部分：环境信息采集 ----------
run_query "00_version_uptime.csv" "
SELECT version() AS pg_version,
       pg_postmaster_start_time() AS start_time,
       now() - pg_postmaster_start_time() AS uptime,
       pg_is_in_recovery() AS is_standby;
"

run_query "00_key_settings.csv" "
SELECT name, setting, unit, context
FROM pg_settings
WHERE name IN ('max_connections','max_wal_size','wal_keep_size','wal_keep_segments',
               'archive_mode','archive_command','archive_timeout',
               'autovacuum_freeze_max_age','vacuum_freeze_min_age','vacuum_freeze_table_age',
               'autovacuum_max_workers','synchronous_commit','synchronous_standby_names');
"

run_query "00_replication_slots.csv" "
SELECT slot_name, slot_type, database, active, restart_lsn,
       pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) AS restart_lag_bytes,
       confirmed_flush_lsn
FROM pg_replication_slots;
"

run_query "00_wal_receiver.csv" "
SELECT status, receive_start_lsn, received_lsn, last_msg_send_time,
       last_msg_receipt_time, latest_end_lsn, latest_end_time, slot_name, sender_host
FROM pg_stat_wal_receiver;
"

# ---------- 第一部分：事务回卷预警 ----------
run_query "01_database_xid_age.csv" "
SELECT datname, age(datfrozenxid) AS xid_age,
       pg_size_pretty(pg_database_size(datname)) AS db_size
FROM pg_database
WHERE datistemplate = false
ORDER BY xid_age DESC;
"

run_query "01_table_xid_age_top20.csv" "
SELECT c.oid::regclass AS table_name,
       age(c.relfrozenxid) AS table_xid_age,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class c
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE c.relkind IN ('r','m','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema')
ORDER BY table_xid_age DESC
LIMIT 20;
"

run_query "01_vacuum_progress.csv" "
SELECT p.pid, p.datname, p.relid::regclass AS relation,
       p.phase, p.heap_blks_total, p.heap_blks_scanned, p.heap_blks_vacuumed,
       a.query_start, now() - a.query_start AS running_time
FROM pg_stat_progress_vacuum p
JOIN pg_stat_activity a ON p.pid = a.pid;
"

# ---------- 第二部分：序列回卷预警 ----------
# 序列的 last_value 无法通过普通视图批量获取，需要动态生成 SQL 后执行。
# 使用 \gset + \gexec 组合：先生成包含元数据与分级判断的联合查询文本，
# 再执行该文本，全程只读（仅 SELECT，不调用 nextval/setval）。
{
  cat <<'EOSQL'
BEGIN;
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
SET statement_timeout = '30s';

SELECT string_agg(
  format(
    'SELECT %L::text AS seq_full_name, %L::boolean AS is_cycle, last_value,
            CASE WHEN %L THEN NULL ELSE floor((%s::numeric - last_value) / NULLIF(%s,0)) END AS remaining_calls,
            CASE
              WHEN %L THEN ''循环序列(不回卷但可能重复)''
              WHEN floor((%s::numeric - last_value) / NULLIF(%s,0)) < 1000 THEN ''🔴严重: 即将耗尽''
              WHEN floor((%s::numeric - last_value) / NULLIF(%s,0)) < 10000 THEN ''🟠警告: 需尽快处理''
              WHEN floor((%s::numeric - last_value) / NULLIF(%s,0)) < 100000 THEN ''🟡关注: 建议规划''
              ELSE ''🟢正常''
            END AS risk_level,
            %L::text AS data_type
     FROM %I.%I',
    n.nspname || '.' || c.relname, s.seqcycle,
    s.seqcycle, s.seqmax, s.seqincrement,
    s.seqcycle,
    s.seqmax, s.seqincrement,
    s.seqmax, s.seqincrement,
    s.seqmax, s.seqincrement,
    format_type(s.seqtypid, null),
    n.nspname, c.relname
  ),
  ' UNION ALL '
) AS combined_query
FROM pg_sequence s
JOIN pg_class c ON s.seqrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid
\gset

\if :{?combined_query}
:combined_query;
\else
SELECT '当前实例没有序列对象' AS note;
\endif

COMMIT;
EOSQL
} | "${PSQL_BASE[@]}" --csv > "$OUTDIR/02_sequence_risk.csv" 2> "$OUTDIR/02_sequence_risk.csv.err"

# ---------- 第三部分：冻结风暴预警 ----------
run_query "03_freeze_storm_buckets.csv" "
SELECT width_bucket(age(c.relfrozenxid), 0, 2000000000, 20) AS age_bucket,
       count(*) AS table_count,
       pg_size_pretty(sum(pg_total_relation_size(c.oid))) AS total_size,
       sum(pg_total_relation_size(c.oid)) AS total_size_bytes
FROM pg_class c
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE c.relkind IN ('r','m','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema')
GROUP BY age_bucket
ORDER BY age_bucket DESC;
"

# ---------- 第四部分：复制延迟预警 ----------
run_query "04_physical_replication.csv" "
SELECT application_name, client_addr, state, sync_state,
       pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) AS send_lag_bytes,
       pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn) AS write_lag_bytes,
       pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) AS flush_lag_bytes,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes,
       write_lag, flush_lag, replay_lag
FROM pg_stat_replication;
"

run_query "04_logical_slots.csv" "
SELECT s.slot_name, s.slot_type, s.database, s.active, s.restart_lsn,
       pg_wal_lsn_diff(pg_current_wal_lsn(), s.restart_lsn) AS restart_lag_bytes,
       s.confirmed_flush_lsn,
       CASE WHEN s.confirmed_flush_lsn IS NOT NULL
            THEN pg_wal_lsn_diff(pg_current_wal_lsn(), s.confirmed_flush_lsn)
            ELSE NULL END AS confirmed_flush_lag_bytes,
       r.application_name, r.client_addr, r.state
FROM pg_replication_slots s
LEFT JOIN pg_stat_replication r ON s.slot_name = r.application_name
ORDER BY restart_lag_bytes DESC NULLS LAST;
"

# ---------- 第五部分：WAL 日志异常预警 ----------
run_query "05_archiver_status.csv" "
SELECT archived_count, failed_count,
       last_archived_wal, last_archived_time,
       last_failed_wal, last_failed_time
FROM pg_stat_archiver;
"

# pg_ls_waldir() 需要超级用户或 pg_monitor 角色权限，权限不足时优雅降级。
run_query "05_wal_dir.csv" "
SELECT count(*) AS wal_file_count,
       pg_size_pretty(sum(size)) AS total_wal_size,
       sum(size) AS total_wal_size_bytes,
       pg_size_pretty(avg(size)::bigint) AS avg_file_size
FROM pg_ls_waldir();
"

# ---------- 第六部分：连接数耗尽预警 ----------
run_query "06_connection_saturation.csv" "
SELECT (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_connections,
       (SELECT setting::int FROM pg_settings WHERE name = 'superuser_reserved_connections') AS superuser_reserved,
       count(*) AS current_total,
       count(*) FILTER (WHERE state = 'active') AS active_count,
       count(*) FILTER (WHERE state = 'idle') AS idle_count,
       count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx_count,
       count(*) FILTER (WHERE state = 'idle in transaction (aborted)') AS idle_in_tx_aborted_count,
       count(*) FILTER (WHERE wait_event_type = 'Lock') AS waiting_on_lock_count,
       round(
         100.0 * count(*) /
         NULLIF((SELECT setting::int FROM pg_settings WHERE name = 'max_connections'), 0)
       , 1) AS usage_pct
FROM pg_stat_activity
WHERE backend_type = 'client backend';
"

run_query "06_connection_by_database.csv" "
SELECT datname, count(*) AS conn_count,
       count(*) FILTER (WHERE state = 'active') AS active_count,
       count(*) FILTER (WHERE state LIKE 'idle in transaction%') AS idle_in_tx_count
FROM pg_stat_activity
WHERE backend_type = 'client backend' AND datname IS NOT NULL
GROUP BY datname
ORDER BY conn_count DESC;
"

run_query "06_connection_by_user.csv" "
SELECT usename, count(*) AS conn_count,
       count(*) FILTER (WHERE state = 'active') AS active_count
FROM pg_stat_activity
WHERE backend_type = 'client backend' AND usename IS NOT NULL
GROUP BY usename
ORDER BY conn_count DESC;
"

run_query "06_long_idle_in_transaction.csv" "
SELECT pid, usename, datname, application_name, client_addr, state,
       now() - state_change AS idle_duration,
       now() - xact_start AS xact_duration,
       left(query, 200) AS last_query
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY state_change ASC
LIMIT 20;
"

# ---------- 第八部分：大对象泄漏预警 ----------
run_query "08_large_object_summary.csv" "
SELECT count(DISTINCT loid) AS lo_count,
       pg_size_pretty(sum(octet_length(data))) AS total_lo_size,
       sum(octet_length(data)) AS total_lo_size_bytes
FROM pg_largeobject;
"

run_query "08_lo_reference_columns.csv" "
SELECT n.nspname, c.relname, a.attname,
       format_type(a.atttypid, a.atttypmod) AS data_type
FROM pg_attribute a
JOIN pg_class c ON a.attrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE a.atttypid IN ('oid'::regtype, 'lo'::regtype)
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname NOT IN ('pg_catalog','information_schema');
"

echo "==> 扫描完成，结果已保存至 $OUTDIR"
echo "==> 请检查各 *.err 文件，非空说明该检查项因权限/版本/扩展缺失被跳过（属正常优雅降级）"
