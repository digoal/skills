-- 04_large_tables_partition.sql :: 大表与分区检查（只读）
\pset border 0

-- [4.1] 超过 1GB 的表（含分区父表），标注是否已分区
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size_pretty,
       pg_total_relation_size(c.oid) AS total_size_bytes,
       c.reltuples::bigint AS est_rows,
       CASE WHEN c.relkind = 'p' THEN true
            WHEN EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid) THEN NULL -- 是某分区表的子分区
            ELSE false END AS is_partitioned,
       'large_table' AS issue
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid) -- 排除子分区，避免重复统计
  AND pg_total_relation_size(c.oid) > 1024*1024*1024
ORDER BY total_size_bytes DESC;

-- [4.2] 分区数超过 100 的分区表（"分区过多风险"）
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name,
       count(ch.inhrelid) AS partition_count, 'too_many_partitions' AS issue
FROM pg_partitioned_table pt
JOIN pg_class c ON c.oid = pt.partrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_inherits ch ON ch.inhparent = c.oid
GROUP BY 1,2,3
HAVING count(ch.inhrelid) > 100
ORDER BY partition_count DESC;
