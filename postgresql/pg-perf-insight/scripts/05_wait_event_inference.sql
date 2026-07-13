-- 05_wait_event_inference.sql
-- 目的：结合 pg_stat_statements 差值 与 pg_stat_activity 历史快照，
--       推断等待事件画像（CPU / IO / Lock / WAL / 其他）
-- 占位符：{schema}；:snap_begin_id / :snap_end_id 为快照ID

-- 5.1 基于 pg_stat_statements 差值的 CPU / IO / WAL 占比推断
WITH deltas AS (
  SELECT
    e.queryid,
    e.total_exec_time  - COALESCE(b.total_exec_time, 0)  AS delta_total_exec_time,
    e.shared_blks_read - COALESCE(b.shared_blks_read, 0) AS delta_shared_blks_read,
    e.blk_read_time     - COALESCE(b.blk_read_time, 0)    AS delta_blk_read_time,
    e.wal_bytes          - COALESCE(b.wal_bytes, 0)        AS delta_wal_bytes
  FROM {schema}.pg_stat_statements_snapshot e
  LEFT JOIN {schema}.pg_stat_statements_snapshot b
    ON b.snapshot_id = :snap_begin_id AND b.queryid = e.queryid
  WHERE e.snapshot_id = :snap_end_id
)
SELECT
  SUM(delta_total_exec_time) AS total_exec_time_ms,
  SUM(delta_blk_read_time)   AS total_io_wait_ms,
  SUM(delta_wal_bytes)       AS total_wal_bytes,
  -- IO占比：若 track_io_timing 未开启，delta_blk_read_time 恒为0，需改用 shared_blks_read 做近似
  ROUND(SUM(delta_blk_read_time) / NULLIF(SUM(delta_total_exec_time), 0) * 100, 1) AS io_wait_pct_by_time,
  ROUND(
    (SUM(delta_total_exec_time) - SUM(delta_blk_read_time))
    / NULLIF(SUM(delta_total_exec_time), 0) * 100, 1
  ) AS cpu_pct_estimate
FROM deltas;

-- 5.2 锁等待频次：从 pg_stat_activity 历史快照统计 wait_event_type='Lock' 出现次数
SELECT
  a.wait_event_type,
  a.wait_event,
  COUNT(*) AS occurrence_count
FROM {schema}.pg_stat_activity_snapshot a
JOIN {schema}.snapshots s ON s.snapshot_id = a.snapshot_id
WHERE s.snapshot_time BETWEEN
  (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_begin_id)
  AND
  (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_end_id)
  AND a.wait_event_type IS NOT NULL
GROUP BY a.wait_event_type, a.wait_event
ORDER BY occurrence_count DESC
LIMIT 20;

-- 说明：将 5.1（CPU/IO/WAL）与 5.2（Lock 频次占比）综合，
-- 按 CPU/IO/Lock/WAL/其他 五类合计占比≈100%，用文字饼图/表格形式呈现，
-- 若 5.2 无 Lock 记录，则锁等待占比记为接近 0% 并说明"未观测到显著锁等待"。
