---
name: kingbase-runtime-risk
description: "KingbaseES（金仓）高可用架构与运行时风险诊断专家技能。给定金仓实例连接信息（主机、端口、用户名、密码），对实例进行只读全面运行时风险扫描，覆盖事务回卷、序列回卷、冻结风暴、复制延迟（物理/逻辑槽）、WAL 异常与堆积、连接数耗尽、集群单点故障、大对象泄漏、统计信息过时等维度，输出按严重程度分级（🔴严重/🟠警告/🟡关注/🟢正常）的中文预警报告。触发场景包括但不限于：\"帮我评估一下这个金仓实例的运行时风险\"、\"金仓检查事务回卷/XID 回卷风险\"、\"金仓序列要用完了吗\"、\"金仓冻结风暴\"、\"金仓复制延迟检查\"、\"金仓逻辑复制槽是不是堆积了\"、\"金仓 WAL 堆积/归档失败排查\"、\"金仓连接数是不是要满了\"、\"金仓 too many connections\"、\"max_connections 告警\"、\"金仓连接池是不是耗尽了\"、\"金仓这套集群有没有单点故障\"、\"金仓大对象是不是泄漏了\"、\"sys_largeobject 太大了\"、\"金仓数据库年龄检查\"、\"金仓 autovacuum 是否正常\"、\"金仓统计信息是不是过时了\"、\"金仓执行计划突然变差\"、\"金仓优化器选错了执行计划\"、\"金仓为什么走了全表扫描\"、\"金仓 analyze 是不是没跑\"、\"金仓表多久没做 analyze 了\"。即使用户只说\"帮我看看这个金仓库有没有风险\"或提供了 KingbaseES 连接信息但未指明具体维度，也应触发本技能进行全面扫描。"
tags: [KingbaseES, 金仓, 运行时潜在风险分析, 连接数耗尽, 事务回卷, 序列回卷, 冻结风暴, 复制延迟, 逻辑复制槽推进延迟, 逻辑复制槽未激活, 归档日志异常, WAL堆积, 大对象泄露, 统计信息过时]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# KingbaseES（金仓）运行时风险诊断（kingbase-runtime-risk）

对一个 KingbaseES 实例做全维度只读运行时风险扫描：事务回卷、序列回卷、冻结风暴、
复制延迟、WAL 异常、连接数耗尽、集群单点故障、大对象泄漏、统计信息过时，
输出分级中文预警报告。

> KingbaseES 默认采用 **PG 兼容模式**：`pg_stat_activity` / `pg_stat_database` /
> `pg_stat_user_tables` / `pg_stat_progress_vacuum` / `pg_stat_archiver` /
> `pg_stat_wal_receiver` / `pg_stat_replication` / `pg_replication_slots` /
> `pg_sequence` / `pg_largeobject` / `pg_settings` 等视图与 PostgreSQL 12 高度一致，
> 本技能默认使用 `pg_*` 系列视图（与 PostgreSQL 版技能完全同构）；
> 同时 `sys_catalog` 下存在 `sys_stat_activity` / `sys_stat_database` /
> `sys_stat_user_tables` / `sys_stat_progress_vacuum` / `sys_stat_archiver` /
> `sys_stat_wal_receiver` / `sys_stat_replication` / `sys_replication_slots` /
> `sys_sequence` / `sys_largeobject` / `sys_settings` 等同义视图供 DBA 直接使用，
> 数据等价。**SQL 统计采集使用 `sys_stat_statements`**（金仓内置，位于 `public` 或
> `sys_catalog` schema，PG 12 风格列：`calls` / `total_exec_time` 等），
> 而非 PostgreSQL 的 `pg_stat_statements`——后者在金仓上不存在。

## 前置要求

