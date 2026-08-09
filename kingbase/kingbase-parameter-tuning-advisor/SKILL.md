---
name: kingbase-parameter-tuning-advisor
description: "以 KingbaseES DBA 专家、操作系统专家、存储专家、网络专家的复合视角，给定一个金仓（KingbaseES）实例的连接串和账号密码，自动连接实例并（在授权情况下）登录其所在主机，采集数据库侧（pg_settings/kingbase.conf 参数、pg_stat_*/sys_catalog.sys_stat_* 统计视图、sys_stat_statements、EXPLAIN）与操作系统侧（CPU/内存/磁盘/文件系统/网络）指标，识别 workload 特征与瓶颈，产出一份 kingbase.conf 参数调整建议报告，逐项给出调整前后的值、调整原因（有数据支撑）、预期收益、生效方式与风险。KingbaseES 默认采用 PG 兼容模式，因此 pg_settings/pg_stat_* 等视图与 PostgreSQL 一致，但 pg_stat_statements 不存在，需使用 sys_stat_statements；配置文件名是 kingbase.conf 而非 postgresql.conf。触发条件：用户提到'帮我调优这个金仓实例'、'金仓参数优化'、'KingbaseES 参数调优'、'kingbase.conf 怎么调'、'金仓这个库跑得慢帮我看看参数'、'金仓内核参数/数据库参数调优建议'、'给我一份金仓调优报告'、'金仓 connection string + 密码 帮我分析一下'，或提供了 KingbaseES 连接串/密码并希望得到调优建议时，必须使用本 skill。即使用户只说'帮我看看这个金仓实例的参数'或'这个金仓库最近跑得怎么样、参数要不要调'，也应使用本 skill。只产出分析报告，不生成、不执行任何修改数据库配置的可执行脚本或 ALTER SYSTEM 语句。"
tags: [KingbaseES, 金仓, 参数优化, kingbase.conf, 性能调优]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# KingbaseES 参数调优顾问

给定一个 KingbaseES（金仓）实例的连接串和账号密码，自动分析其 workload 特征、硬件环境与运行状态，产出一份可操作、有数据支撑的 `kingbase.conf` 参数调整建议报告。本 skill 只做**只读分析**和**报告输出**，不生成、不执行任何修改线上配置的脚本或 SQL（不执行 `ALTER SYSTEM`、不修改 `kingbase.conf`、不重启/reload 实例）。

> KingbaseES 默认采用 **PG 兼容模式**：`pg_settings`、`pg_stat_activity`、`pg_stat_database`、`pg_stat_bgwriter`、`pg_stat_user_tables` 等系统视图与 PostgreSQL 高度一致；同时 `sys_catalog` 下存在 `sys_settings`、`sys_stat_activity`、`sys_stat_database` 等同义视图。**注意**：金仓没有 `pg_stat_statements`，其等价物是 `sys_stat_statements`（public schema，列结构与 PG14+ 一致）。配置文件名是 `kingbase.conf`（对应 PG 的 `postgresql.conf`），连接认证文件是 `sys_hba.conf`。

## 角色定位

分析过程中同时以四种专家视角审视问题：

| 视角 | 关注点 |
|------|--------|
| KingbaseES DBA 专家 | shared_buffers / work_mem / autovacuum / checkpoint / WAL / 连接数等数据库侧参数 |
| 操作系统专家 | CPU 核数与调度、内存与 swap、THP、ulimit、NUMA |
| 存储专家 | 磁盘类型（HDD/SSD/NVMe）、IO 调度器、文件系统与挂载选项、IO 延迟与吞吐 |
| 网络专家 | 连接数与 TCP 参数、网络延迟对同步提交/复制的影响 |

四个视角的结论最终要汇总到同一份报告的参数建议表里，而不是分别输出四份报告。

## 前置要求

- 本机已安装 `psql`（PG 客户端可直连金仓；金仓安装目录下亦有 `ksql`/`sys_ksql`），或 Python `psycopg2` 驱动。检测与安装：
  ```bash
  command -v psql || echo "请安装 PostgreSQL 客户端或使用金仓安装目录 bin/ 下的 ksql/sys_ksql"
  python3 -c "import psycopg2" 2>/dev/null || echo "可选: pip install psycopg2-binary"
  ```
