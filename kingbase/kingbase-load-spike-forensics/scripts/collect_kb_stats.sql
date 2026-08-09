-- kingbase-load-spike-forensics: 数据库侧只读取证脚本
-- 用法：psql -X -U <只读账号> -d <目标库> -f collect_kb_stats.sql > kb_stats_$(date +%Y%m%d_%H%M).log
-- 说明：本脚本全部为只读 SELECT，不做任何写操作。
--       KingbaseES 默认采用 PG 兼容模式，因此 pg_stat_* 视图可用；
--       同时 sys_catalog.sys_stat_* / sys_stat_sql / sys_stat_wait 等金仓独有视图
--       能给出比 PG 更丰富的"SQL × 等待事件 × IO × WAL"全维度画像，
--       强烈建议在怀疑窗口内立即执行（事后只能验证残留状态）。
--
-- 金仓默认坑：log_min_duration_statement = -1（不记慢 SQL），请先 SHOW 确认。

\timing on
\pset pager off

\echo '===== 0. 环境画像 ====='
SELECT version();
SHOW timezone;
SHOW log_timezone;
SHOW shared_buffers;
SHOW work_mem;
SHOW max_connections;
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW autovacuum;
SHOW track_io_timing;
SHOW log_destination;
SHOW log_directory;
SHOW log_filename;
SHOW logging_collector;
SHOW log_min_duration_statement;

\echo '----- 已装扩展 -----'
SELECT extname, extversion FROM pg_extension
WHERE extname IN ('sys_stat_statements','sys_kwr','sys_ksh','sysaudit','sysmac','sys_hm','auto_explain')
ORDER BY extname;

\echo '===== 1. 会话状态与等待事件分布 ====='
SELECT state, wait_event_type, wait_event, count(*)
FROM pg_stat_activity
GROUP BY 1,2,3
ORDER BY count(*) DESC;

\echo '===== 2. 长时间运行/活跃会话明细 ====='
SELECT pid, usename, datname, state, wait_event_type, wait_event,
       now() - query_start AS running_for,
       now() - xact_start  AS xact_running_for,
       left(query, 150) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY running_for DESC NULLS LAST
LIMIT 50;

\echo '===== 3. 阻塞锁链 ====='
SELECT blocked_locks.pid       AS blocked_pid,
       blocking_locks.pid      AS blocking_pid,
       blocked_activity.usename AS blocked_user,
       blocking_activity.usename AS blocking_user,
       left(blocked_activity.query, 100)  AS blocked_query,
       left(blocking_activity.query, 100) AS blocking_query,
       now() - blocked_activity.query_start AS blocked_duration
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_locks blocking_locks
  ON blocking_locks.locktype = blocked_locks.locktype
 AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
 AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
 AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;

\echo '===== 4. 数据库级吞吐与缓存命中 ====='
SELECT datname, numbackends, xact_commit, xact_rollback,
       blks_read, blks_hit,
       round(blks_hit::numeric / nullif(blks_hit + blks_read, 0), 4) AS hit_ratio,
       tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
       temp_files, temp_bytes, deadlocks, conflicts, stats_reset
FROM pg_stat_database
ORDER BY numbackends DESC;

\echo '===== 5. 后台写/检查点统计 ====='
SELECT * FROM pg_stat_bgwriter;

\echo '===== 6. 复制状态（主库执行） ====='
SELECT client_addr, state, sync_state,
       sent_lsn, write_lsn, flush_lsn, replay_lsn,
       write_lag, flush_lag, replay_lag
FROM pg_stat_replication;

\echo '===== 7. 表膨胀 / autovacuum 状态 Top 20 ====='
SELECT schemaname, relname, n_dead_tup, n_live_tup,
       round(n_dead_tup::numeric / nullif(n_live_tup + n_dead_tup, 0), 4) AS dead_ratio,
       last_autovacuum, last_autoanalyze, autovacuum_count, analyze_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;

\echo '===== 8. 正在进行的 vacuum 进度 ====='
SELECT * FROM pg_stat_progress_vacuum;

