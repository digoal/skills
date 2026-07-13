-- pg-find-unused-index 核心查询
-- 用法: psql "host=<host> port=<port> user=<user> dbname=<dbname>" -f find_unused_indexes.sql
-- 密码通过环境变量 PGPASSWORD 或 ~/.pgpass 提供，不要写在连接串里。

\pset format aligned
\pset border 2

-- 0. 上下文信息：统计窗口是否足够长
SELECT
  current_database()               AS database,
  stats_reset,
  now() - stats_reset               AS stats_age,
  (SELECT pg_postmaster_start_time()) AS instance_start_time,
  now() - (SELECT pg_postmaster_start_time()) AS instance_uptime
FROM pg_stat_database
WHERE datname = current_database();

-- 1. 未使用索引明细（按索引大小倒序）
SELECT
  n.nspname                                      AS schema_name,
  s.relname                                       AS table_name,
  s.indexrelname                                  AS index_name,
  pg_size_pretty(pg_relation_size(s.indexrelid))  AS index_size,
  pg_size_pretty(pg_relation_size(s.relid))       AS table_size,
  round(
    100.0 * pg_relation_size(s.indexrelid) /
    NULLIF(pg_relation_size(s.relid), 0), 1
  )                                                AS index_pct_of_table,
  s.idx_scan,
  i.indisunique                                   AS is_unique,
  i.indisexclusion                                AS is_exclusion,
  EXISTS (
    SELECT 1 FROM pg_constraint c
    WHERE c.conindid = s.indexrelid
      AND c.contype IN ('f', 'u', 'p')
  )                                                AS backs_constraint,
  pg_get_indexdef(s.indexrelid)                   AS index_def
FROM pg_stat_user_indexes s
JOIN pg_index i     ON i.indexrelid = s.indexrelid
JOIN pg_class c      ON c.oid = s.relid
JOIN pg_namespace n  ON n.oid = c.relnamespace
WHERE s.idx_scan = 0
  AND NOT i.indisprimary
ORDER BY pg_relation_size(s.indexrelid) DESC;

-- 2. 本库可回收空间合计（不含仍支撑约束的索引）
SELECT
  pg_size_pretty(SUM(pg_relation_size(s.indexrelid))) AS reclaimable_size
FROM pg_stat_user_indexes s
JOIN pg_index i ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0
  AND NOT i.indisprimary
  AND NOT EXISTS (
    SELECT 1 FROM pg_constraint c
    WHERE c.conindid = s.indexrelid
      AND c.contype IN ('f', 'u', 'p')
  );
