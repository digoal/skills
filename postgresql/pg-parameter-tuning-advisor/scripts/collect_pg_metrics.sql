-- pg-parameter-tuning-advisor: PostgreSQL 侧只读采集脚本
-- 全部为只读查询（SHOW / SELECT 系统视图），不包含任何写操作。
-- 建议分段执行，每段之间可以断开连接，避免长时间占用连接。
-- 使用方式示例：
--   PGPASSWORD='<密码>' psql -h <host> -p <port> -U <user> -d <dbname> -Atqc "<单条SQL>"
-- 或将本文件整体喂给 psql -f，再人工/程序化解析输出。

-- ========== 1. 实例基础信息 ==========
SELECT version();
SHOW server_version;
SHOW data_directory;
SELECT pg_postmaster_start_time();
SELECT now() - pg_postmaster_start_time() AS uptime;

-- ========== 2. 当前关键参数值 ==========
SHOW shared_buffers;
SHOW work_mem;
SHOW maintenance_work_mem;
SHOW effective_cache_size;
SHOW huge_pages;
SHOW max_connections;
SHOW superuser_reserved_connections;
SHOW wal_buffers;
SHOW min_wal_size;
SHOW max_wal_size;
SHOW checkpoint_timeout;
SHOW checkpoint_completion_target;
SHOW wal_compression;
SHOW max_worker_processes;
SHOW max_parallel_workers;
SHOW max_parallel_workers_per_gather;
SHOW max_wal_senders;
SHOW autovacuum_max_workers;
SHOW autovacuum_vacuum_cost_limit;
SHOW autovacuum_naptime;
SHOW autovacuum_vacuum_scale_factor;
SHOW autovacuum_analyze_scale_factor;
SHOW random_page_cost;
SHOW effective_io_concurrency;
SHOW default_statistics_target;
SHOW synchronous_commit;
SHOW synchronous_standby_names;
SHOW track_io_timing;

-- 也可以一次性拿到所有非默认参数，快速定位人为改动过的项：
SELECT name, setting, unit, source, context
FROM pg_settings
WHERE source NOT IN ('default', 'override')
ORDER BY name;

-- ========== 3. 缓存命中率（数据库级） ==========
SELECT
  datname,
  blks_hit,
  blks_read,
  round(100.0 * blks_hit / nullif(blks_hit + blks_read, 0), 2) AS cache_hit_ratio,
  temp_files,
  temp_bytes,
  deadlocks,
  xact_commit,
  xact_rollback
FROM pg_stat_database
WHERE datname NOT IN ('template0', 'template1')
ORDER BY blks_read DESC;

-- ========== 4. Checkpoint / bgwriter 压力 ==========
SELECT
  checkpoints_timed,
  checkpoints_req,
  round(100.0 * checkpoints_req / nullif(checkpoints_timed + checkpoints_req, 0), 2) AS req_checkpoint_ratio,
  checkpoint_write_time,
  checkpoint_sync_time,
  buffers_checkpoint,
  buffers_clean,
  buffers_backend,
  buffers_alloc,
  stats_reset
FROM pg_stat_bgwriter;

-- ========== 5. 当前连接与状态分布 ==========
SELECT
  state,
  count(*) AS cnt
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
GROUP BY state
ORDER BY cnt DESC;

SELECT count(*) AS current_connections,
       (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_connections
FROM pg_stat_activity;

-- ========== 6. 锁等待 ==========
SELECT
  locktype, relation::regclass, mode, granted, count(*)
FROM pg_locks
WHERE NOT granted
GROUP BY locktype, relation, mode, granted;

-- ========== 7. 表级扫描方式与膨胀信号（Top 20 按总扫描次数） ==========
SELECT
  schemaname, relname,
  seq_scan, seq_tup_read,
  idx_scan, idx_tup_fetch,
  n_live_tup, n_dead_tup,
  round(100.0 * n_dead_tup / nullif(n_live_tup + n_dead_tup, 0), 2) AS dead_tup_ratio,
  last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
ORDER BY (seq_scan + idx_scan) DESC
LIMIT 20;

-- ========== 8. 慢查询 / 高频查询画像（需 pg_stat_statements 扩展） ==========
-- 若报错 relation "pg_stat_statements" does not exist，说明未安装该扩展，
-- 在报告中注明并降级为仅依赖上面几个系统视图的结论。
SELECT
  round(total_exec_time::numeric, 2) AS total_exec_time_ms,
  calls,
  round(mean_exec_time::numeric, 2) AS mean_exec_time_ms,
  round((100 * total_exec_time / sum(total_exec_time) OVER())::numeric, 2) AS pct_of_total,
  left(query, 120) AS query_snippet
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

-- ========== 9. 数据目录大小与库大小，辅助判断规模 ==========
SELECT pg_size_pretty(pg_database_size(current_database())) AS current_db_size;
SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;
