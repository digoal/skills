-- 03_aas_overview.sql
-- 目的：计算平均活跃会话数(AAS)、CPU占比近似、IO等待估算、缓存命中率
-- 占位符：{schema}；:snap_begin_id / :snap_end_id 为快照ID

WITH window_info AS (
  SELECT
    (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_begin_id) AS begin_time,
    (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_end_id)   AS end_time
),
deltas AS (
  SELECT
    e.dbid, e.userid, e.queryid,
    e.calls               - COALESCE(b.calls, 0)               AS delta_calls,
    e.total_exec_time     - COALESCE(b.total_exec_time, 0)     AS delta_total_exec_time,
    e.rows                - COALESCE(b.rows, 0)                AS delta_rows,
    e.shared_blks_hit     - COALESCE(b.shared_blks_hit, 0)     AS delta_shared_blks_hit,
    e.shared_blks_read    - COALESCE(b.shared_blks_read, 0)    AS delta_shared_blks_read,
    -- blk_read_time / wal_bytes 视版本/配置可能不存在，若报错请删除对应列后重跑
    e.blk_read_time       - COALESCE(b.blk_read_time, 0)       AS delta_blk_read_time,
    e.wal_bytes           - COALESCE(b.wal_bytes, 0)           AS delta_wal_bytes
  FROM {schema}.pg_stat_statements_snapshot e
  LEFT JOIN {schema}.pg_stat_statements_snapshot b
    ON b.snapshot_id = :snap_begin_id
   AND b.dbid = e.dbid AND b.userid = e.userid AND b.queryid = e.queryid
  WHERE e.snapshot_id = :snap_end_id
)
SELECT
  ROUND(EXTRACT(EPOCH FROM (w.end_time - w.begin_time))) AS window_seconds,
  ROUND(SUM(d.delta_total_exec_time) / NULLIF(EXTRACT(EPOCH FROM (w.end_time - w.begin_time)), 0) / 1000.0, 2) AS aas,
  SUM(d.delta_total_exec_time) AS total_db_time_ms,
  SUM(d.delta_shared_blks_read) AS total_blks_read,
  SUM(d.delta_shared_blks_hit)  AS total_blks_hit,
  ROUND(
    SUM(d.delta_shared_blks_hit)::numeric
    / NULLIF(SUM(d.delta_shared_blks_hit) + SUM(d.delta_shared_blks_read), 0) * 100, 2
  ) AS cache_hit_ratio_pct,
  SUM(d.delta_blk_read_time) AS total_blk_read_time_ms,
  SUM(d.delta_wal_bytes) AS total_wal_bytes
FROM deltas d, window_info w
GROUP BY w.begin_time, w.end_time;

-- vCPU 数（用于计算 CPU 利用率 = AAS / vCPU），来自快照期设置或当前设置
SELECT setting AS vcpu_hint
FROM {schema}.pg_settings_snapshot
WHERE snapshot_id = :snap_end_id AND name = 'max_parallel_workers';
-- 说明：PostgreSQL 不直接暴露物理 vCPU 数，此处仅作参考；
-- 若快照未采集该设置，或该值不能代表真实 vCPU 数，应向用户询问实际 vCPU 数量。

-- 峰值活跃会话（若采集了 pg_stat_activity 快照）
SELECT
  s.snapshot_time,
  COUNT(*) FILTER (WHERE a.state <> 'idle') AS active_sessions
FROM {schema}.pg_stat_activity_snapshot a
JOIN {schema}.snapshots s ON s.snapshot_id = a.snapshot_id
WHERE s.snapshot_time BETWEEN
  (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_begin_id)
  AND
  (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_end_id)
GROUP BY s.snapshot_time
ORDER BY active_sessions DESC
LIMIT 1;
