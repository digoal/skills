-- 08_anomaly_detection.sql
-- 目的：检测负载突增、执行计划疑似变化、窗口内新出现的 queryid
-- 占位符：{schema}；:snap_begin_id / :snap_end_id 为快照ID

-- 8.1 相邻快照间 AAS 突增检测（窗口内若有多于2个快照，可看到更细粒度趋势）
WITH per_snapshot AS (
  SELECT
    s.snapshot_id,
    s.snapshot_time,
    LAG(s.snapshot_id) OVER (ORDER BY s.snapshot_time) AS prev_snapshot_id,
    LAG(s.snapshot_time) OVER (ORDER BY s.snapshot_time) AS prev_snapshot_time
  FROM {schema}.snapshots s
  WHERE s.snapshot_time BETWEEN
    (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_begin_id)
    AND
    (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_end_id)
),
pairwise_aas AS (
  SELECT
    p.snapshot_time,
    (
      SELECT SUM(e.total_exec_time - COALESCE(b.total_exec_time, 0))
      FROM {schema}.pg_stat_statements_snapshot e
      LEFT JOIN {schema}.pg_stat_statements_snapshot b
        ON b.snapshot_id = p.prev_snapshot_id
       AND b.dbid = e.dbid AND b.userid = e.userid AND b.queryid = e.queryid
      WHERE e.snapshot_id = p.snapshot_id
    ) / NULLIF(EXTRACT(EPOCH FROM (p.snapshot_time - p.prev_snapshot_time)), 0) / 1000.0 AS interval_aas
  FROM per_snapshot p
  WHERE p.prev_snapshot_id IS NOT NULL
)
SELECT * FROM pairwise_aas ORDER BY interval_aas DESC NULLS LAST;
-- interval_aas 明显高于窗口整体 AAS 的时间点即为负载突增点，
-- 建议提示用户针对该更小的时间段重新执行本技能以精确定位。

-- 8.2 同一 queryid 平均延迟显著变化（疑似执行计划变化/参数嗅探/统计信息过期）
SELECT
  e.queryid,
  LEFT(e.query, 200) AS query_text,
  ROUND(b.total_exec_time / NULLIF(b.calls, 0), 2) AS avg_latency_begin_ms,
  ROUND(e.total_exec_time / NULLIF(e.calls, 0), 2) AS avg_latency_end_ms,
  ROUND(
    (e.total_exec_time / NULLIF(e.calls, 0)) / NULLIF(b.total_exec_time / NULLIF(b.calls, 0), 0),
    2
  ) AS latency_ratio
FROM {schema}.pg_stat_statements_snapshot e
JOIN {schema}.pg_stat_statements_snapshot b
  ON b.snapshot_id = :snap_begin_id
 AND b.dbid = e.dbid AND b.userid = e.userid AND b.queryid = e.queryid
WHERE e.snapshot_id = :snap_end_id
  AND b.calls > 0 AND e.calls > 0
  AND (e.total_exec_time / NULLIF(e.calls, 0)) / NULLIF(b.total_exec_time / NULLIF(b.calls, 0), 0) >= 2
ORDER BY latency_ratio DESC
LIMIT 10;

-- 8.3 窗口内新出现的 queryid（snap_end 有、snap_begin 无）
SELECT
  e.queryid,
  LEFT(e.query, 200) AS query_text,
  e.calls AS delta_calls,
  e.total_exec_time AS delta_total_exec_time
FROM {schema}.pg_stat_statements_snapshot e
WHERE e.snapshot_id = :snap_end_id
  AND NOT EXISTS (
    SELECT 1 FROM {schema}.pg_stat_statements_snapshot b
    WHERE b.snapshot_id = :snap_begin_id
      AND b.dbid = e.dbid AND b.userid = e.userid AND b.queryid = e.queryid
  )
ORDER BY e.total_exec_time DESC
LIMIT 10;
