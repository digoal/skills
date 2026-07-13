-- 07_by_user_app.sql
-- 目的：按用户拆解 pg_stat_statements 负载；按应用拆解活跃连接数
-- 占位符：{schema}；:snap_begin_id / :snap_end_id 为快照ID

-- 7.1 按用户（userid）聚合总耗时贡献
WITH deltas AS (
  SELECT
    e.userid,
    e.total_exec_time - COALESCE(b.total_exec_time, 0) AS delta_total_exec_time,
    e.calls           - COALESCE(b.calls, 0)           AS delta_calls
  FROM {schema}.pg_stat_statements_snapshot e
  LEFT JOIN {schema}.pg_stat_statements_snapshot b
    ON b.snapshot_id = :snap_begin_id
   AND b.dbid = e.dbid AND b.userid = e.userid AND b.queryid = e.queryid
  WHERE e.snapshot_id = :snap_end_id
)
SELECT
  userid,
  SUM(delta_total_exec_time) AS total_db_time_ms,
  SUM(delta_calls) AS total_calls,
  ROUND(SUM(delta_total_exec_time) / NULLIF(SUM(SUM(delta_total_exec_time)) OVER (), 0) * 100, 1) AS pct_of_total
FROM deltas
GROUP BY userid
ORDER BY total_db_time_ms DESC;

-- 7.2 按应用（application_name）统计窗口内平均活跃连接数
SELECT
  a.usename,
  a.application_name,
  ROUND(AVG(active_count), 1) AS avg_active_connections,
  MAX(active_count) AS peak_active_connections
FROM (
  SELECT
    s.snapshot_time,
    a.usename,
    a.application_name,
    COUNT(*) FILTER (WHERE a.state <> 'idle') AS active_count
  FROM {schema}.pg_stat_activity_snapshot a
  JOIN {schema}.snapshots s ON s.snapshot_id = a.snapshot_id
  WHERE s.snapshot_time BETWEEN
    (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_begin_id)
    AND
    (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_end_id)
  GROUP BY s.snapshot_time, a.usename, a.application_name
) a
GROUP BY a.usename, a.application_name
ORDER BY avg_active_connections DESC
LIMIT 20;

-- 说明：若 pg_stat_activity_snapshot 只采集了 state <> 'idle' 的行，
-- 上面的 FILTER 条件可去掉（因为快照本身已过滤），并在报告中注明
-- "活跃连接数可能偏低，仅统计非空闲连接"。