- 若用户同意采集操作系统指标，需要能执行常见只读诊断命令：`free`、`vmstat`、`iostat`（sysstat 包）、`lscpu`、`nproc`、`lsblk`、`ss`、`df`、`mount`、`cat /proc/*`。缺失时优雅降级，跳过对应指标并在报告中注明"未采集"。
- 若目标主机与执行环境不是同一台机器，且需要采集 OS 指标，需要用户提供可用的 SSH 访问方式（host/port/user + 密钥或密码，或已配置好的免密登录）。
- 网络需能访问目标金仓实例的 host:port（数据库连接层面）。
- **金仓默认账号**：本 skill 默认采用 `kingbase` / `123456` / 5432 与同名数据库 `kingbase`（注意：金仓安装后默认库是 `kingbase`，**没有** `postgres` 库）。

## 连接约定

按优先级解析连接参数：

1. 用户明确提供的连接参数（host/port/dbname/user/password）；
2. 环境变量 `PGHOST` `PGPORT` `PGDBNAME`（或 `PGDATABASE`）`PGUSER` `PGPASSWORD`（即使 KingbaseES 手册把这些变量写作 `KINGBASEHOST`/`KINGBASE_HOST` 等 `KINGBASE_*` 形式，本 skill **继续沿用 PG 风格的环境变量**，脚本同时兼容两者）；
3. 缺省值：`PGHOST=127.0.0.1 PGPORT=5432 PGDBNAME=kingbase PGUSER=kingbase PGPASSWORD=123456`。

## 兼容模式说明

- 金仓默认数据库为 **PG 兼容模式**，本 skill 的所有 SQL 均在该模式下验证。
- 可以用 `SHOW database_mode;` 确认当前会话的兼容模式（取值如 `pg`/`oracle`/`mysql`；在 V9 中该参数为 session/DB 级）。若目标库是 Oracle/MySQL 兼容模式，`pg_*` 系统视图仍可用（它们始终存在），但部分 GUC 与 SQL 行为（如日期函数、空串处理、序列用法）会有差异，报告中应注明，且参数建议优先针对 PG 兼容模式给出。
- 配置文件名：`SHOW config_file;` 通常返回 `.../data/kingbase.conf`；认证文件为 `sys_hba.conf`。

## 工作流程

### Step 0：解析连接信息，安全处理密码

用户会直接在对话中提供连接串和密码，按以下方式处理：

1. 从连接串中解析出 `host`、`port`、`dbname`、`user`；密码单独处理。
2. **执行 psql 时优先使用 `PGPASSWORD` 环境变量传参，而不要把密码拼进命令行参数**（避免密码出现在 `ps aux`、shell history 中）：
   ```bash
   PGPASSWORD='<密码>' psql -h <host> -p <port> -U <user> -d <dbname> -Atqc "<SQL>"
   ```
3. 分析过程中和最终报告里，**永远不要把密码明文写入任何输出文件、日志或报告**。报告中涉及连接信息时只写 host/port/dbname/user，密码用 `******` 代替。
4. 如果用户提供的是标准 `postgresql://user:password@host:port/dbname` 形式，同样先解析出各字段再按上面方式使用，不要整串透传给下游命令。

### Step 1：环境识别

判断当前执行环境与目标数据库主机的关系，决定能采集到哪些数据：

```bash
# 判断是否已经就在目标数据库所在主机上
hostname -I 2>/dev/null; hostname
# 与连接串中的 host 做比对（若 host 是 127.0.0.1/localhost，且本机确实跑着 kingbase 进程，则视为同机）
pgrep -a kingbase | head -5
ps -ef | grep '[k]ingbase' | head -5
```

三种情况：

- **同机执行**：直接用本地命令采集 OS 指标，无需 SSH。
- **需要 SSH 到 DB 主机**：使用用户提供的 SSH 信息远程执行 Step 3 中的只读命令；每条命令只做采集，不做任何写入/重启操作。
- **仅有数据库连接权限，无主机访问权限**：跳过 Step 3 的直接 OS 采集，改为通过数据库侧视图间接推断硬件特征（见 Step 3 "无主机权限时的间接推断"）。

不确定采集范围时，在开始分析前用一句话向用户确认："本次是否可以 SSH 到数据库主机采集操作系统指标？" 若用户已经在本轮任务中明确授权（如已提供 SSH 信息），直接执行，无需重复确认。

### Step 2：采集 KingbaseES 侧信息

