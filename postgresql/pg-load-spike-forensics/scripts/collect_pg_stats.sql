-- pg-load-spike-forensics: 数据库侧只读取证脚本
-- 用法：psql -X -U <只读账号> -d <目标库> -f collect_pg_stats.sql > pg_stats_$(date +%Y%m%d_%H%M).log
-- 说明：本脚本全部为只读 SELECT，不做任何写操作；建议在怀疑窗口内及发现问题后立即执行，
--       因为 pg_stat_activity 是当前快照，事后执行只能验证残留状态，不能还原历史时刻。

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

\echo '===== 5. 后台写/检查点统计（PG<17 用 bgwriter，PG>=17 用 checkpointer） ====='
SELECT * FROM pg_stat_bgwriter;
-- PG 17+ 请改用： SELECT * FROM pg_stat_checkpointer;

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

\echo '===== 9. pg_stat_statements Top 20（累计值，需两次快照做差才能得到窗口内增量） ====='
SELECT left(query, 120) AS query, calls, total_exec_time, mean_exec_time, rows,
       shared_blks_hit, shared_blks_read, temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

\echo '===== 采集完成，请结合日志/OS指标做时间对齐分析 ====='
