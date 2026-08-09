---
name: kingbase-awr-report
description: "给定 KingbaseES（金仓）数据库连接串（host/port/dbname/user/password 或 postgresql:// URI），以资深 KingbaseES DBA 专家视角连接数据库，采集两个时间点的系统计数器视图并做差，生成类似 Oracle AWR 报告的 KingbaseES 性能诊断报告（Load Profile、Top SQL、等待事件、实例效率、Checkpoint/BGWriter、锁等待、复制延迟、表膨胀、配置快照、Findings & Recommendations）。KingbaseES 默认采用 PG 兼容模式，因此 SQL/视图与 PostgreSQL 高度一致，但 Top SQL 取自 `sys_stat_statements` 而非 `pg_stat_statements`，且 kingbase 自带 `sys_kwr` 自动快照仓库可作交叉验证。触发条件：用户提到「生成AWR报告」「KingbaseES性能报告」「金仓AWR」「金仓性能报告」「金仓数据库健康检查」「金仓数据库体检」「给你连接串帮我看看这个金仓库」「Top SQL分析」「等待事件分析」「sys_stat_statements 分析」「金仓数据库负载画像」「类似Oracle AWR」「金仓性能诊断报告」「帮我诊断一下这个KingbaseES实例」「sys_kwr 报告」「查看 sys_stat_statements」「金仓 KWR」，或者用户直接提供了 KingbaseES 连接串/密码并希望做性能分析、健康检查、慢SQL排查。即使用户只说「帮我看看这个金仓库最近咋样」但同时给了连接信息，也应使用本 skill。"
tags: [KingbaseES, 金仓, AWR, 健康报告, sys_stat_statements]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# KingbaseES AWR 风格性能报告生成器

以资深 KingbaseES DBA 专家的方法论，把 Oracle AWR「两次快照做差得到速率」的核心思路移植到 KingbaseES。KingbaseES（KES）默认采用 PostgreSQL 兼容模式，因此 `pg_stat_*` 视图体系在 KingbaseES 上基本可用，统计计数器与 PG 同样都是自实例启动或上次 `pg_stat_reset()` 以来的累计值。只要在时间点 A 和时间点 B 各采一次快照、做差再除以采样时长，就能得到和 AWR 报告一样的"负载画像"（Load Profile）与 Top SQL、等待事件、效率指标。

> KingbaseES 兼容性说明（影响 Top SQL 取数）：
> - 标准 PG：使用 `pg_stat_statements` 扩展，取数视图 `pg_stat_statements`
> - KingbaseES：使用 `sys_stat_statements` 扩展（默认随 `shared_preload_libraries='sys_stat_statements'` 启动），取数视图 `sys_stat_statements`，字段命名基本一致，但额外提供 `parses`/`plans`/`total_parse_time`/`total_plan_time` 解析/规划耗时统计，**不提供** `wal_records`/`wal_bytes` 字段（WAL 生成量改由 `pg_wal_lsn_diff` 计算）
> - KingbaseES 还内置 `sys_kwr` 自动快照仓库，可作为本 skill 的"自动版 AWR"交叉验证（详见后文"补充章节"）

## 前置要求

- 运行环境需要能直连目标数据库的 `host:port`。
  - **重要**：如果当前在 Claude 官方网页版/移动端沙箱中执行，出站网络受白名单限制，通常无法直连用户自己的数据库地址。此时应如实告知用户，并改为：(a) 输出本 skill 附带的 `scripts/kingbase_awr_collector.py` 采集脚本，请用户在能访问数据库的机器（本地终端、跳板机、Claude Code 本地环境）上运行，把生成的两份 JSON 快照回传；或 (b) 在具备网络出口权限的 Claude Code / 类似环境中直接执行本 skill 全流程。
