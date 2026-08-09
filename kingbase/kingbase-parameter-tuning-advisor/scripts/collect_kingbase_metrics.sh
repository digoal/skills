#!/usr/bin/env bash
# kingbase-parameter-tuning-advisor: KingbaseES 侧只读指标采集脚本（psql 版）
#
# 用法:
#   export PGPASSWORD='your_password'        # 推荐
#   ./collect_kingbase_metrics.sh [--host H] [--port P] [--user U] [--dbname D]
#
# 连接参数解析优先级（与 SKILL.md 一致）:
#   1. 命令行参数 --host/--port/--user/--dbname
#   2. 环境变量 PGHOST PGPORT PGDBNAME(PGDATABASE) PGUSER PGPASSWORD
#      （兼容 KINGBASEHOST/KINGBASE_HOST 等 KINGBASE_* 变体）
#   3. 缺省值: 127.0.0.1 / 5432 / kingbase / kingbase / 123456
#
# 行为与 collect_kingbase_metrics.sql / .py 一致：全部只读查询，不修改任何数据。
# 客户端优先用 psql；若只有金仓客户端，则回退到 ksql / sys_ksql。

set -u

HOST=""; PORT=""; USER=""; DBNAME=""
while [ $# -gt 0 ]; do
  case "$1" in
    --host)   HOST="${2:-}"; shift 2 ;;
    --port)   PORT="${2:-}"; shift 2 ;;
    --user)   USER="${2:-}"; shift 2 ;;
    --dbname) DBNAME="${2:-}"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

# ---- 解析连接参数（参数 > 环境变量 > 默认值）----
HOST="${HOST:-${PGHOST:-${KINGBASEHOST:-${KINGBASE_HOST:-127.0.0.1}}}}"
PORT="${PORT:-${PGPORT:-${KINGBASEPORT:-${KINGBASE_PORT:-5432}}}}"
USER="${USER:-${PGUSER:-${KINGBASEUSER:-${KINGBASE_USER:-kingbase}}}}"
# 注意: 用户可能使用 PGDBNAME（本 skill 约定），psql 原生变量是 PGDATABASE
DBNAME="${DBNAME:-${PGDBNAME:-${PGDATABASE:-${KINGBASEDBNAME:-${KINGBASE_DBNAME:-kingbase}}}}}"
# 密码: 只从 PGPASSWORD / KINGBASE_PASSWORD 环境变量读取，绝不拼进命令行

if [ -z "${PGPASSWORD:-}" ] && [ -n "${KINGBASE_PASSWORD:-}" ]; then
  export PGPASSWORD="$KINGBASE_PASSWORD"
fi
if [ -z "${PGPASSWORD:-}" ] && [ -z "${KINGBASE_PASSWORD:-}" ]; then
  echo "警告: 未设置 PGPASSWORD，将依赖 ~/.pgpass 或触发交互式输入" >&2
fi

# ---- 客户端选择 ----
PSQL="$(command -v psql 2>/dev/null)"
if [ -z "$PSQL" ]; then
  for c in ksql sys_ksql; do
    PSQL="$(command -v "$c" 2>/dev/null)" && break
  done
fi
if [ -z "$PSQL" ]; then
  echo "错误: 未找到 psql / ksql / sys_ksql 客户端" >&2
  exit 1
fi

section () { echo ""; echo "===== $1 ====="; }

run_sql () {
  # 每条 SQL 独立短连接，执行完即断开
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DBNAME" -Atqc "$1" 2>&1
}

section "1. 实例基础信息"
run_sql "SELECT version();"
run_sql "SHOW database_mode;"
run_sql "SHOW config_file;"
run_sql "SHOW data_directory;"
run_sql "SELECT pg_postmaster_start_time();"

section "2. 关键参数"
for p in shared_buffers work_mem maintenance_work_mem effective_cache_size huge_pages \
         max_connections superuser_reserved_connections wal_buffers min_wal_size max_wal_size \
         checkpoint_timeout checkpoint_completion_target wal_compression max_worker_processes \
         max_parallel_workers max_parallel_workers_per_gather max_wal_senders \
         autovacuum_max_workers autovacuum_vacuum_cost_limit autovacuum_naptime \
         autovacuum_vacuum_scale_factor autovacuum_analyze_scale_factor random_page_cost \
         effective_io_concurrency default_statistics_target synchronous_commit \
         synchronous_standby_names track_io_timing shared_preload_libraries; do
  echo "$p = $(run_sql "SHOW $p;")"
done

section "3. 缓存命中率（数据库级）"
run_sql "SELECT datname, blks_hit, blks_read, round(100.0*blks_hit/nullif(blks_hit+blks_read,0),2) AS cache_hit_ratio, temp_files, temp_bytes, deadlocks, xact_commit, xact_rollback FROM pg_stat_database WHERE datname NOT IN ('template0','template1') ORDER BY blks_read DESC;"

section "4. Checkpoint / bgwriter"
run_sql "SELECT checkpoints_timed, checkpoints_req, round(100.0*checkpoints_req/nullif(checkpoints_timed+checkpoints_req,0),2) AS req_checkpoint_ratio, checkpoint_write_time, checkpoint_sync_time, buffers_checkpoint, buffers_clean, buffers_backend, buffers_alloc, stats_reset FROM pg_stat_bgwriter;"

section "5. 连接状态分布"
run_sql "SELECT state, count(*) AS cnt FROM pg_stat_activity WHERE pid <> pg_backend_pid() GROUP BY state ORDER BY cnt DESC;"
run_sql "SELECT count(*) AS current_connections, (SELECT setting::int FROM pg_settings WHERE name='max_connections') AS max_connections FROM pg_stat_activity;"

section "6. 锁等待"
run_sql "SELECT locktype, relation::regclass, mode, granted, count(*) FROM pg_locks WHERE NOT granted GROUP BY locktype, relation, mode, granted;"

section "7. 表级扫描方式与膨胀信号 Top20"
run_sql "SELECT schemaname, relname, seq_scan, idx_scan, n_live_tup, n_dead_tup, round(100.0*n_dead_tup/nullif(n_live_tup+n_dead_tup,0),2) AS dead_tup_ratio, last_autovacuum, last_autoanalyze FROM pg_stat_user_tables WHERE schemaname NOT IN ('sys_catalog','sys_hm','sysaudit','sysmac','src_restrict','xlog_record_read','dbms_job','dbms_scheduler','kdb_schedule','anon') ORDER BY (seq_scan+idx_scan) DESC LIMIT 20;"

section "8. 慢查询 / 高频查询（sys_stat_statements）"
run_sql "SELECT round(total_exec_time::numeric,2) AS total_exec_time_ms, calls, round(mean_exec_time::numeric,2) AS mean_exec_time_ms, round((100*total_exec_time/sum(total_exec_time) OVER())::numeric,2) AS pct_of_total, left(query,120) AS query_snippet FROM sys_stat_statements ORDER BY total_exec_time DESC LIMIT 20;" || echo "提示: sys_stat_statements 不可用，需在 kingbase.conf 的 shared_preload_libraries 中加入 sys_stat_statements"

section "9. 数据库大小"
run_sql "SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size FROM pg_database ORDER BY pg_database_size(datname) DESC;"

echo ""
echo "===== 采集完成 ====="
