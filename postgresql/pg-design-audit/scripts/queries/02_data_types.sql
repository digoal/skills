-- 02_data_types.sql :: 字段类型选择合理性检查（只读）
\pset border 0

-- [2.1] 疑似布尔字段但类型非 boolean
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS current_type,
       col_description(c.oid, a.attnum) AS column_comment,
       'bool_stored_as_wrong_type' AS issue
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND format_type(a.atttypid, a.atttypmod) NOT IN ('boolean')
  AND (
    a.attname ~* '^(is_|has_|can_|should_|need_)' OR a.attname ~* '(_flag|_bool|_yn)$'
    OR col_description(c.oid, a.attnum) LIKE '%是否%'
  )
  AND format_type(a.atttypid, a.atttypmod) IN ('integer','smallint','bigint','text','character varying')
ORDER BY 2,3,4;

-- [2.2] 疑似时间字段但类型为字符串
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS current_type, 'time_stored_as_string' AS issue
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND (a.attname ~* '(_date|_time|_at|_ts)$' OR a.attname ~* '^(date|time)_')
  AND format_type(a.atttypid, a.atttypmod) IN ('text','character varying','character')
ORDER BY 2,3,4;

-- [2.3] 疑似 JSON 字段但类型为字符串
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS current_type, 'json_stored_as_string' AS issue
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND (a.attname ~* '(json|_data|_extra|_meta|extra_info|metadata)')
  AND format_type(a.atttypid, a.atttypmod) IN ('text','character varying')
ORDER BY 2,3,4;

-- [2.4] 主键/外键使用 varchar 而非 integer/bigint/uuid
SELECT current_database() AS db, n.nspname AS schema_name, t.relname AS table_name, a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS current_type,
       CASE con.contype WHEN 'p' THEN 'primary_key' WHEN 'f' THEN 'foreign_key' END AS constraint_type,
       'pk_fk_uses_varchar' AS issue
FROM pg_constraint con
JOIN pg_class t ON t.oid = con.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(con.conkey)
WHERE con.contype IN ('p','f')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND format_type(a.atttypid, a.atttypmod) IN ('character varying','text')
ORDER BY 2,3,4;

-- [2.5] 无长度限制的 varchar / 应有固定长度关键词字段使用 text
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS current_type, 'unbounded_or_overused_text' AS issue
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND (
    (format_type(a.atttypid, a.atttypmod) = 'character varying' AND a.atttypmod = -1)
    OR (format_type(a.atttypid, a.atttypmod) = 'text' AND a.attname ~* '(_code|_no$|_id$|_status$|^code|^no_|^status)')
  )
ORDER BY 2,3,4;

-- [2.5b] text 字段总数统计（按库汇总，用于判断是否过度使用）
SELECT current_database() AS db, count(*) AS total_text_columns
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND format_type(a.atttypid, a.atttypmod) = 'text';

-- [2.6] 金额字段使用 float/real 而非 numeric/decimal
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS current_type, 'money_uses_float' AS issue
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND (a.attname ~* '(price|amount|money|balance|fee|cost|salary|金额|价格)')
  AND format_type(a.atttypid, a.atttypmod) IN ('real','double precision')
ORDER BY 2,3,4;

-- [2.7] IP 地址字段未使用 inet 类型
SELECT current_database() AS db, n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS current_type, 'ip_not_inet' AS issue
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
  AND (a.attname ~* '(^ip$|_ip$|^ip_|ip_addr|ipaddress)')
  AND format_type(a.atttypid, a.atttypmod) NOT IN ('inet','cidr')
ORDER BY 2,3,4;