- 客户端依赖：`python3 -m pip install psycopg2-binary --break-system-packages`（或系统自带 `ksql`/`psql`，KingbaseES 自带 `ksql` 客户端，语法与 `psql` 高度兼容）。
- 建议的数据库账号权限：具备超级用户（`rolsuper=t`），或至少对 `pg_stat_database`、`pg_stat_bgwriter`、`pg_stat_activity`、`sys_stat_statements`、`pg_stat_replication`、`pg_locks`、`pg_stat_user_tables`、`pg_statio_user_tables`、`pg_settings` 有 SELECT 权限。KingbaseES 默认无 `pg_monitor` 角色概念，靠 `rolsuper`/显式 GRANT 控制访问。非 superuser 也能运行，功能会按下方"降级矩阵"自动收缩范围。
- **连接串解析优先级**（脚本与 skill 一致）：
  1. 命令行参数 `--dsn` / `-H/-p/-d/-U/-W` 或独立环境变量 `KINGBASE_HOST` 等显式传入
  2. PG 兼容环境变量 `PGHOST` / `PGPORT` / `PGDBNAME` / `PGUSER` / `PGPASSWORD`
  3. kingbase 专属环境变量 `KINGBASE_HOST` / `KINGBASE_PORT` / `KINGBASE_DB` / `KINGBASE_USER` / `KINGBASE_PASSWORD`
  4. 内置默认值：`host=127.0.0.1, port=5432, dbname=kingbase, user=kingbase, password=123456`（仅在没有以上任何环境变量时使用）

## 安全底线（不可协商）

1. **绝不明文回显或落盘密码**：连接串中的密码只用于建立连接，不写入报告、不写入日志、不出现在生成的任何 Markdown/JSON 文件里；展示连接串时一律脱敏为 `postgresql://user:***@host:port/db`。
2. **只读操作为主**：不执行任何 DDL/DML，不修改用户业务数据，不调用 `pg_stat_reset()`。
3. 如需临时开启 `track_io_timing`（用于获得 IO 耗时数据）等参数，必须先向用户说明这是全局/会话级改动、采集完成后是否需要还原，取得确认后再执行。
4. 不对陌生/未授权的数据库地址发起连接；连接目标必须是用户本人提供的。
5. 大表禁止使用 `SELECT count(*)` 做体检（会做全表扫描甚至长时间持锁），行数估算一律使用 `pg_stat_user_tables.n_live_tup` 或 `pg_class.reltuples`。
6. KingbaseES 内置 `sys_kwr` 自动快照仓库由 kingbase 后台进程写盘，**不要手动调用** `kwr_snap`、`kwr_report`、`kwr_delete` 等函数，避免污染 kingbase 自带的 AWR 历史；本 skill 维持"两次快照做差"思路，与 kingbase 内置 KWR 并行运行互不干扰。

## 工作流程

### Step 0：解析连接信息 & 环境探测

解析连接串后，第一步先跑：

```sql
SELECT version(), current_setting('server_version_num')::int AS ver_num,
       pg_is_in_recovery() AS is_standby, now() AS db_time,
       pg_postmaster_start_time() AS start_time;

SELECT rolname, rolsuper, rolreplication FROM pg_roles WHERE rolname = current_user;

-- 探测 kingbase 自带 KWR 是否启用（仅探测，不主动操作）
SELECT extname, extversion FROM pg_extension
WHERE extname IN ('sys_stat_statements','sys_kwr','sys_hm','sys_spacequota','sys_squeeze')
ORDER BY 1;

SELECT name, setting, unit FROM pg_settings
WHERE name IN ('shared_buffers','work_mem','maintenance_work_mem','effective_cache_size',
  'max_connections','track_io_timing','track_activities','autovacuum','wal_level',
  'max_wal_size','checkpoint_timeout','random_page_cost','shared_preload_libraries',
  'syskwr_enable','sys_stat_statements_max');
```

记录：版本号（KES V9R1C10 对应 `server_version_num` 大致为 120001，PG 12 兼容）、是否备库、实例启动时间（决定 `pg_stat_bgwriter`/`pg_stat_database` 的计数器是"自启动以来"还是"自上次 reset 以来"，两次快照的差值才有意义，因此**不要**在两次快照之间执行 `pg_stat_reset()`）。

**降级矩阵**（探测后据此裁剪报告章节，并在报告开头列出"本次报告能力边界"）：

