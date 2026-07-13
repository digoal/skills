-- 05_index_design.sql :: 索引设计问题检查（只读）
\pset border 0

-- [5.1] 完全重复的索引（字段组合与顺序完全一致）
SELECT current_database() AS db, indrelid::regclass::text AS table_name,
       array_agg(indexrelid::regclass::text ORDER BY indexrelid) AS duplicate_indexes,
       indkey::text AS column_positions, 'exact_duplicate_index' AS issue
FROM pg_index
WHERE indrelid IN (
  SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
)
GROUP BY indrelid, indkey
HAVING count(*) > 1
ORDER BY 1;

-- [5.2] 冗余索引：一个索引的字段是另一个索引的最左前缀
WITH idx AS (
  SELECT i.indexrelid, i.indrelid, i.indkey::text AS keys,
         ix.relname AS index_name, t.relname AS table_name, n.nspname AS schema_name
  FROM pg_index i
  JOIN pg_class ix ON ix.oid = i.indexrelid
  JOIN pg_class t ON t.oid = i.indrelid
  JOIN pg_namespace n ON n.oid = t.relnamespace
  WHERE n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
    AND i.indisvalid
)
SELECT current_database() AS db, a.schema_name, a.table_name,
       a.index_name AS redundant_index, b.index_name AS covering_index,
       a.keys AS redundant_index_keys, b.keys AS covering_index_keys,
       'redundant_prefix_index' AS issue
FROM idx a
JOIN idx b ON a.indrelid = b.indrelid AND a.indexrelid <> b.indexrelid
WHERE b.keys LIKE a.keys || '%' AND length(b.keys) > length(a.keys)
ORDER BY 2,3;

-- [5.3] 未使用的索引（idx_scan = 0）
-- 注意：PostgreSQL 目录不记录索引创建时间，"超过7天"需结合 pg_stat_database.stats_reset 人工判断，
-- 若 stats_reset 距今不足7天，本项结果仅供参考，需人工复核。
SELECT current_database() AS db, s.schemaname AS schema_name, s.relname AS table_name,
       s.indexrelname AS index_name, s.idx_scan,
       pg_size_pretty(pg_relation_size(s.indexrelid)) AS index_size,
       (SELECT stats_reset FROM pg_stat_database WHERE datname = current_database()) AS stats_reset_time,
       'unused_index' AS issue
FROM pg_stat_user_indexes s
JOIN pg_index i ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0
  AND NOT i.indisprimary AND NOT i.indisunique -- 唯一/主键索引即使未被扫描也可能承担约束作用，单独提示而非直接判定冗余
  AND s.schemaname NOT IN ('pg_catalog','information_schema','pg_toast')
ORDER BY 2,3;

-- [5.3b] 未使用但承担唯一/主键约束的索引（需人工复核，不建议直接删除）
SELECT current_database() AS db, s.schemaname AS schema_name, s.relname AS table_name,
       s.indexrelname AS index_name, s.idx_scan, 'unused_unique_or_pk_index_review_needed' AS issue
FROM pg_stat_user_indexes s
JOIN pg_index i ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0 AND (i.indisprimary OR i.indisunique)
  AND s.schemaname NOT IN ('pg_catalog','information_schema','pg_toast')
ORDER BY 2,3;

-- [5.4] 宽度过大的组合索引（索引字段类型总长度估算超过 256 字节）
SELECT current_database() AS db, n.nspname AS schema_name, t.relname AS table_name, ix.relname AS index_name,
       sum(CASE WHEN a.attlen > 0 THEN a.attlen ELSE 32 END) AS est_total_bytes, -- 变长类型无法精确得知，按32字节估算，仅供参考
       'wide_composite_index' AS issue
FROM pg_index i
JOIN pg_class ix ON ix.oid = i.indexrelid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey)
WHERE n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND array_length(i.indkey,1) > 1
GROUP BY 1,2,3,4
HAVING sum(CASE WHEN a.attlen > 0 THEN a.attlen ELSE 32 END) > 256
ORDER BY 5 DESC;
