-- ============================================================
-- pg-top-sql-analyze / Step 2: 快照采集
-- 每个阶段执行一次，需分别记录 snapshot_time（应用层记录，SQL 内也记录一份供交叉核对）
-- 用法：psql -h <host> -p <port> -U <user> -d <dbname> -f 01_snapshot.sql > snapshotN.tsv
-- ============================================================

-- 采集时间戳（用于计算采集间隔）
SELECT clock_timestamp() AS snapshot_time;

-- 全量字段采集
-- 注：total_plan_time / mean_plan_time 字段仅 PG13+ 存在，
--     若目标版本 < 13，需将下方两列替换为 0 或直接删除对应列后再执行。
SELECT
    s.queryid,
    LEFT(s.query, 500)          AS query_text,
    a.rolname                   AS username,
    s.calls,
    s.total_exec_time,
    s.total_exec_time / NULLIF(s.calls, 0)  AS mean_exec_time,
    s.rows,
    s.shared_blks_hit,
    s.shared_blks_read,
    s.shared_blks_hit::float / NULLIF(s.shared_blks_hit + s.shared_blks_read, 0) AS cache_hit_ratio,
    s.wal_bytes,
    s.total_plan_time,
    s.total_plan_time / NULLIF(s.calls, 0)  AS mean_plan_time,
    s.calls                     AS raw_calls_for_diff  -- 差值模式下用于对齐/校验
FROM pg_stat_statements s
JOIN pg_authid a ON a.oid = s.userid
ORDER BY s.total_exec_time DESC;

-- ------------------------------------------------------------
-- 重置模式专用：采集完快照1后，需用户明确授权才可执行下面这条
-- ⚠️ 危险操作：会清空该实例全局 pg_stat_statements 统计历史
-- ------------------------------------------------------------
-- SELECT pg_stat_statements_reset();
