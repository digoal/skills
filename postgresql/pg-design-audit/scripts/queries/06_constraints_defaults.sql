-- 06_constraints_defaults.sql :: 默认值与约束检查（只读）
\pset border 0

-- [6.1] 缺少主键的表
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name, 'missing_primary_key' AS issue
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND NOT EXISTS (
    SELECT 1 FROM pg_constraint con WHERE con.conrelid = c.oid AND con.contype = 'p'
  )
  AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid) -- 排除分区子表（主键通常在父表定义）
ORDER BY 2,3;

-- [6.2] 缺少 created_at / updated_at 时间戳字段的表
WITH ts_cols AS (
  SELECT a.attrelid,
         bool_or(a.attname ~* '(creat)' AND format_type(a.atttypid,a.atttypmod) LIKE '%timestamp%') AS has_created,
         bool_or(a.attname ~* '(updat|modif)' AND format_type(a.atttypid,a.atttypmod) LIKE '%timestamp%') AS has_updated
  FROM pg_attribute a
  WHERE a.attnum > 0 AND NOT a.attisdropped
  GROUP BY a.attrelid
)
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name,
       coalesce(t.has_created,false) AS has_created_at, coalesce(t.has_updated,false) AS has_updated_at,
       'missing_audit_timestamp' AS issue
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN ts_cols t ON t.attrelid = c.oid
WHERE c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND (coalesce(t.has_created,false) = false OR coalesce(t.has_updated,false) = false)
ORDER BY 2,3;

-- [6.3] 外键列未建索引（外键列未作为任何索引的最左列出现）
SELECT current_database() AS db, n.nspname AS schema_name, t.relname AS table_name,
       con.conname AS fk_constraint, a.attname AS fk_column, 'fk_without_index' AS issue
FROM pg_constraint con
JOIN pg_class t ON t.oid = con.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = con.conkey[1]
WHERE con.contype = 'f'
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND NOT EXISTS (
    SELECT 1 FROM pg_index i
    WHERE i.indrelid = con.conrelid AND i.indkey[0] = con.conkey[1]
  )
ORDER BY 2,3;

-- [6.4] 可为 NULL 但业务上大概率不应为空的字段（username/email/order_no 等）
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
       'nullable_but_likely_required' AS issue
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND NOT a.attisdropped AND NOT a.attnotnull
  AND c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND a.attname ~* '(username|user_name|email|order_no|order_id|mobile|phone|id_card|account)'
ORDER BY 2,3,4;
