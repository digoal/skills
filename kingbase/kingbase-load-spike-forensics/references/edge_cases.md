# 边界情况补充说明（KingbaseES 适配）

本文档补充 SKILL.md 中未展开的 KingbaseES 特有细节，供 Agent 在遇到对应场景时按需查阅。

> **PG 兼容视角**：KingbaseES 默认采用 PG 兼容模式，PG 12 的所有 `pg_stat_*` / `pg_locks` / `pg_settings` 视图在金仓里**列名、列序、语义均一致**，可以直接用 PG 12 的脚本工具排查。差异主要在以下方面。

## 1. KingbaseES 默认行为里与 PG 不同的地方

| 维度 | PostgreSQL 默认 | KingbaseES 默认 | 影响 |
|------|------------------|------------------|------|
| `log_min_duration_statement` | -1（不记慢 SQL） | -1（金仓同样保守） | 默认都不记慢 SQL；金仓同样需要在 `postgresql.conf` 中显式设置才能在日志里看到慢查询 |
| `logging_collector` | off | on | 金仓默认开 collector，日志一定写文件，路径在 `data_directory` 下的 `sys_log/` |
| `log_filename` | `postgresql-%Y-%m-%d_%H%M%S.log` | `kingbase-%Y-%m-%d_%H%M%S.log` | 日志命名带 `kingbase-` 前缀 |
| `log_directory` | `log` | `sys_log` | 子目录名带 `sys_` 前缀 |
| `shared_preload_libraries` | 取决于发行版 | 默认含 `sys_stat_statements` | 金仓默认开启 SQL 统计 |
| 角色 `pg_monitor` | 存在 | 同义映射为 `sys_monitor`（PG 兼容） | 二者都能识别 |
| 默认 admin db | `postgres` | `kingbase`（金仓不创建 `postgres`） | 列库脚本不要硬编码 `postgres` |

取证脚本里第一次执行前请 `SHOW log_min_duration_statement;` —— 如果是 -1，立刻写入报告"证据缺口"并在"规避建议"里要求打开。

## 2. sys_stat_statements 的 schema 与 pg_stat_statements 关系

KingbaseES 安装 `sys_stat_statements` 扩展后：

- 视图物理位置：`public.sys_stat_statements`
- PG 兼容别名：`pg_stat_statements`（同一查询同时有 `pg_stat_statements` 和 `public.sys_stat_statements` 两个名称指向同一视图）
- 列名 / 列序与 `pg_stat_statements`（v1.11 / PG 13 风格）一致

`pg_stat_statements` 在该实例上**没有单独的视图定义**（仅 `public.sys_stat_statements`），用 `SELECT * FROM pg_stat_statements` 时 KingbaseES 客户端会做隐式映射。

## 3. sys_catalog.sys_stat_* 与 public.sys_stat_statements 的角色分工

| 视图 | 定位 | 谁用 |
|------|------|------|
| `public.sys_stat_statements` (≡ `pg_stat_statements`) | PG 兼容、单条 SQL 的 parse/plan/exec 时间、IO 计数 | 兼容脚本/工具 |
| `sys_catalog.sys_stat_sql` | **金仓独有**：SQL × 全维度画像（db_time/db_cpu/db_wait 分开，top-2 wait_event 已排名，parse/plan/exec 拆分，IO 大小，WAL size，buffer hit 率） | 取证主表，**优先用这张** |
| `sys_catalog.sys_stat_sqltime` / `sys_stat_sqlio` / `sys_stat_sqlwait` / `sys_stat_sqlcount` | 单维度的细分（与 sys_stat_sql 拆分粒度对齐） | 按需取用，比如只关心等待事件就只查 sys_stat_sqlwait |
| `sys_catalog.sys_stat_wait` | 全实例等待事件分布（等价 Oracle V$SYSTEM_WAIT） | 排查"等待事件集中度" |
| `sys_catalog.sys_stat_waitaccum` | SQL × 等待事件累计矩阵 | 与 sys_stat_sqlwait 类似，差异在累计方式 |
| `sys_catalog.sys_stat_wal_buffer` | 实时 WAL buffer 写盘速率 / utilization | 排查 WAL 堆积 |
| `sys_catalog.sys_stat_dbtime` / `sys_stat_dmlcount` | DB-Time 总量 / DML 分类计数 | 高频小事务 vs. 大事务判断 |
| `sys_catalog.sys_stat_instevent` / `sys_stat_instlock` / `sys_stat_instio` | 实例级事件/锁/IO 聚合 | 跨库聚合分析 |
| `sys_catalog.sys_stat_msgaccum` / `sys_stat_metric_history` / `sys_stat_sysmetric_history` | 消息累积、AWR 历史 | 关键证据 |

