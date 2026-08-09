-- kingbase-log-analyzer: 开启 csvlog 结构化日志（psql/ksql 版）
--
-- 用法：
--   PGPASSWORD=123456 psql -X -h 127.0.0.1 -p 5432 -U kingbase -d kingbase -f enable_csvlog.sql
--
-- 说明：
--   - 需要超级用户（或可 ALTER SYSTEM 的权限）执行。
--   - ALTER SYSTEM 会把配置写入 postgresql.auto.conf，pg_reload_conf() 即可生效，无需重启。
--   - csvlog 与 stderr 可并存（推荐先并存，确认 csvlog 文件正常后再考虑纯 csvlog）。
--   - 开启后日志目录会多出与 .log 同基名的 .csv 文件（如 kingbase-2026-08-09_090045.csv），
--     用 scripts/parse_csvlog.py 解析。
--   - 回滚：ALTER SYSTEM SET log_destination = 'stderr'; SELECT pg_reload_conf();

\pset pager off

\echo '===== 0. 开启前状态 ====='
SHOW log_destination;
SHOW logging_collector;
SHOW log_directory;
SHOW log_filename;

\echo '===== 1. 开启 csvlog（与 stderr 并存） ====='
-- 只想要 csvlog 可改为：ALTER SYSTEM SET log_destination = 'csvlog';
ALTER SYSTEM SET log_destination = 'stderr,csvlog';
ALTER SYSTEM SET logging_collector = on;

\echo '===== 2. reload 使配置生效（无需重启） ====='
SELECT pg_reload_conf();

\echo '===== 3. 验证 ====='
SHOW log_destination;
SHOW logging_collector;

\echo '===== 4. 回滚方法（如需恢复，执行以下两条） ====='
\echo "    ALTER SYSTEM SET log_destination = 'stderr';"
\echo "    SELECT pg_reload_conf();"