使用 `scripts/collect_kingbase_metrics.sql` 中的查询集合（可分批执行，每次连接后主动关闭连接，不占用长连接）。也可以用 `scripts/collect_kingbase_metrics.py`（psycopg2 版）或 `scripts/collect_kingbase_metrics.sh`（psql 版）一键采集。核心采集内容：

1. **实例基础信息**：`SELECT version();`、`SHOW server_version;`、`SHOW database_mode;`、`SHOW config_file;`（kingbase.conf 路径）、`SHOW data_directory;`、运行时长 `pg_postmaster_start_time()`。
2. **当前生效的关键参数**（对照 `references/parameter_knowledge_base.md` 里的参数清单，用 `SHOW ALL` 或针对性 `SHOW xxx` 采集），尤其是：
   - 内存类：`shared_buffers`、`work_mem`、`maintenance_work_mem`、`effective_cache_size`、`huge_pages`
   - 连接类：`max_connections`、`superuser_reserved_connections`
   - WAL/Checkpoint 类：`wal_buffers`、`min_wal_size`、`max_wal_size`、`checkpoint_timeout`、`checkpoint_completion_target`、`wal_compression`
   - 并行/后台类：`max_worker_processes`、`max_parallel_workers`、`max_parallel_workers_per_gather`、`max_wal_senders`
   - Autovacuum 类：`autovacuum_max_workers`、`autovacuum_vacuum_cost_limit`、`autovacuum_naptime`、`autovacuum_vacuum_scale_factor`、`autovacuum_analyze_scale_factor`
   - Planner 类：`random_page_cost`、`effective_io_concurrency`、`default_statistics_target`
   - 提交/复制类：`synchronous_commit`、`synchronous_standby_names`
   - 附加：`track_io_timing`（决定能否采集 blk_read_time/blk_write_time）、`shared_preload_libraries`（判断 sys_stat_statements 是否已加载）
3. **Workload 与瓶颈信号**：
   - 缓存命中率：`pg_stat_database` 里 `blks_hit / (blks_hit + blks_read)`
   - Checkpoint 压力：`pg_stat_bgwriter` 里 `checkpoints_timed` vs `checkpoints_req`（后者占比高说明 `max_wal_size` 偏小）、`buffers_backend` 占比高说明 `shared_buffers`/bgwriter 不够
   - 临时文件溢出：`pg_stat_database.temp_files` / `temp_bytes`（持续增长说明 `work_mem` 偏小）
   - 连接压力：`pg_stat_activity` 当前连接数 vs `max_connections`，以及 `state` 分布（`idle in transaction` 过多是应用层问题，不建议单纯加大 `max_connections`）
   - 锁等待：`pg_locks` 里 `granted = false` 的记录
   - 慢查询/高频查询：金仓用 `sys_stat_statements`（**不是** `pg_stat_statements`，后者在金仓上不存在）。取 `total_exec_time`、`calls`、`mean_exec_time` 排名前 10~20 的查询，辅助判断 `work_mem`、索引、`default_statistics_target` 是否需要调整。若该视图不可用（报 relation "sys_stat_statements" does not exist），说明 `shared_preload_libraries` 未加载 `sys_stat_statements` 扩展，报告中提示"建议启用 sys_stat_statements 以获得更精确的 workload 画像"，同时基于 `pg_stat_database`/`pg_stat_user_tables` 降级给出结论。
   - 表膨胀与扫描方式：`pg_stat_user_tables` 里 `seq_scan` vs `idx_scan`，配合表大小判断是否需要调 `random_page_cost`/`effective_io_concurrency` 或建索引（后者超出本 skill 范围，仅在报告中提示）
   - Autovacuum 滞后：`pg_stat_user_tables.last_autovacuum`、`n_dead_tup` 相对 `n_live_tup` 的比例

采集时**只使用只读查询**，不执行任何 `INSERT/UPDATE/DELETE/ALTER/CREATE/DROP`。若目标是生产库，避免一次性拉全表扫描类的诊断查询（如对超大表做无 LIMIT 的统计），必要时加 `LIMIT` 或使用 `pg_stat_*` 系统视图而非直接扫描业务表。

### Step 3：采集操作系统 / 存储 / 网络侧信息

已获得授权（同机或 SSH）时，使用 `scripts/collect_os_metrics.sh` 采集：

