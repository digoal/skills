# KingbaseES AWR 报告 — 字段级查询参考

本文件是 `SKILL.md` 的 L3 附属资源，收录每个章节需要用到的具体 SQL。Agent 在 Step 1/3 采集快照、Step 4 撰写报告时按需查阅。

> **KingbaseES 兼容性提示**：默认采用 PG 兼容模式（`server_version_num=120001` 对应 KES V9R1C10），所有 `pg_stat_*` 视图可用；Top SQL 取自 KingbaseES 特有的 `sys_stat_statements`（不是 `pg_stat_statements`）。

---

## 0. 客户端 SQL 执行（psql / ksql）

KingbaseES 自带 `ksql` 客户端（语法与 PostgreSQL `psql` 高度一致），所有 SQL 可在 `ksql` 中直接执行：

```bash
# 通过环境变量连接（推荐，密码不暴露在进程列表）
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGPASSWORD=xxx \
       PGDBNAME=kingbase
ksql -c "SELECT version();"

# 或显式传参（密码会在进程列表里短暂可见，慎用）
ksql -h 127.0.0.1 -p 5432 -U kingbase -d kingbase -W -c "SELECT 1"
```

如需在 `ksql`/`psql` 中手工执行本 skill 的两步快照采集，可以参考下文每节的 SQL 模板，前后两次执行同一组查询，将结果保存为 JSON 后再做差。

---

## 1. 实例基本信息

```sql
SELECT version() AS full_version,
       current_setting('server_version_num')::int AS ver_num,
       current_setting('server_version') AS ver_str,
       pg_is_in_recovery() AS is_standby,
       now() AS db_time,
       pg_postmaster_start_time() AS instance_start_time;
```

KingbaseES 输出示例：`KingbaseES V009R001C010`，`ver_num=120001`（PG 12 兼容）。

---

## 2. pg_stat_database（Load Profile 主要来源）

```sql
SELECT datname, numbackends, xact_commit, xact_rollback,
       blks_read, blks_hit,
       tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
       conflicts, temp_files, temp_bytes, deadlocks,
       blk_read_time, blk_write_time,
       stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL;
```

做差时用 `stats_reset` 校验两次快照之间是否被重置过；若变化则该库的增量不可信。

---

## 3. pg_stat_bgwriter（Checkpoint / Background Writer）

KingbaseES V9R1C10 基于 PG 12，无 `pg_stat_checkpointer` 拆分（该拆分是 PG 17 引入），checkpoint 相关字段仍位于 `pg_stat_bgwriter`：

```sql
SELECT checkpoints_timed, checkpoints_req, checkpoint_write_time, checkpoint_sync_time,
       buffers_checkpoint, buffers_clean, maxwritten_clean,
       buffers_backend, buffers_backend_fsync, buffers_alloc, stats_reset
FROM pg_stat_bgwriter;
```

---

## 4. sys_stat_statements（Top SQL，KingbaseES 特有）

> ⚠️ **不要**使用 `pg_stat_statements`，KingbaseES 用的是 `sys_stat_statements`。

```sql
SELECT queryid, LEFT(query, 200) AS query_sample,
       parses, total_parse_time, mean_parse_time,
       plans, total_plan_time, mean_plan_time,
       calls, total_exec_time, mean_exec_time, min_exec_time, max_exec_time,
       rows,
       shared_blks_hit, shared_blks_read, shared_blks_dirtied, shared_blks_written,
       temp_blks_read, temp_blks_written,
       blk_read_time, blk_write_time
FROM sys_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

**字段差异（vs PG 的 pg_stat_statements）**：

| 字段 | KingbaseES sys_stat_statements | PostgreSQL pg_stat_statements |
|---|---|---|
| 解析耗时 | ✅ `parses`/`total_parse_time`/`mean_parse_time` | ❌ 无 |
| 规划耗时 | ✅ `plans`/`total_plan_time`/`mean_plan_time` | ❌ 无 |
| WAL 生成 | ❌ 无 `wal_records`/`wal_bytes` | ✅ PG13+ 有 |
| 其他 | ✅ `calls`/`total_exec_time`/`shared_blks_*` 等同 PG | ✅ |

做增量时按 `queryid` 做差；同样按 `calls DESC` 和 `mean_exec_time DESC` 各取一份 Top 20，分别对应 Oracle AWR 的 "SQL ordered by Elapsed Time" / "SQL ordered by Executions" / "SQL ordered by Mean Time"。

**Parse-to-Exec 比**：`parses / calls`（KingbaseES 特有）。> 1.2 表示连接池未复用 prepared statement。

---

## 4b. sys_stat_statements_all（跨库全量视图，可选）

若需要看全实例（跨库）Top SQL，使用 KingbaseES 特有的 `sys_stat_statements_all`：

```sql
SELECT queryid, LEFT(query, 200) AS query_sample,
       calls, total_exec_time, mean_exec_time,
       shared_blks_hit, shared_blks_read
FROM sys_stat_statements_all
ORDER BY total_exec_time DESC
LIMIT 30;
```

注意：跨库视图不展示 `parses/plans` 等细粒度字段，仅供"全实例 Top N"用。

---

## 5. 等待事件采样（模拟 ASH）

在采样窗口内循环执行（间隔 1–2 秒）：

```sql
SELECT pid, state, wait_event_type, wait_event, query_start,
       now() - query_start AS duration
