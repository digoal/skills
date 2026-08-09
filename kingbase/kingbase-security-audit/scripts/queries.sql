-- ============================================================
-- kingbase-security-audit：只读安全审计查询集（KingbaseES / 金仓）
-- 使用方式：psql -h <host> -p <port> -U <user> -d <database> -f queries.sql
--   （连接参数也可通过环境变量 PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDBNAME 提供；
--     默认值为 127.0.0.1/5432/kingbase/kingbase/123456）
-- 严禁在本文件中添加任何 CREATE/ALTER/DROP/INSERT/UPDATE/DELETE 语句
-- ============================================================

-- 会话级只读兜底（务必最先执行）
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;

\echo '===== Step 1: 基本信息 ====='
SELECT version();
SELECT pg_postmaster_start_time();
SHOW data_directory;
SHOW shared_preload_libraries;
SHOW max_connections;
SELECT setting AS database_mode FROM pg_settings WHERE name = 'database_mode';

\echo '===== Step 1: 数据库列表 ====='
SELECT datname, datallowconn, datconnlimit
FROM pg_database
WHERE datistemplate = false
ORDER BY datname;

\echo '===== Step 1: 角色与属性 ====='
SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb,
       rolcanlogin, rolreplication, rolbypassrls, rolconnlimit, rolvaliduntil
FROM pg_roles
ORDER BY rolsuper DESC, rolname;

\echo '===== Step 1: 空密码 / 密码永不过期角色（需要superuser或pg_monitor，否则报错请忽略并记为受限项）====='
SELECT usename, passwd IS NULL AS no_password, valuntil
FROM pg_shadow
ORDER BY no_password DESC;

\echo '===== Step 2.1: sys_hba.conf 规则（需要superuser或pg_read_all_settings/pg_monitor）====='
SHOW hba_file;
SELECT line_number, type, database, user_name, address, netmask, auth_method, error
FROM pg_hba_file_rules
ORDER BY line_number;
-- 若上一句报错（老版本无该视图），可降级尝试：
-- SELECT line_number, type, database, user_name, address, netmask, auth_method, error
-- FROM sys_catalog.sys_hba_file_rules
-- ORDER BY line_number;

\echo '===== Step 2.2: 超级用户列表 ====='
SELECT rolname FROM pg_roles WHERE rolsuper = true;

\echo '===== Step 2.2: 正在使用超级用户账号的应用连接 ====='
SELECT a.pid, a.usename, a.datname, a.client_addr, a.application_name,
       a.state, a.backend_start
FROM pg_stat_activity a
JOIN pg_roles r ON a.usename = r.rolname
WHERE r.rolsuper = true
  AND a.pid <> pg_backend_pid();

\echo '===== Step 2.2: 使用超级用户的流复制连接 ====='
SELECT pid, usename, client_addr, application_name, state, sync_state
FROM pg_stat_replication;

\echo '===== Step 3.1: 三权分立（sepapower）检查 ====='
-- 注意：sepapower 通常只出现在 shared_preload_libraries 中，pg_extension 里可能查不到，属正常
SHOW shared_preload_libraries;
SELECT extname, extversion FROM pg_extension WHERE extname = 'sepapower';
SELECT name, setting FROM pg_settings WHERE name LIKE 'sepapower%' OR name = 'sync_security' ORDER BY name;
SELECT rolname, rolsuper, rolcreaterole, rolcanlogin FROM pg_roles WHERE rolname IN ('sao', 'sso') ORDER BY rolname;

\echo '===== Step 3.2: 数据库审计（sysaudit）检查 ====='
SELECT extname, extversion FROM pg_extension WHERE extname = 'sysaudit';
-- 以下两条在三权分立开启后仅 SAO/SSO 可查（超级用户也会 permission denied，属正常，记为受限项）
SELECT * FROM sysaudit.all_audit_rules;
SELECT * FROM sysaudit.all_ids_rules;

\echo '===== Step 3.3: 强制访问控制（sysmac / src_restrict）检查 ====='
SELECT extname, extversion FROM pg_extension WHERE extname IN ('sysmac', 'src_restrict');
SELECT name, setting FROM pg_settings WHERE name LIKE 'restrict%' ORDER BY name;
-- 以下表仅 SAO/SSO 可查（permission denied 属正常，记为受限项）
SELECT * FROM sysmac.sysmac_level;
SELECT * FROM sysmac.sysmac_user;

\echo '===== Step 3.4: 透明列加密（kdb_ce_col）与数据脱敏（anon）检查 ====='
SELECT * FROM sys_catalog.kdb_ce_col;
SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'anon';
SELECT extname, extversion FROM pg_extension WHERE extname LIKE '%anon%';

\echo '===== Step 5: 非内网来源的活跃连接 ====='
SELECT pid, usename, datname, client_addr, application_name, backend_start
FROM pg_stat_activity
WHERE client_addr IS NOT NULL
  AND NOT (
    client_addr <<= '10.0.0.0/8'::inet OR
    client_addr <<= '172.16.0.0/12'::inet OR
    client_addr <<= '192.168.0.0/16'::inet OR
    client_addr <<= '127.0.0.0/8'::inet
  );

\echo '===== Step 5: 全部连接来源统计 ====='
SELECT client_addr, usename, datname, application_name, count(*) AS conn_count
FROM pg_stat_activity
WHERE client_addr IS NOT NULL
GROUP BY client_addr, usename, datname, application_name
ORDER BY conn_count DESC;

\echo '===== Step 6: 活跃会话概览 ====='
SELECT pid, usename, datname, state, wait_event_type, wait_event,
       now() - query_start AS duration, left(query, 200) AS query_snippet
FROM pg_stat_activity
WHERE state IS DISTINCT FROM 'idle'
ORDER BY duration DESC NULLS LAST;

\echo '===== Step 6: 运行超过1小时的查询 ====='
SELECT pid, usename, datname, state, now() - query_start AS duration,
       left(query, 200) AS query_snippet
FROM pg_stat_activity
WHERE state = 'active'
  AND now() - query_start > interval '1 hour';

\echo '===== Step 6: idle in transaction 超过5分钟的会话 ====='
SELECT pid, usename, datname, now() - state_change AS idle_duration,
       left(query, 200) AS last_query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND now() - state_change > interval '5 minutes'
ORDER BY idle_duration DESC;

-- ============================================================
-- Step 4: 敏感数据列扫描
-- 注意：information_schema.columns 是"当前连接数据库"范围内的视图，
-- 若实例有多个数据库，需对每个数据库分别建立连接后重复执行本段查询。
-- 金仓的系统 schema（sys_catalog/sysaudit/sysmac/sys_hm/src_restrict/anon）必须排除。
-- ============================================================
\echo '===== Step 4: 敏感关键词列扫描（当前数据库）====='
SELECT table_schema, table_name, column_name, data_type,
       col_description(
         (quote_ident(table_schema) || '.' || quote_ident(table_name))::regclass::oid,
         ordinal_position
       ) AS column_comment
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'sys_catalog',
                           'sysaudit', 'sysmac', 'sys_hm', 'src_restrict', 'anon')
  AND column_name ~* '(password|pwd|secret|token|key|card|id_card|idcard|phone|mobile|ssn|credential)'
ORDER BY table_schema, table_name, column_name;
