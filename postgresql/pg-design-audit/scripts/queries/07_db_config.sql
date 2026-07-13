-- 07_db_config.sql :: 数据库级配置与模式检查（只读）
\pset border 0

-- [7.1] 当前会话默认事务隔离级别（反映集群级 default_transaction_isolation）
SELECT current_database() AS db, current_setting('default_transaction_isolation') AS default_isolation,
       CASE WHEN current_setting('default_transaction_isolation') <> 'read committed'
            THEN 'non_default_isolation_level' ELSE 'ok' END AS issue;

-- [7.1b] 数据库级单独覆盖的事务隔离配置（ALTER DATABASE ... SET）
SELECT d.datname AS db, s.setconfig, 'db_level_isolation_override_review_needed' AS issue
FROM pg_db_role_setting s
JOIN pg_database d ON d.oid = s.setdatabase
WHERE s.setconfig::text ILIKE '%isolation%';

-- [7.2] 是否启用数据校验和 data_checksums（集群级，PG12+ 可用 pg_control_checksum 或 SHOW）
SHOW data_checksums;

-- [7.3] public 模式下直接建表的情况（安全风险提示）
SELECT current_database() AS db, c.relname AS table_name,
       pg_get_userbyid(c.relowner) AS owner, 'table_created_directly_in_public_schema' AS issue
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r','p')
ORDER BY 2;

-- [7.4] public 模式权限检查（是否对 PUBLIC 角色开放 CREATE，常见安全风险来源）
SELECT current_database() AS db, nspname AS schema_name,
       has_schema_privilege('public', nspname, 'CREATE') AS public_role_can_create,
       'public_schema_open_create_review_needed' AS issue
FROM pg_namespace WHERE nspname = 'public';