- **CPU**：`nproc`、`lscpu`（核数、是否开启超线程、NUMA 节点数）
- **内存**：`free -h`（总量、可用量、swap 使用情况——swap 被大量使用往往说明内存配置类参数偏大或物理内存不足）
- **磁盘/存储**：
  - `lsblk -d -o NAME,ROTA,SIZE,TYPE`（`ROTA=1` 是机械盘，`0` 是 SSD/NVMe）
  - 数据目录所在挂载点与文件系统：`df -h $(SHOW data_directory 的结果)`、`mount | grep <挂载点>`（关注是否有 `noatime`）
  - IO 压力：`iostat -x 1 3`（关注 `%util`、`await`、`r/s`、`w/s`）
- **网络**：`ss -s`（连接数概览）、`sysctl net.core.somaxconn net.ipv4.tcp_max_syn_backlog`（连接风暴场景相关）
- **内核/系统限制**：`ulimit -n`（进程最大文件句柄数，需大于 `max_connections` 相关的文件描述符预估）、`cat /sys/kernel/mm/transparent_hugepage/enabled`（THP 建议 `madvise` 或 `never`，`always` 可能导致延迟毛刺）
- **同机确认**：`pgrep -a kingbase` / `ps -ef | grep '[k]ingbase'`

**无主机权限时的间接推断**：如果 Step 1 判断为"仅有数据库连接权限"，则跳过上述直接采集，转而用以下方式间接估计硬件规模，并在报告中明确标注"该项为间接推断，非直接采集，建议用户核实"：

- 用 `effective_cache_size` 现有配置值反推运维人员对内存规模的预期（仅作为参考基线，不作为调整依据本身）
- 用 `pg_stat_bgwriter`/IO 相关统计（如 `blk_read_time`/`blk_write_time`，需 `track_io_timing = on`）估计存储的相对快慢
- 明确告知用户：无法获取真实物理内存/CPU核数/磁盘类型时，`shared_buffers`、`effective_cache_size`、`max_worker_processes` 等强依赖硬件规格的参数建议将标注为"待用户确认硬件规格后修正"，不给出确定性数值。

### Step 4：综合分析，识别 workload 类型与瓶颈

结合 Step 2/3 采集结果，判断：

1. **Workload 类型**：OLTP（高频短事务、随机点查为主）/ OLAP（少量长查询、大范围扫描聚合为主）/ 混合型 / 高并发写入型。判断依据：`sys_stat_statements` 中查询形态、`seq_scan` 与 `idx_scan` 比例、平均事务时长、`temp_files` 使用频率。
2. **主要瓶颈**（可能多个并存，需按影响程度排序）：
   - 内存不足导致缓存命中率低 / 频繁临时文件落盘
   - Checkpoint 过于频繁导致 IO 尖峰（`checkpoints_req` 占比高）
   - Autovacuum 跟不上导致膨胀和统计信息过期
   - 连接数配置与实际并发/物理核数不匹配
   - 磁盘 IO 延迟高（尤其机械盘场景）而 `random_page_cost`/`effective_io_concurrency` 未按存储介质调整
   - 网络/同步提交延迟影响写入吞吐（`synchronous_commit`/跨机房同步复制场景）
3. 每个瓶颈都要能追溯到 Step 2/3 采集到的具体数字，不能凭经验空判断。

### Step 5：生成参数调整建议

针对每一项建议调整的参数，遵循 `references/parameter_knowledge_base.md` 中的经验公式和取值范围，同时结合 Step 4 的具体瓶颈证据，得出建议值。每一项都必须包含：

- 参数名
- 调整前的值（Step 2 实际采集到的当前值，不是默认值）
- 建议调整后的值
- 调整原因（引用 Step 2/3/4 中的具体证据，如"缓存命中率 92.3%，低于健康阈值 99%，且 shared_buffers 当前仅为物理内存的 8%"）
- 预期收益（尽量量化或给出方向性预期，如"预计减少约 30% 的临时文件落盘"）
- 生效方式：`reload`（`SELECT sys_reload_conf();` / `SELECT pg_reload_conf();` 即可生效，服务器侧对应 `sys_ctl reload -D <data_dir>`）还是 `restart`（需要重启实例才能生效，如 `shared_buffers`、`max_connections`、`max_worker_processes`；服务器侧 `sys_ctl restart`）
- 风险提示（如调大 `work_mem` 在高并发下可能造成总内存超配，需要用 `max_connections × work_mem` 估算上限）