| 条件缺失 | 影响 | 处理方式 |
|---|---|---|
| 无 `sys_stat_statements` 扩展 | 无法生成 Top SQL 章节 | 跳过该章节，报告中给出安装命令：`shared_preload_libraries` 加入 `sys_stat_statements` 后重启 + `CREATE EXTENSION sys_stat_statements;`（KES V9R1C10 默认已开启） |
| `track_io_timing = off` | Top SQL / IO 耗时字段全为 0 | 提示可临时 `SET track_io_timing = on;`（会话级，仅对本连接后续查询生效，不影响其他会话），采集完成后说明该设置不持久 |
| 非 superuser | `pg_stat_activity.query` 对他人会话可能被打码（KES 沿用 PG12 行为），部分统计视角受限 | 报告中标注"以当前账号可见范围为准"，不假装看到了全局真相 |
| 云托管 RDS（阿里云 RDS for KingbaseES 等） | 通常没有真正的 superuser，部分系统函数被禁用 | 完全依赖增量做差法，不依赖 reset 权限 |
| 无从库 / 非主库角色 | 无复制延迟章节 | 跳过 |
| `sys_kwr` 未启用 | 无法做 kingbase 内置 KWR 自动快照交叉验证 | 跳过"补充章节：sys_kwr 历史快照交叉验证"小节，并在报告中给出开启命令（需重启） |
| `pg_wal_lsn_diff` 函数不可用（极少数早期 KES 版本） | WAL 生成速率无法计算 | 改用 `pg_current_xlog_location()` 与 `pg_xlog_location_diff()`（KES 早期版本名），报告中标注 |

### Step 1：采集 Snapshot A（begin）

一次性采集以下视图并连同采集时间戳整体落成一份内存/JSON 结构（字段清单见 `references/kingbase_catalog_queries.md`）：

- `pg_stat_database`（目标库 + 全库汇总；字段与 PG12 一致）
- `pg_stat_bgwriter`（KES V9R1C10 基于 PG12，无 `pg_stat_checkpointer` 拆分，仍走 `pg_stat_bgwriter`）
- `sys_stat_statements`（若可用，Top by `total_exec_time`/`calls`/`mean_exec_time`）
- `pg_stat_user_tables` / `pg_statio_user_tables`（增删改行数、死元组、autovacuum 次数与时间、buffer 命中）
- `pg_stat_replication` / `pg_stat_wal_receiver`（若有从库/为从库）
- `pg_current_wal_lsn()`（主库）或 `pg_last_wal_replay_lsn()`（备库），用于算 WAL 生成速率
- `pg_database_size(datname)`：各库大小，用于算增长
- （可选）`sys_stat_statements_all`：跨库全量视图，若用户希望看跨库 Top SQL 时采集

### Step 2：等待间隔

默认间隔 **15–30 分钟**（可配置，最短建议 5 分钟）。明确告知用户："采集窗口内请让真实业务负载正常运行，窗口太短或空载会让 Top SQL / Load Profile 失真"。

在等待期间，如果需要模拟 Oracle 的 ASH（Active Session History），可用轮询方式每 1–2 秒采一次 `pg_stat_activity` 的 `wait_event_type`/`wait_event`/`state`，持续整个窗口，事后做等待事件分布统计（KingbaseES 与 PG 同样没有内建 ASH，这是唯一能拿到"当下正在等什么"的办法；`scripts/kingbase_awr_collector.py` 内置了这个采样循环）。

### Step 3：采集 Snapshot B（end），计算 Delta

对计数器类字段做差（B − A）；对状态类字段（当前连接数、当前锁等待、当前复制延迟）直接取 B 时刻的值。核心公式：

- 采样时长 `Δt`（秒）= B.采集时间 − A.采集时间
- TPS = `(xact_commit + xact_rollback 的增量) / Δt`
- QPS（近似）= `sum(sys_stat_statements.calls 的增量) / Δt`（仅当扩展可用）
- Buffer Cache Hit % = `1 - (blks_read 增量) / (blks_read 增量 + blks_hit 增量)`（越接近 100% 越好，长期 < 99% 需要关注 `shared_buffers`/索引设计）
- WAL 生成速率 = `pg_wal_lsn_diff(lsn_B, lsn_A) / Δt`（字节/秒）
- 解析/规划耗时（KingbaseES 特有）：`total_parse_time`/`total_plan_time` 增量，可反映硬解析/重规划开销
- 单表增删改速率、死元组增长速率、autovacuum 触发次数增量，用于判断膨胀/vacuum 是否跟得上写入

若 Snapshot B 采集失败（连接中断等），报告需要降级为"仅基于 Snapshot A 的静态健康检查"，并在报告顶部明确标注，不得假装有完整的 Load Profile。

### Step 4：按 Oracle AWR 章节结构生成报告