**取证最佳实践**：先查 `sys_stat_sql`（Top 20）+ `sys_stat_wait`（Top 20）+ `sys_stat_wal_buffer` + `sys_stat_sysmetric_history`（窗口内时序），其他视图按需展开。

## 4. AWR 仓库（sys_stat_metric_history / sys_stat_sysmetric_history）的使用

依赖 `sys_kwr` 扩展（`CREATE EXTENSION sys_kwr;`），它会自动按 interval（默认 60 分钟）把累计型视图的数据写入以下两张历史表：

- `sys_catalog.sys_stat_metric_history` —— 细粒度（如 buffer hit / wait count 等）
- `sys_catalog.sys_stat_sysmetric_history` —— 粗粒度（QPS / TPS / CPU%）

通过以下检查可判断仓库是否可用：

```sql
SELECT count(*) FROM sys_catalog.sys_stat_sysmetric_history;
-- 若返回 0，说明 sys_kwr 未开启或 interval 尚未触发
```

如果仓库为空但仍然想回溯历史，**只能**走：
1. 日志（前提：`log_min_duration_statement` 已开启、auto_explain 已开启）；
2. 两次 `sys_stat_statements` / `sys_stat_sql` 快照做差（事后已无法补做）；
3. 外部监控（Prometheus / 云监控）。

**KB 官方行为**：金仓把 AWR 仓库设计为"快照+差分"两段式，这与 Oracle AWR 高度类似，可与 `KSH`（Kingbase Snapshot Helper，等价 Oracle MMON）协同工作。

### 4.1 `sys_stat_sql` / `sys_stat_wait` / `sys_stat_sqlwait` 等 KB-extra 视图的启用条件

实测发现：以上视图在某些默认安装的 KingbaseES 实例上**始终返回 0 行**，但 `sys_stat_statements` 同时有数据。原因在于 KingbaseES 引入了一组**额外的 track_* GUC** 控制 KB-extra 视图的采集开关：

| GUC | 控制范围 | 默认 | 取证时建议 |
|-----|----------|------|------------|
| `track_sql` | `sys_stat_sql` / `sys_stat_sqltime` / `sys_stat_sqlio` / `sys_stat_sqlwait` / `sys_stat_sqlcount` / `sys_stat_dbtime` / `sys_stat_dmlcount` | off | 改为 on |
| `track_instance` | `sys_stat_instevent` / `sys_stat_instlock` / `sys_stat_instio` / `sys_stat_msgaccum` | off | 改为 on |
| `track_real_stats` | `sys_stat_metric` / `sys_stat_metric_history`（实时部分） | off | 改为 on |
| `track_wait_timing` | 等待事件细分计时（已在 sys_stat_sql 中用到） | on | 保持 |
| `track_io_timing` | `pg_stat_statements.blk_read_time` / `blk_write_time` | off | 改为 on（PG 默认项，KB 同样适用） |
| `sys_kwr` 扩展 | `sys_stat_sysmetric` / `sys_stat_sysmetric_history` / `sys_stat_sysmetric_summary` 自动落库 | 未安装 | `CREATE EXTENSION sys_kwr;` |

**取证前的必查项**（Step 0）：

```sql
SELECT name, setting FROM pg_settings
WHERE name IN ('track_sql','track_instance','track_real_stats','track_wait_timing',
               'track_io_timing','track_activities','track_counts','log_min_duration_statement');
```

如果 `track_sql = off` 而 `sys_stat_sql` 始终为空，**不是脚本问题**，是金仓 SQL 级采集开关未打开。取证时把此项列入"证据缺口"并写入"规避建议"：

```ini
# postgresql.conf 修改后 ALTER SYSTEM SET 或 reload
track_sql = on
track_instance = on
track_io_timing = on
log_min_duration_statement = 500ms
shared_preload_libraries = 'sys_stat_statements,sys_kwr,sys_ksh'
```

⚠️ 上述 GUC 修改后**历史数据不会回填**，只能从修改时起开始采集；排查窗口已过去的事实不可补，只能事后增强可观测性。

## 5. KshMain / LogicalLauncherMain 等金仓独有后台进程

`pg_stat_activity` 中的 background worker 列表里，金仓比 PG 多两类：

