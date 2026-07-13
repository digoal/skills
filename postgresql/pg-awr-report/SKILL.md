---
name: pg-awr-report
description: "给定 PostgreSQL 数据库连接串（host/port/dbname/user/password 或 postgresql:// URI），以资深 PostgreSQL DBA 专家视角连接数据库，采集两个时间点的系统计数器视图并做差，生成类似 Oracle AWR 报告的 PostgreSQL 性能诊断报告（Load Profile、Top SQL、等待事件、实例效率、Checkpoint/BGWriter、锁等待、复制延迟、表膨胀、配置快照、Findings & Recommendations）。触发条件：用户提到「生成AWR报告」「PostgreSQL性能报告」「数据库健康检查」「给你连接串帮我看看这个库」「Top SQL分析」「等待事件分析」「pg_stat_statements 分析」「数据库负载画像」「类似Oracle AWR」「性能诊断报告」「帮我诊断一下这个PG实例」，或者用户直接提供了数据库连接串/密码并希望做性能分析、健康检查、慢SQL排查。即使用户只说「帮我看看这个库最近咋样」但同时给了连接信息，也应使用本 skill。"
tags: [PostgreSQL, AWR, 健康报告]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# PostgreSQL AWR 风格性能报告生成器

以资深 PostgreSQL DBA 专家的方法论，把 Oracle AWR「两次快照做差得到速率」的核心思路移植到 PostgreSQL：PostgreSQL 的 `pg_stat_*` 视图本质上都是自实例启动或上次 `pg_stat_reset()` 以来的**累计计数器**，因此只要在时间点 A 和时间点 B 各采一次快照，做差再除以采样时长，就能得到和 AWR 报告一样的"负载画像"（Load Profile）与 Top SQL、等待事件、效率指标。

## 前置要求

- 运行环境需要能直连目标数据库的 `host:port`。
  - **重要**：如果当前在 Claude 官方网页版/移动端沙箱中执行，出站网络受白名单限制，通常无法直连用户自己的数据库地址。此时应如实告知用户，并改为：(a) 输出本 skill 附带的 `scripts/pg_awr_collector.py` 采集脚本，请用户在能访问数据库的机器（本地终端、跳板机、Claude Code 本地环境）上运行，把生成的两份 JSON 快照回传；或 (b) 在具备网络出口权限的 Claude Code / 类似环境中直接执行本 skill 全流程。
- 客户端依赖：`python3 -m pip install psycopg2-binary --break-system-packages`（或系统自带 `psql`）。
- 建议的数据库账号权限：具备 `pg_monitor` 角色，或至少对 `pg_stat_database`、`pg_stat_bgwriter`、`pg_stat_activity`、`pg_stat_statements`、`pg_stat_replication`、`pg_locks`、`pg_stat_user_tables`、`pg_statio_user_tables`、`pg_settings` 有 SELECT 权限。非 superuser 也能运行，功能会按下方"降级矩阵"自动收缩范围。

## 安全底线（不可协商）

1. **绝不明文回显或落盘密码**：连接串中的密码只用于建立连接，不写入报告、不写入日志、不出现在生成的任何 Markdown/JSON 文件里；展示连接串时一律脱敏为 `postgresql://user:***@host:port/db`。
2. **只读操作为主**：不执行任何 DDL/DML，不修改用户业务数据。
3. 如需临时开启 `track_io_timing`（用于获得 IO 耗时数据）等参数，必须先向用户说明这是全局/会话级改动、采集完成后是否需要还原，取得确认后再执行。
4. 不对陌生/未授权的数据库地址发起连接；连接目标必须是用户本人提供的。
5. 大表禁止使用 `SELECT count(*)` 做体检（会做全表扫描甚至长时间持锁），行数估算一律使用 `pg_stat_user_tables.n_live_tup` 或 `pg_class.reltuples`。

## 工作流程

### Step 0：解析连接信息 & 环境探测

解析连接串后，第一步先跑：

```sql
SELECT version(), current_setting('server_version_num')::int AS ver_num,
       pg_is_in_recovery() AS is_standby, now() AS db_time,
       pg_postmaster_start_time() AS start_time;

SELECT rolname, rolsuper FROM pg_roles WHERE rolname = current_user;

SELECT extname, extversion FROM pg_extension ORDER BY 1;

SELECT name, setting, unit FROM pg_settings
WHERE name IN ('shared_buffers','work_mem','maintenance_work_mem','effective_cache_size',
  'max_connections','track_io_timing','track_activities','autovacuum','wal_level',
  'max_wal_size','checkpoint_timeout','random_page_cost','shared_preload_libraries');
```

记录：版本号、是否备库、实例启动时间（决定 `pg_stat_bgwriter`/`pg_stat_database` 的计数器是"自启动以来"还是"自上次 reset 以来"，两次快照的差值才有意义，因此**不要**在两次快照之间执行 `pg_stat_reset()`）。

**降级矩阵**（探测后据此裁剪报告章节，并在报告开头列出"本次报告能力边界"）：

