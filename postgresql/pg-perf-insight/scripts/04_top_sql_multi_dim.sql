-- 04_top_sql_multi_dim.sql
-- 目的：按 总耗时/调用频率/平均延迟/IO/WAL/行数 六个维度输出 TOP 10 SQL
-- 占位符：{schema}；:snap_begin_id / :snap_end_id 为快照ID

WITH deltas AS (
  SELECT
    e.dbid, e.userid, e.queryid,
    LEFT(e.query, 200) AS query_text,
    e.calls               - COALESCE(b.calls, 0)               AS delta_calls,
    e.total_exec_time     - COALESCE(b.total_exec_time, 0)     AS delta_total_exec_time,
    e.rows                - COALESCE(b.rows, 0)                AS delta_rows,
    e.shared_blks_read    - COALESCE(b.shared_blks_read, 0)    AS delta_shared_blks_read,
    e.wal_bytes           - COALESCE(b.wal_bytes, 0)           AS delta_wal_bytes
  FROM {schema}.pg_stat_statements_snapshot e
  LEFT JOIN {schema}.pg_stat_statements_snapshot b
    ON b.snapshot_id = :snap_begin_id
   AND b.dbid = e.dbid AND b.userid = e.userid AND b.queryid = e.queryid
  WHERE e.snapshot_id = :snap_end_id
),
totals AS (
  SELECT
    SUM(delta_total_exec_time) AS grand_total_exec_time,
    SUM(delta_shared_blks_read) AS grand_total_blks_read,
    SUM(delta_wal_bytes) AS grand_total_wal_bytes
  FROM deltas
)
-- 维度1：按总耗时排序
SELECT 'total_exec_time' AS dimension, queryid, query_text,
  delta_total_exec_time AS metric_value,
  ROUND(delta_total_exec_time / NULLIF((SELECT grand_total_exec_time FROM totals), 0) * 100, 1) AS pct_of_total,
  delta_calls,
  ROUND(delta_total_exec_time / NULLIF(delta_calls, 0), 2) AS avg_latency_ms
FROM deltas
ORDER BY delta_total_exec_time DESC NULLS LAST
LIMIT 10;

-- 维度2：按调用频率排序
SELECT 'calls' AS dimension, queryid, query_text,
  delta_calls AS metric_value,
  ROUND(delta_total_exec_time / NULLIF(delta_calls, 0), 2) AS avg_latency_ms,
  delta_shared_blks_read
FROM deltas
ORDER BY delta_calls DESC NULLS LAST
LIMIT 10;

-- 维度3：按平均延迟排序（限定有一定调用量的 SQL，避免个别调用一次的极端值干扰）
SELECT 'avg_latency' AS dimension, queryid, query_text,
  ROUND(delta_total_exec_time / NULLIF(delta_calls, 0), 2) AS metric_value,
  delta_calls, delta_total_exec_time
FROM deltas
WHERE delta_calls >= 5
ORDER BY (delta_total_exec_time / NULLIF(delta_calls, 0)) DESC NULLS LAST
LIMIT 10;

-- 维度4：按 IO 读取量排序
SELECT 'shared_blks_read' AS dimension, queryid, query_text,
  delta_shared_blks_read AS metric_value,
  ROUND(delta_shared_blks_read / NULLIF((SELECT grand_total_blks_read FROM totals), 0) * 100, 1) AS pct_of_total,
  delta_calls
FROM deltas
ORDER BY delta_shared_blks_read DESC NULLS LAST
LIMIT 10;

-- 维度5：按 WAL 生成量排序（PG13+，若列不存在请删除本段）
SELECT 'wal_bytes' AS dimension, queryid, query_text,
  delta_wal_bytes AS metric_value,
  ROUND(delta_wal_bytes / NULLIF((SELECT grand_total_wal_bytes FROM totals), 0) * 100, 1) AS pct_of_total,
  delta_calls
FROM deltas
ORDER BY delta_wal_bytes DESC NULLS LAST
LIMIT 10;

-- 维度6：按返回/处理行数排序
SELECT 'rows' AS dimension, queryid, query_text,
  delta_rows AS metric_value,
  delta_calls,
  ROUND(delta_rows::numeric / NULLIF(delta_calls, 0), 1) AS avg_rows_per_call
FROM deltas
ORDER BY delta_rows DESC NULLS LAST
LIMIT 10;