**不生成任何 `ALTER SYSTEM` 语句或 `kingbase.conf` diff 文件，也不建议用户直接复制粘贴执行——只给出"值"和"why"，把最终决策和执行留给用户自己或其变更管理流程。**

### Step 6：输出报告

将报告以 Markdown 格式输出（若在有项目目录的场景下，保存到当前项目 `markdown/` 目录；否则直接展示在对话中）。报告结构见下方"输出格式"，模板见 `assets/report_template.md`。

## 输出格式

```markdown
# KingbaseES 参数调优建议报告

## 实例概览
- 版本：<version>
- 兼容模式：<database_mode>
- 连接信息：host=<host> port=<port> dbname=<dbname> user=<user>（密码已脱敏）
- 配置文件：<config_file 路径，一般为 kingbase.conf>
- 采集时间：<timestamp>
- 采集范围：[数据库侧 / +操作系统侧 / +存储 / +网络]（注明哪些因权限未采集）

## 硬件与环境画像
- CPU：<核数、架构>
- 内存：<总量/可用/swap 使用情况>
- 存储：<磁盘类型、文件系统、挂载参数>
- 网络：<连接数概况、相关内核参数>

## Workload 特征判断
<OLTP/OLAP/混合型，判断依据>

## 关键瓶颈（按影响程度排序）
1. <瓶颈1，附数据证据>
2. <瓶颈2，附数据证据>
...

## 参数调整建议

| 参数名 | 调整前 | 建议调整后 | 调整原因 | 预期收益 | 生效方式 | 风险提示 |
|--------|--------|-----------|----------|----------|----------|----------|
| shared_buffers | 128MB | 4GB | ... | ... | restart | ... |
| work_mem | 4MB | 32MB | ... | ... | reload | ... |
| ... | ... | ... | ... | ... | ... | ... |

## 未纳入本次调整的观察项
<如索引缺失、慢查询本身需要改写、应用层连接池问题等——不属于 kingbase.conf 参数范畴，但值得用户关注>

## 数据来源与置信度说明
<哪些结论是直接采集，哪些是间接推断，采样窗口是否够长>
```

## Pitfalls & Solutions

| 坑点 | 说明 | 解决方案 |
|------|------|----------|
| 单次采样即下结论 | `pg_stat_*` 是累计值，单点快照可能被历史峰值污染 | 尽量采集两次（间隔几分钟到几十分钟）取差值，或结合 `pg_stat_bgwriter`/`pg_stat_database` 的时间跨度判断 |
| 误用 pg_stat_statements | 金仓上没有 `pg_stat_statements`，只有 `sys_stat_statements`（public schema） | 一律使用 `sys_stat_statements`；列结构与 PG14+ 一致（`total_exec_time`/`mean_exec_time` 单位为**毫秒**）。若报 relation does not exist，说明 `shared_preload_libraries` 未加载该扩展，降级并用报告中提示 |
| 混淆配置文件与命令 | 金仓配置文件名是 `kingbase.conf`（不是 postgresql.conf），reload/restart 命令是 `sys_ctl`（不是 pg_ctl），客户端是 `ksql`/`sys_ksql`（也可用 psql） | 报告中统一使用金仓命名；示例命令用 `sys_ctl reload -D <data_dir>`；SQL 侧 reload 可用 `SELECT sys_reload_conf();`（与 `pg_reload_conf()` 等价，均已验证存在） |
| sys_catalog.sys_stat_* 需要显式 schema | `sys_stat_activity` 等不带前缀查不到（不在 search_path），只有 `sys_catalog.sys_stat_activity` 可查 | 本 skill 默认使用 `pg_*` 视图（PG 兼容，与 sys_* 数据等价）；确需 sys_* 视图时加 `sys_catalog.` 前缀 |
| 金仓内置 schema 干扰统计 | `sys_catalog`/`sys_hm`/`sysaudit`/`sysmac`/`src_restrict` 等内置 schema 的表/查询会出现在统计视图里 | 分析 workload 时按 `n.nspname NOT IN (...)` 过滤内置 schema，避免把金仓自身维护负载误判为用户瓶颈 |
| 默认库名差异 | 金仓默认库是 `kingbase`，**没有** `postgres` 库 | 脚本默认 `PGDBNAME=kingbase`；枚举库时直接查 `pg_database`，不硬编码 `postgres` |
| 环境变量命名差异 | 金仓手册把连接变量写作 `KINGBASEHOST`/`KINGBASE_HOST` 等 | 本 skill 统一沿用 `PGHOST/PGPORT/PGDBNAME/PGDATABASE/PGUSER/PGPASSWORD`，脚本同时兼容 `KINGBASE_*` 变体 |
| 密码明文出现在命令行/日志 | `ps aux` 可看到明文参数，shell history 也会记录 | 统一使用 `PGPASSWORD` 环境变量或临时 `.pgpass`（用完立即删除），不要把密码拼进 `-h ... -U ... password=...` 这类可见参数里 |
| work_mem 建议值忽略并发放大效应 | `work_mem` 是每个查询的每个排序/哈希操作独立分配，高并发+复杂查询下总内存可能是 `work_mem × 并发数 × 每查询操作数`，容易 OOM | 报告中必须给出总内存占用的估算公式和上限提醒，倾向于保守值 + 允许单个复杂查询用 `SET work_mem` 临时调高 |
| 直接套用网上"万能参数模板" | 不同 workload（OLTP/OLAP）、不同硬件对同一参数的合理值可能相差数倍 | 严格要求 Step 5 每条建议都要能追溯回 Step 2/3/4 采集到的具体证据，拒绝无依据的经验数字 |
| 同机执行时误判为"远程" | `hostname -I` 在容器/多网卡环境下可能不直观 | 优先用 `pgrep -a kingbase` + 数据目录路径是否本地可读来判断，而不是单纯比较 IP |
| 云托管/金仓云数据库无法 SSH | 托管数据库通常没有主机访问权限，也可能限制部分参数 | 自动降级为"仅数据库连接权限"模式；参数建议里注明哪些参数在该云产品上可能需要通过控制台而非 `kingbase.conf` 修改 |