| 条件缺失 | 影响 | 处理方式 |
|---|---|---|
| 无 `pg_stat_statements` 扩展 | 无法生成 Top SQL 章节 | 跳过该章节，报告中给出安装命令：`shared_preload_libraries='pg_stat_statements'` 后重启 + `CREATE EXTENSION` |
| `track_io_timing = off` | Top SQL / IO 耗时字段全为 0 | 提示可临时 `SET track_io_timing = on;`（会话级，仅对本连接后续查询生效，不影响其他会话），采集完成后说明该设置不持久 |
| 非 superuser / 无 `pg_monitor` | `pg_stat_activity.query` 对他人会话可能被打码（PG13-），部分统计视角受限 | 报告中标注"以当前账号可见范围为准"，不假装看到了全局真相 |
| 云托管 RDS（阿里云/AWS RDS 等） | 通常没有真正的 superuser，`pg_stat_reset()`/部分系统函数被禁用 | 完全依赖增量做差法，不依赖 reset 权限；如厂商有专属性能洞察产品，可作为交叉验证提及 |
| 无从库 / 非主库角色 | 无复制延迟章节 | 跳过 |

### Step 1：采集 Snapshot A（begin）

一次性采集以下视图并连同采集时间戳整体落成一份内存/JSON 结构（字段清单见 `references/pg_catalog_queries.md`）：

- `pg_stat_database`（目标库 + 全库汇总）
- `pg_stat_bgwriter`（PG17+ 部分字段拆分进 `pg_stat_checkpointer`，需按版本判断）
- `pg_stat_statements`（若可用，Top by `total_exec_time`/`calls`/`mean_exec_time`）
- `pg_stat_user_tables` / `pg_statio_user_tables`（增删改行数、死元组、autovacuum 次数与时间、buffer 命中）
- `pg_stat_replication` / `pg_stat_wal_receiver`（若有从库/为从库）
- `pg_current_wal_lsn()`（主库）或 `pg_last_wal_replay_lsn()`（备库），用于算 WAL 生成速率
- `pg_database_size(datname)`：各库大小，用于算增长

### Step 2：等待间隔

默认间隔 **15–30 分钟**（可配置，最短建议 5 分钟）。明确告知用户："采集窗口内请让真实业务负载正常运行，窗口太短或空载会让 Top SQL / Load Profile 失真"。

在等待期间，如果需要模拟 Oracle 的 ASH（Active Session History），可用轮询方式每 1–2 秒采一次 `pg_stat_activity` 的 `wait_event_type`/`wait_event`/`state`，持续整个窗口，事后做等待事件分布统计（PostgreSQL 没有内建 ASH，这是唯一能拿到"当下正在等什么"的办法；`scripts/pg_awr_collector.py` 内置了这个采样循环）。

### Step 3：采集 Snapshot B（end），计算 Delta

对计数器类字段做差（B − A）；对状态类字段（当前连接数、当前锁等待、当前复制延迟）直接取 B 时刻的值。核心公式：

- 采样时长 `Δt`（秒）= B.采集时间 − A.采集时间
- TPS = `(xact_commit + xact_rollback 的增量) / Δt`
- QPS（近似）= `sum(pg_stat_statements.calls 的增量) / Δt`（仅当扩展可用）
- Buffer Cache Hit % = `1 - (blks_read 增量) / (blks_read 增量 + blks_hit 增量)`（越接近 100% 越好，长期 < 99% 需要关注 `shared_buffers`/索引设计）
- WAL 生成速率 = `pg_wal_lsn_diff(lsn_B, lsn_A) / Δt`（字节/秒）
- 单表增删改速率、死元组增长速率、autovacuum 触发次数增量，用于判断膨胀/vacuum 是否跟得上写入

若 Snapshot B 采集失败（连接中断等），报告需要降级为"仅基于 Snapshot A 的静态健康检查"，并在报告顶部明确标注，不得假装有完整的 Load Profile。

### Step 4：按 Oracle AWR 章节结构生成报告

| Oracle AWR 章节 | PostgreSQL 对应实现 |
|---|---|
| Report Summary | 版本/是否备库/采集窗口/降级矩阵结果 |
| Load Profile | 上面 Step 3 的速率指标表（TPS/QPS/WAL生成/回滚率/临时文件） |
| Instance Efficiency Percentages | Buffer Hit%、Index Hit%、Soft Parse 近似（PG无硬解析概念，可略） |
| Top SQL | `pg_stat_statements` 按 `total_exec_time`/`calls`/`mean_exec_time`/`shared_blks_read` 分别 Top 10 |
| Wait Event / Wait Class | 采样期内 `wait_event_type` 分布直方图 + Top `wait_event` |
| Checkpoint & Background Writer | `checkpoints_timed/req` 增量、`buffers_checkpoint/clean/backend` 增量，判断是否 checkpoint 过于频繁（间隔小于 `checkpoint_timeout` 触发的 `_req` 占比过高） |
| 锁等待 Top | Snapshot B 时刻 `pg_locks` 中 `granted=false` 的记录 + 阻塞链（`pg_blocking_pids()`） |
| 复制延迟 | `pg_stat_replication.replay_lag` 等（若适用） |
| 表膨胀 & Autovacuum | 死元组占比 Top、autovacuum 次数与耗时增量 |
| Segments Growth | 各库/Top 表大小增长 Top 10 |
| 配置快照 | Step 0 采集的关键 GUC |
| Findings & Recommendations | 见下方阈值规则 |