| Oracle AWR 章节 | KingbaseES 对应实现 |
|---|---|
| Report Summary | 版本/是否备库/采集窗口/降级矩阵结果/`sys_kwr` 状态 |
| Load Profile | 上面 Step 3 的速率指标表（TPS/QPS/WAL生成/回滚率/临时文件/解析规划耗时） |
| Instance Efficiency Percentages | Buffer Hit%、Index Hit%、Parse-to-Exec 比率（KingbaseES 特有，可由 `sys_stat_statements.parses`/`calls` 推算） |
| Top SQL | `sys_stat_statements` 按 `total_exec_time`/`calls`/`mean_exec_time`/`shared_blks_read` 分别 Top 10 |
| Wait Event / Wait Class | 采样期内 `wait_event_type` 分布直方图 + Top `wait_event` |
| Checkpoint & Background Writer | `checkpoints_timed/req` 增量、`buffers_checkpoint/clean/backend` 增量，判断是否 checkpoint 过于频繁（间隔小于 `checkpoint_timeout` 触发的 `_req` 占比过高） |
| 锁等待 Top | Snapshot B 时刻 `pg_locks` 中 `granted=false` 的记录 + 阻塞链（`pg_blocking_pids()`） |
| 复制延迟 | `pg_stat_replication.replay_lag` 等（若适用） |
| 表膨胀 & Autovacuum | 死元组占比 Top、autovacuum 次数与耗时增量 |
| Segments Growth | 各库/Top 表大小增长 Top 10 |
| 配置快照 | Step 0 采集的关键 GUC（含 `syskwr_enable`/`sys_stat_statements_max`） |
| 补充：sys_kwr 交叉验证 | 若 `sys_kwr` 启用，列出近 N 次自动快照的统计摘要（仅引用，不操作） |
| Findings & Recommendations | 见下方阈值规则 |

**给建议时使用的经验阈值**（仅作为提示线索，不是绝对红线，需结合业务上下文）：

- Buffer Hit % 持续 < 99%：关注 `shared_buffers`、索引缺失、大表全扫描
- `checkpoints_req` 占比明显高于 `checkpoints_timed`：`max_wal_size` 可能偏小，导致提前触发 checkpoint
- 死元组占比（`n_dead_tup / (n_live_tup + n_dead_tup)`）> 10–20% 且持续增长：autovacuum 跟不上，检查 `autovacuum_vacuum_scale_factor`/是否被长事务/复制槽阻塞；KingbaseES 还可考虑 `sys_squeeze` 在线压缩（详见 kingbase 文档）
- `sys_stat_statements.parses` 增量明显高于 `calls` 增量（Parse-to-Exec > 1.2）：连接池未复用 prepared statement，需检查应用是否走 PreparedStatement 缓存
- `total_plan_time` 占比 `total_exec_time` 超过 10–20%：统计信息陈旧或绑定变量窥探失败，建议 `ANALYZE` 或调优
- 存在长时间 `granted=false` 的锁等待：定位阻塞源头（`pg_blocking_pids`），检查是否有未提交的长事务
- 复制延迟（`replay_lag`）持续增长：检查从库 IO/网络/是否有长查询占用 `hot_standby_feedback`
- 临时文件（`temp_files`/`temp_bytes` 增量明显）：`work_mem` 可能偏小，或存在需要优化的排序/哈希操作

### Step 5：输出

- 语言：中文，Markdown 格式
- 保存路径：当前项目 `markdown/` 目录（与其他分析类 skill 保持一致），文件名建议 `kingbase_awr_<dbname>_<snapshot_A_time>_<snapshot_B_time>.md`
- 图表：优先用 Mermaid（趋势/占比用简单的柱状/饼图描述，或用 Markdown 表格 + 简易 ASCII 条形图），避免过度依赖外部渲染
- 报告开头必须包含"降级矩阵/能力边界"小节，明确本次报告哪些章节因权限/扩展缺失被跳过
- 报告末尾必须包含 3–5 条按优先级排序的 Findings & Recommendations，每条给出：现象 → 可能原因 → 建议动作 → 建议验证方式（不下"绝对结论"，给出可证伪的验证路径）

## 使用附带脚本

`scripts/kingbase_awr_collector.py` 实现了 Step 0–3 的自动化采集（两次快照 + 采样窗口内的等待事件轮询 + 增量计算），输出一份结构化 JSON（`snapshot_diff.json`），供后续按 Step 4 的章节结构直接改写成 Markdown 报告。脚本特性：