## 注意事项

- **只读原则**：本 skill 全程只执行只读采集（`SHOW`、`SELECT` 系统视图/统计视图），不执行任何写入、`ALTER SYSTEM`、重启、reload 等操作性命令。
- **不生成可执行脚本**：最终交付物只有 Markdown 分析报告，不生成 `.sql`/`.sh` 形式的落地变更脚本，避免被误执行到生产库。
- **密码安全**：密码只在当次会话内存中使用，不写入任何持久化文件、日志或最终报告；报告中的连接信息一律脱敏密码字段。
- **权限声明**：采集操作系统/存储/网络指标需要用户明确授权（同机执行或提供 SSH 方式）；未获授权时自动降级为纯数据库侧分析，并在报告中如实说明降级原因。
- **生产环境谨慎性**：诊断查询避免对大表做无限制全表扫描；`iostat`/`vmstat` 等命令仅做短时间采样（如 3~5 次），不做长时间轮询占用资源。
- **不做绝对化承诺**：报告中的"预期收益"是基于经验和采集数据的方向性预测，不是性能保证；建议用户在测试环境验证后再应用到生产。
- **官方文档**：性能调优相关章节参考 [性能调优指南](https://docs.kingbase.com.cn/cn/KES-V9R1C10/category/%E6%80%A7%E8%83%BD%E8%B0%83%E4%BC%98%E6%8C%87%E5%8D%97)（含[性能问题调优](https://docs.kingbase.com.cn/cn/KES-V9R1C10/perf/db-optimization/%E6%80%A7%E8%83%BD%E9%97%AE%E9%A2%98%E8%B0%83%E4%BC%98/%E6%80%A7%E8%83%BD%E8%B0%83%E4%BC%98%EF%BC%8C%E8%A7%A3%E5%86%B3%E6%80%A7%E8%83%BD%E9%97%AE%E9%A2%98)、[动态性能视图分类](https://docs.kingbase.com.cn/cn/KES-V9R1C10/perf/db-optimization/%E6%80%A7%E8%83%BD%E8%B0%83%E4%BC%98%E5%B7%A5%E5%85%B7/%E5%8A%A8%E6%80%81%E6%80%A7%E8%83%BD%E8%A7%86%E5%9B%BE/%E5%8A%A8%E6%80%81%E6%80%A7%E8%83%BD%E8%A7%86%E5%9B%BE%E5%88%86%E7%B1%BB)）；参数参考以 `SHOW config_file` 指向的 `kingbase.conf` 与 `pg_settings`/`sys_settings` 实际值及官方手册为准。
