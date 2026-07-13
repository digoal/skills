-- 06_by_database.sql
-- 目的：按数据库拆解负载（AAS贡献、总耗时占比、事务数、IO读占比）
-- 占位符：{schema}；:snap_begin_id / :snap_end_id 为快照ID

-- 方式A：优先使用 pg_stat_database 快照（更准确的事务数与IO统计）
WITH db_deltas AS (
  SELECT
    e.datname,
    e.xact_commit - COALESCE(b.xact_commit, 0)   AS delta_xact_commit,
    e.xact_rollback - COALESCE(b.xact_rollback, 0) AS delta_xact_rollback,
    e.blks_read - COALESCE(b.blks_read, 0)       AS delta_blks_read,
    e.blks_hit  - COALESCE(b.blks_hit, 0)        AS delta_blks_hit
  FROM {schema}.pg_stat_database_snapshot e
  LEFT JOIN {schema}.pg_stat_database_snapshot b
    ON b.snapshot_id = :snap_begin_id AND b.datid = e.datid
  WHERE e.snapshot_id = :snap_end_id
)
SELECT
  datname,
  delta_xact_commit + delta_xact_rollback AS total_transactions,
  delta_blks_read,
  ROUND(delta_blks_read::numeric / NULLIF(SUM(delta_blks_read) OVER (), 0) * 100, 1) AS blks_read_pct
FROM db_deltas
ORDER BY total_transactions DESC;

-- 方式B：从 pg_stat_statements 差值按 dbid 聚合总耗时占比（与快照关联需 pg_database 快照或 oid->name 映射，
-- 若无映射表，可直接展示 dbid，提示用户自行核对 pg_database.oid）
WITH deltas AS (
  SELECT
    e.dbid,
    e.total_exec_time - COALESCE(b.total_exec_time, 0) AS delta_total_exec_time
  FROM {schema}.pg_stat_statements_snapshot e
  LEFT JOIN {schema}.pg_stat_statements_snapshot b
    ON b.snapshot_id = :snap_begin_id
   AND b.dbid = e.dbid AND b.userid = e.userid AND b.queryid = e.queryid
  WHERE e.snapshot_id = :snap_end_id
)
SELECT
  dbid,
  SUM(delta_total_exec_time) AS total_db_time_ms,
  ROUND(SUM(delta_total_exec_time) / NULLIF(SUM(SUM(delta_total_exec_time)) OVER (), 0) * 100, 1) AS pct_of_total
FROM deltas
GROUP BY dbid
ORDER BY total_db_time_ms DESC;
