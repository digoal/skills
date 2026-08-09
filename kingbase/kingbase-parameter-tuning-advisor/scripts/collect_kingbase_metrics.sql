-- kingbase-parameter-tuning-advisor: KingbaseES 侧只读采集脚本
-- 全部为只读查询（SHOW / SELECT 系统视图 / 统计视图），不包含任何写操作。
--
-- KingbaseES 默认 PG 兼容模式，说明：
--   - pg_settings / pg_stat_activity / pg_stat_database / pg_stat_bgwriter /
--     pg_stat_user_tables / pg_locks 与 PostgreSQL 一致（本脚本默认使用）
--   - sys_catalog.sys_settings / sys_catalog.sys_stat_* 是同义视图（需显式 schema 前缀）
--   - pg_stat_statements 不存在；慢查询画像使用 sys_stat_statements（public schema）
--
-- 使用方式示例：
--   PGPASSWORD='<密码>' psql -h <host> -p <port> -U <user> -d <dbname> -f collect_kingbase_metrics.sql
-- 或将其中单条 SQL 抽出执行：
--   PGPASSWORD='<密码>' psql -h <host> -p <port> -U <user> -d <dbname> -Atqc "<单条SQL>"

-- ========== 1. 实例基础信息 ==========
SELECT version();
SHOW server_version;
SHOW database_mode;            -- 兼容模式: pg / oracle / mysql
SHOW config_file;              -- 一般为 .../kingbase.conf
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
SHOW shared_preload_libraries;  -- 检查是否加载了 sys_stat_statements / sys_kwr

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
WHERE schemaname NOT IN ('sys_catalog','sys_hm','sysaudit','sysmac',
                         'src_restrict','xlog_record_read',
                         'dbms_job','dbms_scheduler','kdb_schedule','anon')
ORDER BY (seq_scan + idx_scan) DESC
LIMIT 20;

-- ========== 8. 慢查询 / 高频查询画像（sys_stat_statements，金仓版 pg_stat_statements） ==========
-- 若报错 relation "sys_stat_statements" does not exist，说明 shared_preload_libraries
-- 未加载 sys_stat_statements 扩展，在报告中注明并降级为仅依赖上面几个系统视图的结论。
-- 注意: *_exec_time 单位为毫秒（ms）。
SELECT
  round(total_exec_time::numeric, 2) AS total_exec_time_ms,
  calls,
  round(mean_exec_time::numeric, 2) AS mean_exec_time_ms,
  round((100 * total_exec_time / sum(total_exec_time) OVER())::numeric, 2) AS pct_of_total,
  left(query, 120) AS query_snippet
FROM sys_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

-- ========== 9. 数据目录大小与库大小，辅助判断规模 ==========
SELECT pg_size_pretty(pg_database_size(current_database())) AS current_db_size;
SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;