- 客户端需要 `psql`（≥ 10，可用金仓自带的 ksql / sys_ksql，也可用任意 PG 客户端，
  实测 PostgreSQL 18 的 psql 可直接连接金仓 V9）或 Python `psycopg2` 驱动。
  第二部分序列检查依赖 `\gset` + `\if :{?var}` 条件判断语法，该语法在 psql 10 才引入，
  低版本客户端会报语法错误，需提示用户升级客户端（与目标数据库服务端版本无关）。
- 连接账号建议具备 `sys_monitor` 角色或超级用户权限（`pg_ls_waldir()` 等函数需要更高权限，
  权限不足时会自动优雅降级并在报告中注明"因权限不足跳过"，不会导致整体扫描失败）。
- **密码仅通过 `PGPASSWORD` 环境变量传递**，不接受用户以明文形式粘贴到会话记录中长期保留，
  不写入任何脚本文件、不打印到日志、不落盘。
- 本技能全程只读：所有查询均包裹在 `SET TRANSACTION READ ONLY` 的只读事务中执行
  （金仓 V9 实测：只读事务内执行 DML 与 DDL（含超级用户）都会被服务端拒绝；
  注意不要误用 `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`，该语句只影响
  后续事务、不影响当前事务，请一律使用 `SET TRANSACTION READ ONLY`），
  不会对目标实例产生任何写操作。

## 连接约定

按优先级解析连接参数（本技能脚本已内置该逻辑，无需手工逐项传递）：

1. 用户明确提供的连接参数（host/port/user/password/dbname）；
2. 环境变量 `PGHOST` `PGPORT` `PGUSER` `PGPASSWORD` `PGDATABASE`（`PGDBNAME` 作为
   `PGDATABASE` 的等价别名同样被识别；KingbaseES 手册可能把这些变量写作
   `KINGBASEHOST` / `KINGBASE_PORT` 等，本技能**统一沿用 PG 风格环境变量**）；
3. 缺省值：`PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGPASSWORD=123456
   PGDBNAME=kingbase`（金仓默认安装即创建 `kingbase` 库，不保证存在 `postgres` 库，
   因此不要硬编码 `postgres`）。

## 工作流程

### Step 0：获取连接信息

向用户确认：主机（host）、端口（port，默认 5432）、用户名（user）、密码、
目标数据库（database，默认 kingbase，若实例有多个业务库，事务回卷等检查需遍历所有库）。
若用户未提供，按上面"连接约定"的优先级自动解析。

密码通过环境变量传递，例如：

```bash
export PGPASSWORD='xxxxxx'
```

不要将密码写入任何会保存的文件或命令历史。

### Step 1：执行只读扫描

调用 `scripts/run_scan.sh`（psql 版，任选其一即可；也可用 `scripts/run_scan.py`
Python SDK 版，两者输出完全一致）：

```bash
PGPASSWORD='xxxxxx' bash scripts/run_scan.sh -h <host> -p <port> -U <user> -d <database> -o <output_dir>
# 或等价地仅靠环境变量/默认值：
PGPASSWORD='xxxxxx' bash scripts/run_scan.sh
# Python SDK 版：
PGPASSWORD='xxxxxx' python3 scripts/run_scan.py -h <host> -p <port> -U <user> -d <database> -o <output_dir>
```

该脚本会自动完成：

- 第零部分：版本、启动时间、运行角色、关键参数、复制槽、WAL 接收状态
- 第一部分：数据库/表级 XID 年龄、autovacuum freeze 进度
- 第二部分：所有非循环序列的剩余调用次数与风险等级（psql 版通过 `\gset` + 动态 SQL
  在只读事务内一次性计算；Python 版通过 psycopg2 枚举序列并计算，Agent 无需再做算术）
- 第三部分：冻结风暴分桶统计
- 第四部分：物理复制延迟、逻辑复制槽状态
- 第五部分：归档状态、WAL 目录堆积统计
- 第六部分：连接数占用总览、按数据库/用户拆分、长时间 idle in transaction 明细
- 第八部分：大对象总量与疑似引用列
- 第九部分：全表统计信息新鲜度（`n_mod_since_analyze` 占触发阈值比例）、
  从未分析过的表清单

