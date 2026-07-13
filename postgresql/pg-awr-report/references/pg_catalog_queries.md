# PostgreSQL AWR 报告 — 字段级查询参考

本文件是 `SKILL.md` 的 L3 附属资源，收录每个章节需要用到的具体 SQL。Agent 在 Step 1/3 采集快照、Step 4 撰写报告时按需查阅。

## 1. 实例基本信息

```sql
SELECT version() AS full_version,
       current_setting('server_version_num')::int AS ver_num,
       pg_is_in_recovery() AS is_standby,
       now() AS db_time,
       pg_postmaster_start_time() AS instance_start_time;
```

## 2. pg_stat_database（Load Profile 主要来源）

```sql
SELECT datname, numbackends, xact_commit, xact_rollback,
       blks_read, blks_hit,
       tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
       conflicts, temp_files, temp_bytes, deadlocks,
       blk_read_time, blk_write_time,   -- 依赖 track_io_timing=on
       stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL;
```

做差时用 `stats_reset` 校验两次快照之间是否被重置过；若变化则该库的增量不可信。

## 3. pg_stat_bgwriter / pg_stat_checkpointer（PG17 拆分）

PG16 及以前：

```sql
SELECT checkpoints_timed, checkpoints_req, checkpoint_write_time, checkpoint_sync_time,
       buffers_checkpoint, buffers_clean, maxwritten_clean,
       buffers_backend, buffers_backend_fsync, buffers_alloc, stats_reset
FROM pg_stat_bgwriter;
```

PG17+（checkpoint 相关字段迁移到新视图）：

```sql
SELECT num_timed AS checkpoints_timed, num_requested AS checkpoints_req,
       write_time AS checkpoint_write_time, sync_time AS checkpoint_sync_time,
       buffers_written AS buffers_checkpoint, stats_reset
FROM pg_stat_checkpointer;

SELECT buffers_clean, maxwritten_clean, buffers_alloc, stats_reset
FROM pg_stat_bgwriter;
```

Agent 需先用 `ver_num` 判断走哪一套查询。

## 4. pg_stat_statements（Top SQL）

```sql
SELECT queryid, LEFT(query, 200) AS query_sample,
       calls, total_exec_time, mean_exec_time, min_exec_time, max_exec_time,
       rows, shared_blks_hit, shared_blks_read, shared_blks_dirtied, shared_blks_written,
       temp_blks_read, temp_blks_written,
       wal_records, wal_bytes
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

同样按 `calls DESC` 和 `mean_exec_time DESC` 各取一份 Top 20，分别对应 Oracle AWR 的 "SQL ordered by Elapsed Time" / "SQL ordered by Executions" / "SQL ordered by Mean Time"。

做增量时，两次快照的 `(queryid, calls, total_exec_time, ...)` 按 `queryid` 做差；注意如果实例在两次快照间发生过 `pg_stat_statements` 的 `pg_stat_statements_reset()` 或触发了 entry 淘汰（`pg_stat_statements.max` 满），个别 queryid 可能消失，属正常现象需在报告中说明。

## 5. 等待事件采样（模拟 ASH）

在采样窗口内循环执行（间隔 1–2 秒）：

```sql
SELECT pid, state, wait_event_type, wait_event, query_start, now() - query_start AS duration
FROM pg_stat_activity
WHERE state != 'idle' AND pid != pg_backend_pid();
```

累积所有采样点后，按 `wait_event_type` / `wait_event` 计数，得到近似的等待事件分布直方图（采样频率越高、窗口越长，近似度越好，但要权衡对目标库的额外查询压力，建议间隔不小于 1 秒）。

## 6. 表 / 索引统计（膨胀、autovacuum、IO）

```sql
SELECT schemaname, relname,
       n_tup_ins, n_tup_upd, n_tup_del, n_live_tup, n_dead_tup,
       last_vacuum, last_autovacuum, last_analyze, last_autoanalyze,
       vacuum_count, autovacuum_count, analyze_count, autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;

SELECT schemaname, relname,
       heap_blks_read, heap_blks_hit,
       idx_blks_read, idx_blks_hit,
       toast_blks_read, toast_blks_hit
FROM pg_statio_user_tables
ORDER BY heap_blks_read DESC
LIMIT 20;
```

行数估算（禁止用 `count(*)`）：

```sql
SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 20;
-- 或
SELECT relname, reltuples::bigint FROM pg_class WHERE relkind = 'r' ORDER BY reltuples DESC LIMIT 20;
```

## 7. 锁等待

```sql
SELECT l.pid, l.locktype, l.mode, l.granted,
       a.query, a.state, a.wait_event_type, a.wait_event,
       pg_blocking_pids(l.pid) AS blocked_by
FROM pg_locks l
JOIN pg_stat_activity a ON a.pid = l.pid
WHERE NOT l.granted;
```

## 8. 复制延迟（主库视角）

```sql
SELECT application_name, client_addr, state,
       pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) AS sent_lag_bytes,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes,
       write_lag, flush_lag, replay_lag
FROM pg_stat_replication;
```

备库视角（判断自身回放延迟）：

```sql
SELECT now() - pg_last_xact_replay_timestamp() AS replay_delay;
```

## 9. WAL 生成速率

```sql
-- 主库
SELECT pg_current_wal_lsn();
-- 备库
SELECT pg_last_wal_replay_lsn();
```

两次快照的 LSN 做差：`pg_wal_lsn_diff(lsn_B, lsn_A)`，单位字节，除以 `Δt` 得到字节/秒。

## 10. 库/表大小增长

```sql
SELECT datname, pg_database_size(datname) AS size_bytes FROM pg_database;

SELECT schemaname, relname, pg_total_relation_size(relid) AS size_bytes
FROM pg_stat_user_tables
ORDER BY size_bytes DESC
LIMIT 20;
```

## 11. 关键 GUC 快照

```sql
SELECT name, setting, unit, source
FROM pg_settings
WHERE name IN (
  'shared_buffers','work_mem','maintenance_work_mem','effective_cache_size',
  'max_connections','track_io_timing','track_activities','autovacuum',
  'autovacuum_vacuum_scale_factor','autovacuum_max_workers',
  'wal_level','max_wal_size','min_wal_size','checkpoint_timeout',
  'checkpoint_completion_target','random_page_cost','shared_preload_libraries'
);
```

## 12. 权限 / 扩展探测

```sql
SELECT rolname, rolsuper, rolreplication
FROM pg_roles WHERE rolname = current_user;

SELECT pg_has_role(current_user, 'pg_monitor', 'member') AS has_pg_monitor;

SELECT extname, extversion FROM pg_extension ORDER BY 1;
```