| 后台进程 | 来源 | 异常影响 |
|----------|------|----------|
| `KshMain` | 金仓独有（等价 Oracle MMON） | 负责把动态性能视图落 AWR 仓库；异常会导致历史证据缺口 |
| `LogicalLauncherMain` | PG 13+ 引入但 KB 实现 | 负责逻辑复制 launcher；异常会导致逻辑复制堆积，间接引发主库 WAL 增长 |
| `WalWriter` / `BgWriter` / `Checkpointer` / `AutoVacuum` / `StatsCollector` | PG 兼容 | 与 PG 行为一致 |

排查窗口内是否所有 background worker 都健康：

```sql
SELECT pid, application_name, backend_type, wait_event_type, wait_event, state
FROM pg_stat_activity
WHERE backend_type IS NOT NULL OR application_name LIKE '%kingbase%'
ORDER BY backend_type NULLS LAST;
```

## 6. regdatabase 伪类型在 KingbaseES 中的支持

PG 13+ 有 `regdatabase` 伪类型（与 `regclass`、`regrole` 并列），可对 `pg_database.oid` 直接做 `::regdatabase` 转换得到 dbname。

实测：在本实例上 `::regdatabase` 报 `type "regdatabase" does not exist`。原因可能是金仓版本（V009R001C010）基于 PG 12 内核，未引入 `regdatabase`。

**应对**：`sys_stat_sql.datid` 列是 `oid`，要查库名时用 `datid::text` 或 `pg_catalog.pg_database.datname`，不要用 `::regdatabase`。

## 7. KingbaseES 默认连接限制与连接风暴

| 参数 | 默认 | 取证脚本注意事项 |
|------|------|------------------|
| `max_connections` | 100（KB 默认） | 比 PG 默认 100 相同，但很多生产 KB 实例调到 200~500，过高的 max_connections 是性能灾难 |
| `superuser_reserved_connections` | 3 | 取证脚本用 superuser 时仍要至少留 3 给管理员紧急登录 |
| `reserved_connections` | 0（PG 13+ 才引入） | KB 是否生效需 `SHOW reserved_connections` |

连接堆积场景建议同时查：

```sql
SELECT
  state, count(*),
  max(now() - state_change)  AS max_state_age,
  max(now() - query_start)   AS max_query_age
FROM pg_stat_activity
GROUP BY state;
```

## 8. sysaudit / sysmac / sys_hm 对主路径的性能影响

金仓默认安装以下三个安全/可观测性扩展，开启后会带来以下开销：

- **`sysaudit`** —— 审计日志：默认开启后每条 DDL/DML 都会写审计日志，量大时可能成为 IO 瓶颈。建议在排查前先 `SHOW sysaudit.log;` 确认是否开启，必要时临时关闭（生产环境需要审计管理员授权）。
- **`sysmac`** —— 强制访问控制：金仓的 MAC 策略可能在表/行级别增加额外的策略匹配开销。开启后部分表的查询会被策略引擎串行化。
- **`sys_hm`** —— 健康监控：默认开启，会定期检查实例健康状态，本身开销很小，但可能产生误报警告淹没真正的告警。

取证过程中如果发现性能瓶颈但 `pg_stat_*` 全部正常，请优先怀疑这三个扩展是否在主路径上做了不必要的写入/匹配。

## 9. KingbaseES 默认搜路径与 sys_catalog 的引用

默认 `psql` 的 `search_path = "$user", public`，**不含 `sys_catalog`**。本 skill 所有 `sys_catalog.sys_stat_*` 视图都使用 schema 限定调用，可不受 search_path 影响。

如果需要把 `sys_catalog` 加入 search_path 方便调用：

```sql
SET search_path TO sys_catalog, public;
-- 或 ALTER ROLE kingbase SET search_path TO sys_catalog, public;（需 superuser）
```

注意：把 `sys_catalog` 加到 search_path 后，KSQL/PG 的同名视图（如 `sys_stat_statements`）会出现二义性，需要明确 `public.sys_stat_statements`。

## 10. WAL 目录命名差异

PG 中 WAL 默认目录是 `${data_directory}/pg_wal`，但金仓某些版本/打包方式下可能是 `${data_directory}/wal` 或 `${data_directory}/xlog`。取证脚本里应同时尝试这两个命名：

```bash
ls -d ${DATA_DIR}/pg_wal ${DATA_DIR}/wal ${DATA_DIR}/xlog 2>/dev/null
```

WAL 增长异常（窗口内增大数 GB）是写放大或复制槽堆积的强信号。