- **连接参数解析优先级**：命令行 `--dsn` / `-H/-p/-d/-U/-W` > `PGHOST`/`PGPORT`/`PGDBNAME`/`PGUSER`/`PGPASSWORD` > `KINGBASE_HOST`/`KINGBASE_PORT`/`KINGBASE_DB`/`KINGBASE_USER`/`KINGBASE_PASSWORD` > 内置默认（仅在没有以上任何环境变量时使用）
- **兼容 psycopg2 与 psql**：脚本使用 `psycopg2` 直连；如需在客户端机器用 `ksql`/`psql` 等价执行采集 SQL，可参考 `references/kingbase_catalog_queries.md` 中的 SQL 模板

用法：

```bash
# 推荐：通过环境变量传密码，避免出现在进程列表里
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGPASSWORD=xxx \
       PGDBNAME=kingbase
python3 scripts/kingbase_awr_collector.py --interval-seconds 900 \
  --ash-sample-interval 2 --output snapshot_diff.json

# 或显式传 DSN
python3 scripts/kingbase_awr_collector.py \
  --dsn "postgresql://kingbase:xxx@127.0.0.1:5432/kingbase" \
  --interval-seconds 900 --ash-sample-interval 2 --output snapshot_diff.json
```

脚本本身不生成最终 Markdown 报告（避免把措辞/建议逻辑锁死在代码里），由 Agent 读取 `snapshot_diff.json` 后按 Step 4 的结构和阈值规则撰写成给用户看的报告。

详细字段级 SQL 见 `references/kingbase_catalog_queries.md`；常见坑见下表。

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|---|---|
| 两次快照之间被人手动执行了 `pg_stat_reset()` | 采集前检查 `pg_stat_database.stats_reset`，若 A/B 之间 reset 时间戳变化，说明计数器被清零，删除本次报告的增量章节并提示用户 |
| 云 RDS for KingbaseES 无 superuser | 全程只依赖增量做差，不依赖 `pg_stat_reset()`/`pg_terminate_backend()` 等高权限操作 |
| `sys_stat_statements` 跨库聚合但 query 文本可能被截断/归一化（`?` 占位符） | 报告中说明这是归一化后的语句模板，不是原始 SQL 字面量 |
| 把 `sys_stat_statements` 当成 `pg_stat_statements` 查询 | SELECT 字段列表中**不包含** `wal_records`/`wal_bytes`（kingbase 无此字段），多包含 `parses`/`plans`/`total_parse_time`/`total_plan_time` |
| 一个实例挂多个业务库 | 需要说明本次报告聚焦哪个 `dbname`；如需全实例视角，需对每个库分别连接采集 `sys_stat_statements`（该视图是实例级但需要在对应库内查询才能拿到该库的 query 文本）或直接用 `sys_stat_statements_all` |
| 大表用 `count(*)` 估算行数导致长时间扫描 | 一律用 `pg_stat_user_tables.n_live_tup` 或 `pg_class.reltuples` 近似值 |
| 采集窗口太短（<5分钟）或业务空载 | Load Profile/Top SQL 会失真，报告中标注"采样窗口过短，结论仅供参考" |
| 连接数紧张时还开多个诊断连接 | 采集脚本全程复用一个连接，不额外占用连接池 |
| 密码通过命令行参数传递可能出现在进程列表 `ps aux` 中 | 优先使用环境变量 `PGPASSWORD`/`KINGBASE_PASSWORD` 或 `~/.pgpass`/`~/.kingbasepass`，脚本设计上支持从环境变量读取 |
| kingbase 内置 `sys_kwr` 自动快照被误调 | 本 skill 仅**读取** `sys_stat_kwr_snapshot` 等只读视图，绝不调用 `kwr_snap()`/`kwr_report()`/`kwr_delete()` 等会污染 kingbase AWR 历史的过程 |

## 注意事项

- 全程只读，不执行 DDL/DML，不修改业务数据，不调用 `pg_stat_reset()` / `kwr_snap()` 等可能改变数据库状态的过程
- 需要 superuser 权限的操作（如临时开启 `track_io_timing`）必须先取得用户明确同意
- 报告和任何中间产物中不得包含明文密码
- 网络访问仅限用户提供的目标数据库地址
- 若在无法直连数据库的沙箱环境中运行，如实告知网络限制，改为交付采集脚本供用户在有权限的环境执行
- 本 skill 与 kingbase 内置 `sys_kwr` 自动快照系统是**互补关系**，不替代；建议长期运维同时启用 `sys_kwr` 让 kingbase 自己保留 AWR 历史，本 skill 在需要时做即时人工深入分析