**给建议时使用的经验阈值**（仅作为提示线索，不是绝对红线，需结合业务上下文）：

- Buffer Hit % 持续 < 99%：关注 `shared_buffers`、索引缺失、大表全扫描
- `checkpoints_req` 占比明显高于 `checkpoints_timed`：`max_wal_size` 可能偏小，导致提前触发 checkpoint
- 死元组占比（`n_dead_tup / (n_live_tup + n_dead_tup)`）> 10–20% 且持续增长：autovacuum 跟不上，检查 `autovacuum_vacuum_scale_factor`/是否被长事务/复制槽阻塞
- 存在长时间 `granted=false` 的锁等待：定位阻塞源头（`pg_blocking_pids`），检查是否有未提交的长事务
- 复制延迟（`replay_lag`）持续增长：检查从库 IO/网络/是否有长查询占用 `hot_standby_feedback`
- 临时文件（`temp_files`/`temp_bytes` 增量明显）：`work_mem` 可能偏小，或存在需要优化的排序/哈希操作

### Step 5：输出

- 语言：中文，Markdown 格式
- 保存路径：当前项目 `markdown/` 目录（与其他分析类 skill 保持一致），文件名建议 `awr_<dbname>_<snapshot_A_time>_<snapshot_B_time>.md`
- 图表：优先用 Mermaid（趋势/占比用简单的柱状/饼图描述，或用 Markdown 表格 + 简易 ASCII 条形图），避免过度依赖外部渲染
- 报告开头必须包含"降级矩阵/能力边界"小节，明确本次报告哪些章节因权限/扩展缺失被跳过
- 报告末尾必须包含 3–5 条按优先级排序的 Findings & Recommendations，每条给出：现象 → 可能原因 → 建议动作 → 建议验证方式（不下"绝对结论"，给出可证伪的验证路径）

## 使用附带脚本

`scripts/pg_awr_collector.py` 实现了 Step 0–3 的自动化采集（两次快照 + 采样窗口内的等待事件轮询 + 增量计算），输出一份结构化 JSON（`snapshot_diff.json`），供后续按 Step 4 的章节结构直接改写成 Markdown 报告。用法：

```bash
python3 scripts/pg_awr_collector.py --dsn "postgresql://user:password@host:5432/dbname" \
  --interval-seconds 900 --ash-sample-interval 2 --output snapshot_diff.json
```

脚本本身不生成最终 Markdown 报告（避免把措辞/建议逻辑锁死在代码里），由 Agent 读取 `snapshot_diff.json` 后按 Step 4 的结构和阈值规则撰写成给用户看的报告。

详细字段级 SQL 见 `references/pg_catalog_queries.md`；常见坑见下表。

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|---|---|
| 两次快照之间被人手动执行了 `pg_stat_reset()` | 采集前检查 `pg_stat_database.stats_reset`，若 A/B 之间 reset 时间戳变化，说明计数器被清零，删除本次报告的增量章节并提示用户 |
| 云 RDS 无 superuser，禁用部分系统函数 | 全程只依赖增量做差，不依赖 `pg_stat_reset()`/`pg_terminate_backend()` 等高权限操作 |
| `pg_stat_statements` 跨库聚合但 query 文本可能被截断/归一化（`?` 占位符） | 报告中说明这是归一化后的语句模板，不是原始 SQL 字面量 |
| 一个实例挂多个业务库 | 需要说明本次报告聚焦哪个 `dbname`，如需全实例视角需对每个库分别连接采集 `pg_stat_statements`（该视图是实例级但需要在对应库内查询才能拿到该库的 query 文本） |
| 大表用 `count(*)` 估算行数导致长时间扫描 | 一律用 `pg_stat_user_tables.n_live_tup` 或 `pg_class.reltuples` 近似值 |
| 采集窗口太短（<5分钟）或业务空载 | Load Profile/Top SQL 会失真，报告中标注"采样窗口过短，结论仅供参考" |
| 连接数紧张时还开多个诊断连接 | 采集脚本全程复用一个连接，不额外占用连接池 |
| 密码通过命令行参数传递可能出现在进程列表 `ps aux` 中 | 优先使用环境变量 `PGPASSWORD` 或 `~/.pgpass`，脚本设计上支持从环境变量读取 |

## 注意事项

- 全程只读，不执行 DDL/DML，不修改业务数据
- 需要 superuser/pg_monitor 权限的操作（如临时开启 `track_io_timing`）必须先取得用户明确同意
- 报告和任何中间产物中不得包含明文密码
- 网络访问仅限用户提供的目标数据库地址
- 若在无法直连数据库的沙箱环境中运行，如实告知网络限制，改为交付采集脚本供用户在有权限的环境执行
