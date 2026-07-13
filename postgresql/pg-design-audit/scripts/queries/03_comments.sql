-- 03_comments.sql :: 注释(Comment)缺失检查（只读）
\pset border 0

-- [3.1] 无注释的表/视图
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS object_name,
       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'v' THEN 'view' WHEN 'p' THEN 'partitioned_table' END AS obj_type,
       'missing_object_comment' AS issue
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','v','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND obj_description(c.oid,'pg_class') IS NULL
ORDER BY 2,3;

-- [3.2] 无注释的字段
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
       'missing_column_comment' AS issue
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND col_description(c.oid, a.attnum) IS NULL
ORDER BY 2,3,4;

-- [3.3] 汇总：本库对象总数 / 无注释对象数 / 字段总数 / 无注释字段数（供计算缺失率 >30% 标红）
SELECT current_database() AS db,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE c.relkind IN ('r','v','p') AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')) AS total_objects,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE c.relkind IN ('r','v','p') AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
     AND obj_description(c.oid,'pg_class') IS NULL) AS objects_without_comment,
  (SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE a.attnum>0 AND NOT a.attisdropped AND c.relkind IN ('r','p')
     AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')) AS total_columns,
  (SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE a.attnum>0 AND NOT a.attisdropped AND c.relkind IN ('r','p')
     AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
     AND col_description(c.oid,a.attnum) IS NULL) AS columns_without_comment;