\echo '===== 9. KB-extra：sys_stat_sql 全维度 SQL 画像（Top 20 by db_time） ====='
SELECT
  s.datname, s.username, s.queryid,
  left(s.query, 120) AS query,
  s.calls,
  round(s.db_time::numeric/1000, 1)              AS db_time_ms,
  round(s.db_cpu::numeric/1000, 1)               AS db_cpu_ms,
  round(s.db_wait::numeric/1000, 1)              AS db_wait_ms,
  s.total_db_time_pct, s.cpu_time_pct, s.wait_time_pct,
  s.wait_event_1, s.wait_calls_1,
  round(s.wait_time_1::numeric/1000, 1)          AS wait_time_1_ms,
  s.wait_event_2,
  round(s.parse_time::numeric/1000, 1)           AS parse_time_ms,
  round(s.plan_time::numeric/1000, 1)            AS plan_time_ms,
  round(s.exec_time::numeric/1000, 1)            AS exec_time_ms,
  s.wal_size,
  s.shared_blks_read_size, s.shared_blks_write_size,
  s.temp_blks_read_size, s.temp_blks_write_size,
  s.shared_blks_hit
FROM sys_catalog.sys_stat_sql s
ORDER BY s.db_time DESC
LIMIT 20;

\echo '===== 10. KB-extra：sys_stat_wait 全局等待事件分布（Top 20） ====='
SELECT event_type, wait_event, calls, total_time,
       round(avg_time::numeric, 2) AS avg_time,
       round(dbtime_pct::numeric, 2) AS dbtime_pct
FROM sys_catalog.sys_stat_wait
ORDER BY total_time DESC
LIMIT 20;

\echo '===== 11. KB-extra：sys_stat_sqlwait SQL × 等待事件 矩阵（Top 30） ====='
SELECT s.username, s.datname::text, s.queryid, left(s.query, 80) AS query,
       w.wait_event_type, w.wait_event, w.calls,
       round(w.times::numeric/1000, 1) AS times_ms
FROM sys_catalog.sys_stat_sqlwait w
JOIN sys_catalog.sys_stat_sql s USING (userid, datid, queryid)
WHERE w.calls > 0
ORDER BY w.calls DESC
LIMIT 30;

\echo '===== 12. KB-extra：sys_stat_wal_buffer 实时 WAL buffer 状态 ====='
SELECT name, bytes, utilization_rate, write_rate,
       written_to_lsn, written_to_lsn - copied_to_lsn AS unwritten_lsn
FROM sys_catalog.sys_stat_wal_buffer;

\echo '===== 13. KB-extra：sys_stat_sqlcount SQL 类型 × 调用次数 ====='
SELECT datid::text, sql_type, background, sum(calls) AS calls, sum(times) AS times
FROM sys_catalog.sys_stat_sqlcount
GROUP BY 1,2,3
ORDER BY calls DESC
LIMIT 20;

\echo '===== 14. KB-extra：sys_stat_statements（PG 兼容 Top 20 by total_exec_time） ====='
SELECT left(query, 120) AS query, calls, total_exec_time, mean_exec_time, rows,
       shared_blks_hit, shared_blks_read, temp_blks_written
FROM sys_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

\echo '===== 15. KB-extra：AWR 风格历史仓库可用性检查 ====='
SELECT
  (SELECT count(*) FROM sys_catalog.sys_stat_sysmetric_history) AS sysmetric_history_rows,
  (SELECT count(*) FROM sys_catalog.sys_stat_metric_history)     AS metric_history_rows,
  (SELECT min(begin_time) FROM sys_catalog.sys_stat_sysmetric_history) AS sysmetric_min_time,
  (SELECT max(begin_time) FROM sys_catalog.sys_stat_sysmetric_history) AS sysmetric_max_time;

\echo '===== 16. KB-extra：sys_stat_sysmetric_history 最近 5 行 ====='
SELECT begin_time, metric_name, metric_unit, metric_value, abs_value
FROM sys_catalog.sys_stat_sysmetric_history
ORDER BY begin_time DESC
LIMIT 5;

\echo '===== 采集完成，请结合日志/OS指标做时间对齐分析 ====='