脚本对每个检查项都做了权限/版本容错：若某项因权限不足或函数不存在而失败，
会在对应 `<file>.csv.err` 中留痕，并在标准错误输出提示，视为正常的优雅降级，
**不代表整体扫描失败**，继续处理其余项即可。

### Step 2：解读结果并分级

逐个读取 `<output_dir>/` 下的 CSV 文件，对照 `references/thresholds.md` 中
每个维度的分级阈值表进行判定。重点：

1. **事务回卷**：先看 `01_database_xid_age.csv` 找出年龄最高的库，
   再结合 `01_table_xid_age_top20.csv` 定位阻碍该库年龄下降的具体表；
   若已进入警告区间，检查 `01_vacuum_progress.csv` 判断当前是否有 autovacuum
   worker 正在处理、能否在回卷前完成。
2. **序列回卷**：`02_sequence_risk.csv` 已直接给出 `risk_level` 列，
   按严重程度倒序整理；对 `data_type` 为 `integer`/`smallint` 且风险等级较高的，
   建议改为 `bigserial`（可用 `references/manual_checks.sql` 中的 A4 查询二次确认）。
3. **冻结风暴**：`03_freeze_storm_buckets.csv` 中若年龄较高的分桶集中了
   过半的表数量或表体积，判定为高风险，并结合 `00_key_settings.csv` 中
   `autovacuum_freeze_max_age` 给出参数调整建议。
4. **复制延迟**：`04_physical_replication.csv` 按物理延迟阈值判定；
   `04_logical_slots.csv` 需特别关注 `active=false` 的槽（WAL 无限堆积风险）
   以及有槽无消费进程的情况。
5. **WAL 异常**：先用 `00_key_settings.csv` 判断 `archive_mode`/`archive_command`
   是否为有效配置，排除主动关闭归档的情况后再用 `05_archiver_status.csv`
   判定归档失败/滞后；`05_wal_dir.csv` 的堆积量按 thresholds.md 中的
   根因排查顺序（复制延迟 → 槽推进延迟 → 槽未激活 → 槽未消费 → 归档失败 → 未知）
   逐层归因，输出根因分析表。
6. **连接数耗尽**：`06_connection_saturation.csv` 的 `usage_pct` 是主判据；
   若 `idle_in_tx_count`（含 aborted）占比偏高，即使 usage_pct 未达告警线也需单独标注，
   并提示这类长事务会同时加剧"事务回卷"与"冻结风暴"风险（阻塞 autovacuum 推进）；
   结合 `06_connection_by_database.csv` / `06_connection_by_user.csv` 定位是哪个库/账号
   占用了大部分连接；`06_long_idle_in_transaction.csv` 中 `idle_duration` 过长的记录需
   在报告中列出具体 pid，并在 (B) 部分给出 `sys_terminate_backend`/`pg_terminate_backend`
   建议命令（需用户确认）。
7. **集群单点故障**：本项无法仅靠单节点只读查询完成，见 Step 3。
8. **大对象泄漏**：`08_large_object_summary.csv` 按体积判级；
   `08_lo_reference_columns.csv` 列出候选引用列供人工核对，
   不给出任何自动清理结论。
9. **统计信息过时**：`09_stats_staleness.csv` 的 `pct_of_trigger` 是主判据，
   按 `references/thresholds.md` 第 9 节分级；先看 `never_analyzed_flag` 和
   `09_never_analyzed.csv`，非空大表（`n_live_tup > 0`）直接判 🔴；再看
   `autovacuum_enabled` 是否为 `false`（业务方主动关闭，不能仅凭 `last_autoanalyze`
   久远就判定异常）；`dead_tuple_pct` 与统计过时叠加时需在报告中标注"双重风险"
   并建议 `VACUUM ANALYZE` 而非单独 `ANALYZE`。若用户能提供具体慢查询，
   可在 Step 4 做执行计划验证。

