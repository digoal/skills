-- 00_list_databases.sql :: 列出实例中所有可连接的非模板数据库
-- KingbaseES 默认采用 PG 兼容模式，pg_database 系统表与 PostgreSQL 完全一致
SELECT datname FROM pg_database
WHERE datistemplate = false AND datallowconn = true
ORDER BY datname;
