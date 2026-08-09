-- 04_top_sql_multi_dim.sql
-- 目的：按 总耗时/调用频率/平均延迟/IO/解析规划耗时/行数 六个维度输出 TOP 10 SQL
-- 占位符：{schema}；:snap_begin_id / :snap_end_id 为快照ID
-- 注：KES 的 sys_stat_statements 无 wal_bytes，故用金仓特有的解析+规划耗时替代 WAL 维度
-- 注意：整个脚本是单个语句（WITH CTE + 括号包裹的 UNION ALL 分支），
--       每个分支独立 ORDER BY + LIMIT，保证在 psql 与 python 两种执行器下都能跑通
--       （跨语句共享的 CTE 会失效，不要拆成多条语句）。
--       列结构统一为：dimension, queryid, query_text, metric_value, pct_of_total, delta_calls, avg_latency_ms

WITH deltas AS (
  SELECT
    e.dbid, e.userid, e.queryid,
    LEFT(e.query, 200) AS query_text,
    e.calls               - COALESCE(b.calls, 0)               AS delta_calls,
    e.total_exec_time     - COALESCE(b.total_exec_time, 0)     AS delta_total_exec_time,
    e.rows                - COALESCE(b.rows, 0)                AS delta_rows,
    e.shared_blks_read    - COALESCE(b.shared_blks_read, 0)    AS delta_shared_blks_read,
    -- 金仓特色：解析+规划耗时
    e.total_parse_time    - COALESCE(b.total_parse_time, 0)    AS delta_parse_plan_time
  FROM {schema}.sys_stat_statements_snapshot e
  LEFT JOIN {schema}.sys_stat_statements_snapshot b
    ON b.snapshot_id = :snap_begin_id
   AND b.dbid = e.dbid AND b.userid = e.userid AND b.queryid = e.queryid
  WHERE e.snapshot_id = :snap_end_id
),
totals AS (
  SELECT
    SUM(delta_total_exec_time) AS grand_total_exec_time,
    SUM(delta_shared_blks_read) AS grand_total_blks_read,
    SUM(delta_parse_plan_time) AS grand_total_parse_plan_time
  FROM deltas
)
-- 维度1：按总耗时排序
(
  SELECT 'total_exec_time' AS dimension, queryid, query_text,
    ROUND(delta_total_exec_time::numeric, 2) AS metric_value,
    ROUND((delta_total_exec_time / NULLIF((SELECT grand_total_exec_time FROM totals), 0) * 100)::numeric, 1) AS pct_of_total,
    delta_calls,
    ROUND((delta_total_exec_time / NULLIF(delta_calls, 0))::numeric, 2) AS avg_latency_ms
  FROM deltas
  ORDER BY delta_total_exec_time DESC NULLS LAST
  LIMIT 10
)
UNION ALL
-- 维度2：按调用频率排序
(
  SELECT 'calls' AS dimension, queryid, query_text,
    delta_calls::numeric AS metric_value,
    ROUND((delta_total_exec_time / NULLIF((SELECT grand_total_exec_time FROM totals), 0) * 100)::numeric, 1) AS pct_of_total,
    delta_calls,
    ROUND((delta_total_exec_time / NULLIF(delta_calls, 0))::numeric, 2) AS avg_latency_ms
  FROM deltas
  ORDER BY delta_calls DESC NULLS LAST
  LIMIT 10
)
UNION ALL
-- 维度3：按平均延迟排序（限定有一定调用量的 SQL，避免个别调用一次的极端值干扰）
(
  SELECT 'avg_latency' AS dimension, queryid, query_text,
    ROUND((delta_total_exec_time / NULLIF(delta_calls, 0))::numeric, 2) AS metric_value,
    ROUND((delta_total_exec_time / NULLIF((SELECT grand_total_exec_time FROM totals), 0) * 100)::numeric, 1) AS pct_of_total,
    delta_calls,
    ROUND((delta_total_exec_time / NULLIF(delta_calls, 0))::numeric, 2) AS avg_latency_ms
  FROM deltas
  WHERE delta_calls >= 5
  ORDER BY (delta_total_exec_time / NULLIF(delta_calls, 0)) DESC NULLS LAST
  LIMIT 10
)
UNION ALL
-- 维度4：按 IO 读取量排序
(
  SELECT 'shared_blks_read' AS dimension, queryid, query_text,
    delta_shared_blks_read::numeric AS metric_value,
    ROUND((delta_shared_blks_read / NULLIF((SELECT grand_total_blks_read FROM totals), 0) * 100)::numeric, 1) AS pct_of_total,
    delta_calls,
    NULL::numeric AS avg_latency_ms
  FROM deltas
  ORDER BY delta_shared_blks_read DESC NULLS LAST
  LIMIT 10
)
UNION ALL
-- 维度5：按解析+规划耗时排序（金仓特色，PG 无此维度）
(
  SELECT 'parse_plan_time' AS dimension, queryid, query_text,
    ROUND(delta_parse_plan_time::numeric, 2) AS metric_value,
    ROUND((delta_parse_plan_time / NULLIF((SELECT grand_total_parse_plan_time FROM totals), 0) * 100)::numeric, 1) AS pct_of_total,
    delta_calls,
    NULL::numeric AS avg_latency_ms
  FROM deltas
  ORDER BY delta_parse_plan_time DESC NULLS LAST
  LIMIT 10
)
UNION ALL
-- 维度6：按返回/处理行数排序
-- 注：avg_latency_ms 列在此维度中实际是“平均每次调用返回行数”（rows/call），
--     因 UNION ALL 列结构统一，复用该列名，报告呈现时请标注为 avg_rows_per_call。
(
  SELECT 'rows' AS dimension, queryid, query_text,
    delta_rows::numeric AS metric_value,
    ROUND((delta_total_exec_time / NULLIF((SELECT grand_total_exec_time FROM totals), 0) * 100)::numeric, 1) AS pct_of_total,
    delta_calls,
    ROUND((delta_rows::numeric / NULLIF(delta_calls, 0)), 1) AS avg_latency_ms
  FROM deltas
  ORDER BY delta_rows DESC NULLS LAST
  LIMIT 10
);