### Step 3：集群单点故障 —— 主动向用户提问

在处理到第七部分时，必须暂停并向用户提问，因为单点风险评估依赖集群全局拓扑信息，
仅凭当前主库无法完整判断：

> 集群单点故障风险评估需要了解整个集群的拓扑结构。请提供：
> 1. 集群架构描述（如：1 主 2 备，是否使用金仓 HA 集群 / RWC 读写分离集群 /
>    共享存储集群，或 Patroni/Repmgr 等高可用方案）
> 2. 是否使用了连接池（如 PgBouncer/KBProxys），其部署是否为单节点
> 3. 是否使用了 VIP/负载均衡器（如 HAProxy/Keepalived），其部署是否为单节点
> 4. 最近一次有效备份的时间与类型（全量/增量）

如无法提供全部信息，将仅基于当前主库的复制拓扑（`04_physical_replication.csv`、
`references/manual_checks.sql` 中 A1/A2/A3）做有限的单点风险评估。

拿到回答后，结合 `references/manual_checks.sql` 中的 A1（同步备库数量）、
A2（`synchronous_standby_names` 配置）、A3（`synchronous_commit` 取值）
按 `references/thresholds.md` 第 7 节的判定表输出单点故障风险矩阵
（组件 / 当前状态 / 是否为单点 / 故障影响 / 风险等级）。

### Step 4（可选）：统计信息过时的执行计划验证

若第九部分识别出的 🔴/🟠 表是高频访问表，且用户能提供该表上的具体慢查询，
可进一步验证统计信息过时是否已经实际影响执行计划：

1. 先用 `references/manual_checks.sql` 中的 A5 确认 `sys_stat_statements` 是否已启用
   （金仓内置扩展，需在 `shared_preload_libraries` 中加载；用于后续更系统地定位
   劣化查询，非本次验证的硬性前提）。
2. 请用户提供具体 SQL，在只读事务中执行 `EXPLAIN (ANALYZE, BUFFERS) <用户的 SQL>;`
   （注意：若该 SQL 本身是 DML，只能取其只读的等价 SELECT 部分分析，不得直接对
   DML 语句做 ANALYZE 执行，因为 `EXPLAIN ANALYZE` 会真实执行语句）。
3. 对比输出中的 `rows=`（估算）与 `actual rows=`（实际）：若相差达到数量级
   （如估算 1000、实际 5 万+），且出现非预期的 `Seq Scan` 或 `Nested Loop`，
   基本可判定是统计信息过时导致优化器选择了错误的执行计划。
4. 结论写入报告对应表格的"影响描述"字段，作为该表 🔴/🟠 判级的佐证。

本步骤依赖用户提供具体查询语句，若用户无法提供，可跳过，仅保留 Step 2 中
基于 `pct_of_trigger` 的统计判断。

### Step 5：生成最终报告

按 `references/report_template.md` 的结构输出完整中文报告，包含：
风险总览仪表盘、🔴/🟠/🟡 分级明细（含具体修复建议与预估处理时间）、
🟢 检查通过项、十一维度风险雷达图（文字版进度条）、后续巡检与监控建议。

## 输出格式

