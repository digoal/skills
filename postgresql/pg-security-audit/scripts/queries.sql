-- ============================================================
-- pg-security-audit：只读安全审计查询集
-- 使用方式：psql -h <host> -p <port> -U <user> -d <database> -f queries.sql
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

\echo '===== Step 2.1: pg_hba.conf 规则（需要superuser或pg_read_all_settings/pg_monitor）====='
SELECT line_number, type, database, user_name, address, netmask, auth_method, error
FROM pg_hba_file_rules
ORDER BY line_number;

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

\echo '===== Step 4: 非内网来源的活跃连接 ====='
SELECT pid, usename, datname, client_addr, application_name, backend_start
FROM pg_stat_activity
WHERE client_addr IS NOT NULL
  AND NOT (
    client_addr <<= '10.0.0.0/8'::inet OR
    client_addr <<= '172.16.0.0/12'::inet OR
    client_addr <<= '192.168.0.0/16'::inet OR
    client_addr <<= '127.0.0.0/8'::inet
  );

\echo '===== Step 4: 全部连接来源统计 ====='
SELECT client_addr, usename, datname, application_name, count(*) AS conn_count
FROM pg_stat_activity
WHERE client_addr IS NOT NULL
GROUP BY client_addr, usename, datname, application_name
ORDER BY conn_count DESC;

\echo '===== Step 5: 活跃会话概览 ====='
SELECT pid, usename, datname, state, wait_event_type, wait_event,
       now() - query_start AS duration, left(query, 200) AS query_snippet
FROM pg_stat_activity
WHERE state IS DISTINCT FROM 'idle'
ORDER BY duration DESC NULLS LAST;

\echo '===== Step 5: 运行超过1小时的查询 ====='
SELECT pid, usename, datname, state, now() - query_start AS duration,
       left(query, 200) AS query_snippet
FROM pg_stat_activity
WHERE state = 'active'
  AND now() - query_start > interval '1 hour';

\echo '===== Step 5: idle in transaction 超过5分钟的会话 ====='
SELECT pid, usename, datname, now() - state_change AS idle_duration,
       left(query, 200) AS last_query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND now() - state_change > interval '5 minutes'
ORDER BY idle_duration DESC;

-- ============================================================
-- Step 3: 敏感数据列扫描
-- 注意：information_schema.columns 是"当前连接数据库"范围内的视图，
-- 若实例有多个数据库，需对每个数据库分别建立连接后重复执行本段查询。
-- ============================================================
\echo '===== Step 3: 敏感关键词列扫描（当前数据库）====='
SELECT table_schema, table_name, column_name, data_type,
       col_description(
         (quote_ident(table_schema) || '.' || quote_ident(table_name))::regclass::oid,
         ordinal_position
       ) AS column_comment
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
  AND column_name ~* '(password|pwd|secret|token|key|card|id_card|idcard|phone|mobile|ssn|credential)'
ORDER BY table_schema, table_name, column_name;
