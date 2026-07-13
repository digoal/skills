-- 01_naming.sql :: 对象命名规范检查（只读）
-- 用法: psql "<connstr>" -d <dbname> -A -F'|' -t -f 01_naming.sql
\pset border 0

-- [1.1] 表/视图/物化视图命名可疑（含临时/测试特征词、纯数字、单字母）
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS object_name,
       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'v' THEN 'view' WHEN 'm' THEN 'matview' WHEN 'p' THEN 'partitioned_table' END AS obj_type,
       'suspicious_name' AS issue
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','v','m','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND (
    c.relname ~* '(^|_)(aaa+|bbb+|test|temp|tmp|old|backup|copy|111|222)(_|$)'
    OR c.relname ~ '^[0-9]+$'
    OR length(c.relname) = 1
    OR c.relname ~ '[^\x00-\x7F]'          -- 含中文/非ASCII字符
    OR c.relname ~ '[ \-]'                  -- 含空格或连字符，SQL中需引号包裹
  )
ORDER BY 2,3;

-- [1.2] 字段命名可疑：临时特征词 / 与表名重复 / 保留关键字 / 特殊字符
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
       'suspicious_column_name' AS issue
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND NOT a.attisdropped
  AND c.relkind IN ('r','v','m','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND (
    a.attname ~* '(^|_)(aaa+|bbb+|test|temp|tmp|old|backup|copy|111|222)(_|$)'
    OR a.attname = c.relname
    OR lower(a.attname) IN ('order','group','select','from','user','table','column','check','primary',
                             'references','when','case','all','default','grant','union','where')
    OR a.attname ~ '[^\x00-\x7F]'
    OR a.attname ~ '[ \-]'
  )
ORDER BY 2,3,4;

-- [1.3] 索引命名可疑（含临时特征词 / 纯数字 / 中文）
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS index_name,
       t.relname AS table_name, 'suspicious_index_name' AS issue
FROM pg_class c
JOIN pg_index i ON i.indexrelid = c.oid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'i'
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND (
    c.relname ~* '(^|_)(aaa+|bbb+|test|temp|tmp|old|backup|copy|111|222)(_|$)'
    OR c.relname ~ '^[0-9]+$'
    OR c.relname ~ '[^\x00-\x7F]'
  )
ORDER BY 2,3;
