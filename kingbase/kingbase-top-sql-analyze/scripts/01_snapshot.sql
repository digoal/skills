-- ============================================================
-- kingbase-top-sql-analyze / Step 2: 快照采集
-- 适用：KingbaseES（金仓）V9R1C10，PG 兼容模式
-- 每个阶段执行一次，需分别记录 snapshot_time（应用层记录，SQL 内也记录一份供交叉核对）
-- 用法：psql "host=<host> port=<port> user=<user> dbname=<db>" \
--       -f 01_snapshot.sql > snapshotN.tsv
-- 注意：执行前请用 00_precheck.sql 探测字段。下面 SELECT 只用了 R1C10 上
--       sys_stat_statements 1.11 一定存在的字段；若你的实例缺某个字段，
--       删除对应列后再执行（或在 Python 脚本中做动态列拼接）。
-- ============================================================

-- 采集时间戳（用于计算采集间隔）
SELECT clock_timestamp() AS snapshot_time;

-- 全量字段采集
-- 说明：
--   - KES 无 wal_bytes 字段，写放大用 shared_blks_dirtied / shared_blks_written 评估
--   - blk_read_time / blk_write_time 在 track_io_timing=off 时恒为 0
--   - total_plan_time / mean_plan_time 在 KES R1C10 上存在（无需按版本裁剪）
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
    s.shared_blks_dirtied,      -- 写放大（替代 wal_bytes）
    s.shared_blks_written,
    s.temp_blks_written,
    s.total_plan_time,
    s.total_plan_time / NULLIF(s.calls, 0)  AS mean_plan_time,
    s.blk_read_time,            -- 需要 track_io_timing=on 才有值
    s.blk_write_time,
    s.calls                     AS raw_calls_for_diff  -- 差值模式下用于对齐/校验
FROM public.sys_stat_statements s
JOIN pg_authid a ON a.oid = s.userid
ORDER BY s.total_exec_time DESC;

-- ------------------------------------------------------------
-- 重置模式专用：采集完快照1后，需用户明确授权才可执行下面这条
-- ⚠️ 危险操作：会清空该实例全局 sys_stat_statements 统计历史
-- ------------------------------------------------------------
-- SELECT public.sys_stat_statements_reset();
