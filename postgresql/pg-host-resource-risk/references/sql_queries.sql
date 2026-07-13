-- pg-host-resource-risk 只读 SQL 参考集
-- 所有查询均只读。执行前建议先设置只读会话:
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;

-- =====================================================================
-- Step0 基础信息
-- =====================================================================

-- 实例版本 / 运行时长 / data_directory
SELECT version();
SELECT pg_postmaster_start_time() AS start_time,
       now() - pg_postmaster_start_time() AS uptime;
SHOW data_directory;

-- 内存相关参数
SHOW max_connections;
SHOW shared_buffers;
SHOW work_mem;
SHOW maintenance_work_mem;
SHOW effective_cache_size;

-- 数据库服务器 IP（用于 env_detect.sh 比对本地/远程）
SELECT inet_server_addr() AS db_server_ip, inet_server_port() AS db_server_port;

-- 所有活跃会话
SELECT pid, usename, application_name, client_addr, state,
       backend_start, xact_start, query_start, wait_event_type, wait_event, query
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST;

-- 自定义表空间路径
SELECT spcname, pg_tablespace_location(oid) AS location
FROM pg_tablespace
WHERE spcname NOT IN ('pg_default', 'pg_global');

-- =====================================================================
-- Step2 磁盘：大文件溯源 —— OID 反查库/表
-- =====================================================================

-- 通过库 OID（数据目录 base/<oid> 下的目录名）反查数据库名
SELECT oid, datname, pg_size_pretty(pg_database_size(oid)) AS size
FROM pg_database
ORDER BY pg_database_size(oid) DESC;

-- 通过表/索引的 relfilenode（文件名，通常等于 oid，除非发生过 VACUUM FULL/TRUNCATE）反查表名
-- 需要连接到具体的目标库后执行
SELECT c.relname, n.nspname, c.relkind,
       pg_relation_filenode(c.oid) AS filenode,
       pg_size_pretty(pg_relation_size(c.oid)) AS size
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE pg_relation_filenode(c.oid) = <文件名对应的数字>;

-- 复制槽是否导致 WAL 目录堆积（未消费的槽会阻止 WAL 回收）
SELECT slot_name, slot_type, active, restart_lsn,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots
ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC;

-- 归档是否失败导致 WAL 堆积
SELECT * FROM pg_stat_archiver;

-- 数据增长速率估算所需的当前插入量
SELECT schemaname, relname, n_tup_ins, n_tup_upd, n_tup_del,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY n_tup_ins DESC
LIMIT 20;

-- =====================================================================
-- Step3 OOM：高内存进程关联
-- =====================================================================

-- 用 OS 层拿到的 PID 反查该后端在做什么
SELECT pid, usename, application_name, client_addr, state,
       wait_event_type, wait_event, backend_start, xact_start, query_start, query
FROM pg_stat_activity
WHERE pid = <PID>;

-- 若 pg_stat_statements 可用：按 queryid 关联历史资源消耗（判断是否大排序/大哈希）
-- 需先从上面的 query 或 pg_stat_activity.queryid（PG14+）拿到 queryid
SELECT queryid, calls, total_exec_time, mean_exec_time,
       rows, shared_blks_hit, shared_blks_read,
       temp_blks_read, temp_blks_written,  -- 临时文件读写多，说明发生了磁盘排序/hash spill
       query
FROM pg_stat_statements
WHERE queryid = <queryid>;

-- autovacuum worker 在处理哪张表
SELECT pid, datname, relid::regclass AS table_name, phase,
       heap_blks_total, heap_blks_scanned, heap_blks_vacuumed,
       index_vacuum_count
FROM pg_stat_progress_vacuum;

-- WAL sender 复制延迟情况
SELECT pid, usename, client_addr, state, sync_state,
       write_lag, flush_lag, replay_lag,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes
FROM pg_stat_replication;

-- 高内存进程 application_name 分布（结合 OS 层拿到的 PID 列表在应用侧统计）
SELECT application_name, count(*), count(*) FILTER (WHERE state = 'active') AS active_cnt
FROM pg_stat_activity
GROUP BY application_name
ORDER BY count(*) DESC;

-- =====================================================================
-- Step4 IO：来源分析
-- =====================================================================

-- 后端直读 vs 检查点写盘比例
SELECT checkpoints_timed, checkpoints_req,
       buffers_checkpoint, buffers_clean, buffers_backend,
       buffers_backend_fsync, buffers_alloc
FROM pg_stat_bgwriter;
-- 若 checkpoints_req >> checkpoints_timed，说明 max_wal_size 可能偏小，检查点被迫频繁触发

-- TOP 10 磁盘读取最多的 SQL + 缓存命中率
SELECT queryid,
       round(100.0 * shared_blks_hit / NULLIF(shared_blks_hit + shared_blks_read, 0), 2) AS hit_ratio_pct,
       shared_blks_read, calls, total_exec_time, query
FROM pg_stat_statements
ORDER BY shared_blks_read DESC
LIMIT 10;

-- heap_blks_read 最高的表/索引（真实落盘读取多）
SELECT relid::regclass AS table_name, heap_blks_read, heap_blks_hit,
       round(100.0 * heap_blks_hit / NULLIF(heap_blks_hit + heap_blks_read, 0), 2) AS hit_ratio_pct
FROM pg_statio_user_tables
ORDER BY heap_blks_read DESC
LIMIT 10;

SELECT relid::regclass AS table_name, indexrelid::regclass AS index_name,
       idx_blks_read, idx_blks_hit
FROM pg_statio_user_indexes
ORDER BY idx_blks_read DESC
LIMIT 10;

-- =====================================================================
-- Step5 网络：复制流量 / 大结果集 / 连接风暴
-- =====================================================================

-- WAL 生成速率：执行两次，间隔若干秒，用差值 / 时间算速率
SELECT pg_current_wal_lsn(), now();
-- ... 等待 N 秒后再执行一次，然后用 pg_wal_lsn_diff() 计算差值

-- 大结果集嫌疑查询（rows 极大）
SELECT queryid, calls, rows, rows / NULLIF(calls, 0) AS avg_rows_per_call, query
FROM pg_stat_statements
ORDER BY rows DESC
LIMIT 10;

-- 当前活跃且可能返回大量数据的会话
SELECT pid, usename, client_addr, state, query_start, query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;

-- 连接数总览及是否异常激增（结合多次采样对比）
SELECT count(*) AS total_conn,
       count(*) FILTER (WHERE state = 'active') AS active_conn,
       count(*) FILTER (WHERE state = 'idle') AS idle_conn,
       count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_txn_conn
FROM pg_stat_activity;
