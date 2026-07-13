-- 00_list_databases.sql :: 列出实例中所有可连接的非模板数据库
SELECT datname FROM pg_database
WHERE datistemplate = false AND datallowconn = true
ORDER BY datname;
