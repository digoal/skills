-- kingbase-log-analyzer: 只读采集日志相关配置（psql/ksql 版）
--
-- 用法：
--   方式一（环境变量，缺省 127.0.0.1:5432/kingbase/kingbase/123456）：
--     psql -X -U kingbase -d kingbase -f collect_log_settings.sql
--   方式二（显式连接参数）：
--     PGPASSWORD=123456 psql -X -h 127.0.0.1 -p 5432 -U kingbase -d kingbase -f collect_log_settings.sql
--
-- 说明：
--   - KingbaseES 默认采用 PG 兼容模式，连接参数沿用 PG 风格环境变量
--     （PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE；金仓手册可能写作 KINGBASE*，本 skill 一律用 PG 风格）。
--   - 全部为只读 SHOW/SELECT，不做任何写操作、不修改任何配置。
--   - 输出用于日志分析时的"格式/时区/内容开关"假设，帮助判断哪些日志维度数据可得。

\pset pager off

\echo '===== 1. 版本与环境 ====='
SELECT version();
SHOW server_version;
SHOW timezone;
SHOW log_timezone;

\echo '===== 2. 日志输出格式与目录 ====='
SHOW log_destination;
SHOW logging_collector;
SHOW log_directory;      -- 默认 sys_log（相对 data_directory）
SHOW log_filename;       -- 默认 kingbase-%Y-%m-%d_%H%M%S.log
SHOW log_file_mode;
SHOW log_truncate_on_rotation;
SHOW log_rotation_age;   -- 分钟
SHOW log_rotation_size;  -- kB
SHOW log_line_prefix;    -- 默认 %m [%p]

\echo '===== 3. 日志内容开关（决定哪些维度数据可得） ====='
SHOW log_min_duration_statement;     -- -1 表示不记慢 SQL（金仓默认）
SHOW log_statement;
SHOW log_checkpoints;                -- 金仓默认 off
SHOW log_connections;
SHOW log_disconnections;
SHOW log_lock_waits;
SHOW log_temp_files;
SHOW log_autovacuum_min_duration;    -- -1 表示不记 autovacuum（金仓默认）
SHOW log_min_messages;
SHOW log_error_verbosity;

\echo '===== 4. 金仓特有：审计/安全/健康监控 相关开关 ====='
SELECT name, setting FROM pg_settings
 WHERE name IN ('sysaudit.log','sysmac.log','sys_hm', 'track_sql','track_instance','track_real_stats');

\echo '===== 5. 与日志分析相关的其他关键参数 ====='
SHOW data_directory;
SHOW archive_mode;
SHOW archive_command;
SHOW max_connections;
SHOW shared_buffers;
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW work_mem;
SHOW max_prepared_transactions;      -- 金仓默认 0（2PC 未开启）

\echo '===== 采集完成：请结合日志目录与上述参数判断数据可得性 ====='