FROM pg_stat_activity
WHERE state != 'idle' AND pid != pg_backend_pid();
```

累积所有采样点后，按 `wait_event_type` / `wait_event` 计数，得到近似的等待事件分布直方图（采样频率越高、窗口越长，近似度越好，但要权衡对目标库的额外查询压力，建议间隔不小于 1 秒）。

---

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

---

## 7. 锁等待

```sql
SELECT l.pid, l.locktype, l.mode, l.granted,
       a.query, a.state, a.wait_event_type, a.wait_event,
       pg_blocking_pids(l.pid) AS blocked_by
FROM pg_locks l
JOIN pg_stat_activity a ON a.pid = l.pid
WHERE NOT l.granted;
```

`pg_blocking_pids()` 在 KingbaseES 上沿用 PG12 函数签名（参数 pid，返回 int[]），可用性需在 Step 0 探测。

---

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

极少数早期 KingbaseES 版本可能用 `pg_xlog_location_diff`/`pg_current_xlog_location`（PG 9.x 旧名），脚本中已做探测；若不可用则 WAL 速率章节降级。

---

## 9. WAL 生成速率

```sql
-- 主库
SELECT pg_current_wal_lsn();
-- 备库
SELECT pg_last_wal_replay_lsn();
```

两次快照的 LSN 做差：`pg_wal_lsn_diff(lsn_B, lsn_A)`，单位字节，除以 `Δt` 得到字节/秒。

---

## 10. 库/表大小增长

```sql
SELECT datname, pg_database_size(datname) AS size_bytes FROM pg_database;

SELECT schemaname, relname, pg_total_relation_size(relid) AS size_bytes
FROM pg_stat_user_tables
ORDER BY size_bytes DESC
LIMIT 20;
```

---

## 11. 关键 GUC 快照

```sql
SELECT name, setting, unit, source
FROM pg_settings
WHERE name IN (
  'shared_buffers','work_mem','maintenance_work_mem','effective_cache_size',
  'max_connections','track_io_timing','track_activities','autovacuum',
  'autovacuum_vacuum_scale_factor','autovacuum_max_workers',
  'wal_level','max_wal_size','min_wal_size','checkpoint_timeout',
  'checkpoint_completion_target','random_page_cost','shared_preload_libraries',
  -- KingbaseES 特有
  'syskwr_enable','sys_stat_statements_max'
);
```

`syskwr_enable` 控制 kingbase 内置 KWR 自动快照（off/manual/on）；`sys_stat_statements_max` 控制 `sys_stat_statements` 最大条目数（类比 PG 的 `pg_stat_statements.max`）。

---

## 12. 权限 / 扩展探测

```sql
SELECT rolname, rolsuper, rolreplication
FROM pg_roles WHERE rolname = current_user;

-- KingbaseES 默认无 pg_monitor 角色概念，靠 rolsuper/显式 GRANT 控制
SELECT 1;

SELECT extname, extversion FROM pg_extension
WHERE extname IN ('sys_stat_statements','sys_kwr','sys_hm','sys_spacequota','sys_squeeze')
ORDER BY 1;
```

---

## 13. sys_kwr（KingbaseES 内置 AWR，仅只读探测，不主动操作）

KingbaseES 自带 `sys_kwr` 自动快照仓库（与本 skill 的"两次快照做差"思路互补）。

> ⚠️ **只读探测**：可查询 `sys_stat_kwr_snapshot` 等视图，但**严禁**调用 `kwr_snap()`/`kwr_report()`/`kwr_delete()` 等过程，避免污染 kingbase 自带的 AWR 历史。

```sql
-- 探测 sys_kwr 是否启用
SHOW syskwr_enable;
SELECT extname, extversion FROM pg_extension WHERE extname = 'sys_kwr';

-- 列出最近的自动快照（仅当 syskwr_enable=on 时有内容）
SELECT snap_id, snap_time, snap_level
FROM sys_stat_kwr_snapshot
ORDER BY snap_id DESC
LIMIT 10;
```

若用户在 Step 0 探测到 `sys_kwr` 已启用，报告中可加一节"sys_kwr 历史快照交叉验证"，引用近 N 次自动快照的统计摘要做趋势对比（如 `xact_commit`/`blks_read` 等指标的自动快照序列）。**不要主动修改 kingbase 的 KWR 配置/触发新的快照**。

---

## 14. 连接参数解析模板（脚本兼容 PG 环境变量）

在 KingbaseES 上执行 `sys_stat_statements` 等查询时，连接参数解析逻辑（脚本中已实现）：

```python
# 优先级：
# 1. 命令行 --dsn / -H/-p/-d/-U/-W
# 2. PG 兼容环境变量 (PGHOST/PGPORT/PGDBNAME/PGUSER/PGPASSWORD)
# 3. KingbaseES 专属环境变量 (KINGBASE_HOST/KINGBASE_PORT/KINGBASE_DB/
#    KINGBASE_USER/KINGBASE_PASSWORD)
# 4. 内置默认 (127.0.0.1:5432, kingbase/kingbase/123456, 仅供本地测试)
```

**强烈建议**：在 KingbaseES 主机上设置 `~/.pgpass` 或 `~/.kingbasepass`，避免密码出现在环境变量/进程列表中。KingbaseES 同时识别 `~/.pgpass`（PG 兼容）与 `~/.kingbasepass`（KingbaseES 专属），后者优先级更高。