严格遵循 `references/report_template.md`。修复建议中涉及破坏性操作
（删除复制槽、清理大对象、手动 VACUUM FREEZE、修改 `autovacuum_freeze_max_age` 等）
一律使用 `references/manual_checks.sql` 中 (B) 部分的模板，明确标注
"仅供参考，执行前请与用户二次确认"，**不得自动执行**。

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|---|---|
| `pg_ls_waldir()` 报权限不足 | 属预期内降级：在报告中注明"需 sys_monitor 角色或超级用户权限，本次跳过 WAL 目录堆积检查"，其余检查照常输出 |
| 序列数量很多导致动态 SQL 结果集很大 | 两个脚本已在 SQL/程序层完成分级计算，Agent 只需按 `risk_level` 排序摘取 🔴/🟠 项展示，避免把全部序列都塞进最终报告 |
| 多数据库实例，事务回卷需遍历所有库 | `01_database_xid_age.csv` 已按 `pg_database` 全库输出；若需要对非当前连接库做表级年龄分析（`01_table_xid_age_top20.csv`），需针对该库重新指定 `-d <database>` 执行一次扫描，因为表级目录信息只能在连接到目标库后查询 |
| 金仓内置 schema（sys_catalog/sys_hm/sysmac/sysaudit/src_restrict 等）的表/序列/索引混入结果 | 扫描 SQL 已通过 `n.nspname NOT IN (...)` 过滤金仓内置 schema，只聚焦用户业务对象；如需审计内置 schema 请人工复核 |
| 把 `pg_stat_statements` 当作金仓的 SQL 统计视图 | 金仓没有 `pg_stat_statements`，应使用 `sys_stat_statements`（金仓内置，PG 12 风格列），且需确认 `shared_preload_libraries` 已加载 |
| 密码误粘贴进对话记录 | 提醒用户后续修改该账号密码；本技能本身不会将密码写入任何持久化文件 |
| 用户要求直接执行破坏性修复命令 | 展示 (B) 类模板并明确询问"是否确认执行"，得到明确肯定答复后才可代为执行，且执行前建议用户自行备份 |
| 逻辑复制槽 `active=false` 但用户表示是刻意保留 | 不要自动建议删除，只做风险提示，是否清理完全由用户决定 |
| 连接数 usage_pct 很高，但大量是 PgBouncer/连接池的常驻连接 | 先确认是否使用了外部连接池；数据库侧看到的是池到库的连接数，不等于应用侧真实并发，报告中需注明口径，避免误判为"应用连接暴涨" |
| 想直接 `pg_terminate_backend` 杀掉长 idle-in-transaction 连接 | 属于破坏性操作，只能在 (B) 部分给出建议命令，需用户明确确认具体 pid 后才可执行，且要提醒该连接可能持有未提交事务，终止会导致其回滚 |
| 表的 `autovacuum_enabled=false` 但 `last_autoanalyze` 很久远 | 不要直接判 🔴：先检查是否为业务方主动配置的归档/只读历史表，只有确认表仍在写入且需要统计信息新鲜时才建议 `ALTER TABLE ... RESET (autovacuum_enabled)` |
| 用户想直接对疑似统计过时的表执行 `EXPLAIN ANALYZE` 验证 | `EXPLAIN ANALYZE` 会真实执行该 SQL；若原语句是 DML（INSERT/UPDATE/DELETE），必须提醒用户这不是只读操作，只能分析其只读的等价查询部分，不能直接对 DML 做该验证 |
| `sys_stat_statements` 未启用导致无法追溯历史慢查询 | 不强制要求启用；提示用户如需更系统地定位劣化 SQL 可在 `shared_preload_libraries` 中加入 `sys_stat_statements` 后重启实例，本次仅基于用户提供的具体查询做验证 |

## 注意事项

- 全程只读：使用 `SET TRANSACTION READ ONLY` 包裹所有查询（实测金仓只读事务
  同时拒绝 DML 与 DDL）。
- 凭据只通过 `PGPASSWORD` 环境变量传递，不落盘、不写日志。
- 涉及删除复制槽、清理大对象、修改系统参数等破坏性操作，只以"建议命令"形式给出，
  必须经用户二次确认后才能执行，且执行前建议做好备份。
- 集群单点故障评估依赖用户提供的拓扑信息，缺失信息时明确告知"本次为有限评估"。
- 输出语言统一为中文。
- 参考官方文档入口：[KingbaseES V9 产品手册](https://docs.kingbase.com.cn/cn/KES-V9R1C10/introduction/)
  （性能监控与系统视图章节可在手册内检索 `sys_stat_statements`、`sys_stat_activity` 等）。
