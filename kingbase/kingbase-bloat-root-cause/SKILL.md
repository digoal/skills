---
name: kingbase-bloat-root-cause
description: "KingbaseES（金仓）表/索引膨胀根因诊断专家。当用户提供 KingbaseES 实例连接信息（主机、端口、用户名、密码）并希望排查表膨胀、索引膨胀、死元组过多、autovacuum 不生效、vacuum 卡住等问题时触发。KingbaseES 默认采用 PG 兼容模式，因此与 PostgreSQL 共享大量 `pg_stat_*` / `pg_catalog` 视图，但 KingbaseES 提供了独有的在线压缩扩展 `sys_squeeze`（基于逻辑解码，类比 pg_squeeze）、`sys_repack` 命令行工具以及 `sys_spacequota` 磁盘配额，因此修复手段比 PG 更丰富。关键词包括：金仓表膨胀、金仓索引膨胀、膨胀根因、为什么会膨胀、死元组、dead tuple、autovacuum 没生效、vacuum 不清理、空间不回收、bloat、2PC 未提交事务、长事务导致膨胀、复制槽延迟、备库反馈膨胀、磁盘空间异常增长排查、sys_squeeze 怎么用、sys_repack 怎么用。即使用户只说'帮我看看金仓库为什么这么大'或'这张表怎么一直变大'，只要涉及 KingbaseES 实例且怀疑膨胀，也应使用本 skill。本 skill 强调因果链分析而非仅报告膨胀数值：必须把膨胀数据与长事务、未提交 2PC 事务、长查询快照、复制槽延迟、备库 hot_standby_feedback 等根因逐一关联，给出可执行的诊断报告和只读安全的修复建议（包含 KingbaseES 特有的 sys_squeeze/sys_repack 在线压缩选项）。"
tags: [KingbaseES, 金仓, 表膨胀, 索引膨胀, 膨胀潜在隐患, sys_squeeze, sys_repack]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# KingbaseES 膨胀根因诊断（kingbase-bloat-root-cause）

深入诊断 KingbaseES（金仓）表/索引膨胀的**根本原因**，而不只是报告膨胀量。将膨胀现象与长事务、未结束的 2PC 事务、长时间运行的查询、复制槽延迟、备库 hot_standby_feedback 等阻塞 vacuum 的机制建立因果链，最终产出一份可直接用于修复决策的诊断报告。KingbaseES 默认采用 PG 兼容模式，因此诊断方法与 PostgreSQL 高度相通；但 KingbaseES 提供了 `sys_squeeze` 扩展（基于逻辑解码的在线压缩）与 `sys_repack` 命令行工具（无需全程排他锁），修复选项比标准 PG 更丰富。

> KingbaseES 兼容性说明：
> - 默认采用 PG 12 兼容模式（`server_version_num` ≈ 120001），所有 `pg_stat_*` / `pg_catalog` 视图可用
> - 标准 PG 的 `pgstattuple` 扩展**不在** KingbaseES 默认扩展列表中，需要改用基于 `pg_stat_user_tables` + `pg_class.reltuples` / `pg_relation_size` 的**统计信息估算法**作为主手段；如需精确字节级数据，可临时安装 `pgstattuple` 的 kingbase 移植版本或使用 KingbaseES 特有的 `sys_recovery` 扩展读取死元组详情
> - KingbaseES 特有的在线压缩能力：`sys_squeeze` 扩展（依赖 `wal_level=logical` + `max_replication_slots≥1`，提供 `squeeze.squeeze_table()` 函数）与 `sys_repack` 命令行工具（无需逻辑解码，类比 pg_repack），均能在不完全锁表的情况下回收膨胀空间
> - KingbaseES 还提供 `sys_spacequota` 扩展用于设置表空间磁盘配额，配合本 skill 用于诊断"磁盘空间耗尽背后的膨胀"

## 前置要求

- 客户端需要能够访问目标 KingbaseES 实例（主机、端口、用户名、密码，以及可选的备库连接信息）。
- 推荐使用 `psql` 命令行工具执行只读查询（KingbaseES 同时提供 `ksql`，语法与 `psql` 兼容，但本环境可能仅有 `psql`）；未安装时按平台执行 `apt-get install -y postgresql-client` 或 `yum install -y postgresql`（KingbaseES 沿用 PG 客户端协议）。
- KingbaseES 默认**不包含** `pgstattuple` 扩展；本 skill 默认采用基于统计信息的估算方法（见 `references/bloat-estimation.sql`），数值标注为"估算值"。如需精确字节级死元组数据，可启用 KingbaseES 的 `sys_recovery` 扩展（`CREATE EXTENSION sys_recovery;`）或 `sys_squeeze`（需要先 `wal_level=logical` 且重启）。
- 部分视图（如 `pg_prepared_xacts`、`pg_stat_replication`）需要 superuser 或 KingbaseES 的 `MONITOR` 权限角色；权限不足时在报告中注明并给出授权命令，不中断整体分析。
- **不要将密码写入磁盘文件或提交到版本库**。运行 `psql` 时通过环境变量 `PGPASSWORD` 传递密码，仅在当前会话生效；`scripts/run_query.sh` 已按此方式封装。
- **连接参数解析优先级**（与本 skill 一致，与 `kingbase-awr-report` 一致）：
  1. 命令行 `-H/-p/-d/-U/-W` 或 `-c "<sql>"`
  2. PG 兼容环境变量 `PGHOST` / `PGPORT` / `PGDBNAME` / `PGUSER` / `PGPASSWORD`
  3. KingbaseES 专属环境变量 `KINGBASE_HOST` / `KINGBASE_PORT` / `KINGBASE_DB` / `KINGBASE_USER` / `KINGBASE_PASSWORD`
  4. 内置默认值：`127.0.0.1:5432, dbname=kingbase, user=kingbase, password=123456`（仅在没有以上任何环境变量时使用）
- 输出语言：中文。

## 工作流程

严格按以下四个阶段推进，每个阶段的产出都是下一阶段因果匹配的输入。所有查询语句集中在 `references/queries.sql`，按章节编号组织，需要哪一节就去查该文件对应编号，避免把全部 SQL 都塞进正文。

### 阶段一：环境信息采集

连接目标实例后，依次执行 `references/queries.sql` 中 `-- [ENV]` 标记的查询，采集：

1. KingbaseES 版本及编译信息（`SELECT version();`），确认是否 KES V8R6 / V9R1C10 等（PG 兼容模式在所有版本中均为默认）。
2. 实例角色：`SELECT pg_is_in_recovery();`——`true` 为备库，`false` 为主库。
3. 当前所有数据库及大小（`pg_database` + `pg_database_size`）。
4. autovacuum 相关参数：`autovacuum`、`autovacuum_vacuum_scale_factor`、`autovacuum_vacuum_threshold`、`autovacuum_vacuum_cost_delay`、`vacuum_defer_cleanup_age`、`idle_in_transaction_session_timeout`。
5. KingbaseES 特有的 `wal_level`、`max_replication_slots`（用于判断是否能启用 `sys_squeeze` 在线压缩）以及 `shared_preload_libraries`（确认 `sys_squeeze` / `sys_recovery` 是否已预加载）。
6. `hot_standby_feedback` 当前值——如果本实例是主库，记下此项，提示后续阶段需要向用户询问备库信息。

### 阶段二：膨胀隐患因果链排查

逐项排查以下 6 类根因，每一类都必须输出：**是否存在问题 / 严重程度（Critical / Warning / Info）/ 该问题如何导致膨胀**。对应查询见 `references/queries.sql` 中 `-- [CAUSE-n]` 标记。

**1. 长事务检测**
筛选 `pg_stat_activity` 中满足以下任一条件的会话：
- 状态非 `idle`，且事务开始时间距今 > 5 分钟；
- 状态为 `idle in transaction`，且事务开始时间距今 > 30 分钟。

输出字段：`pid`、`usename`、`application_name`、`client_addr`、`state`、`backend_start`、`xact_start`、`query`（截取前 200 字符）、已持续时长（分钟）。

因果说明：长事务会阻止 vacuum 清理其**开始之后**产生的死元组，即使 autovacuum 按时触发也无法回收——因为 vacuum 的可见性判断依赖于所有活跃事务中最老的快照（`xmin horizon`）。该长事务开始之后被 DML 操作过的所有表都在潜在受影响范围内。

**2. 未结束的 2PC 事务检测**
查询 `pg_prepared_xacts`，输出 `transaction`、`gid`、`prepared`、`owner`、`database`、已准备时长。**准备时长 > 15 分钟标记为 Critical**。

因果说明：2PC 事务一旦 `PREPARE` 但未 `COMMIT PREPARED`/`ROLLBACK PREPARED`，它持有的事务快照和锁会无限期存在，是最隐蔽、危害最大的膨胀根因——因为它不会出现在 `pg_stat_activity` 里，很容易被运维忽略。KingbaseES 完全沿用 PG 的 2PC 协议语义。

**3. 长时间运行的查询检测**
筛选 `pg_stat_activity` 中 `state = 'active'` 且 `now() - query_start > 10 分钟` 的查询，输出 `pid`、`usename`、`query_start`、`query`（截取）、已运行时长。重点标注查询目标表是否为高频 DML 表。

因果说明：无论隔离级别如何，运行时间很长的查询本身持有的快照会阻止其涉及表的死元组被回收，直到该查询结束。

**4. 复制槽延迟检测（主库上执行）**
查询 `pg_replication_slots`，输出 `slot_name`、`slot_type`、`active`、`restart_lsn`，并计算 `restart_lsn` 与当前 WAL 位置（`pg_current_wal_lsn()`）之间的差距（MB）。**`active = false` 的复制槽标记为 Critical**（不再被消费但持续阻止清理与保留 WAL）。

因果说明：复制槽的 `restart_lsn` 之前的资源被保留，同时该复制槽（尤其是逻辑复制槽）会将 vacuum 所需回收的 xmin 水位线钉在很旧的位置，是主库表/索引膨胀的常见成因。KingbaseES 的 `sys_squeeze` 自身**会占用一个复制槽**，因此若已启用 `sys_squeeze`，主库 `pg_replication_slots` 中应能看到一个 `slot_type='logical'` 的 squeeze 槽位——不要误判为残留垃圾。

**5. 备库反馈机制检测（需要用户配合）**
如果阶段一判定本实例为主库，**在此暂停并向用户提问**：

> 检测到本实例为主库，需要分析备库侧情况以判断 `hot_standby_feedback` 是否造成了膨胀。请提供备库的连接信息（主机、端口、用户名、密码），若备库不止一个请全部提供。如无法提供，将跳过此步骤并仅基于主库侧指标（如复制槽延迟）推断。

获得备库信息后，逐个连接备库执行：
- 查询备库 `pg_stat_activity`，筛选运行时长 > 5 分钟的长事务/长查询；
- 检查备库 `hot_standby_feedback` 参数值。

若备库 `hot_standby_feedback = on` 且存在上述长事务/长查询，判定为因果关联：备库的查询快照通过 feedback 机制回传主库，导致主库 vacuum 无法回收该快照之后产生的死元组。输出受影响备库的 `pid`、`usename`、`query`、`xact_start`/`query_start`、持续时长。

**6. 孤儿准备事务与失效复制槽的补充检查**
- 检查 `pg_prepared_xacts.gid` 中是否包含逻辑复制相关前缀（可能是逻辑复制初始化过程中残留的孤儿 2PC 事务）。
- 检查 `pg_replication_slots` 中 `active = false` 且 `slot_type = 'logical'` 的复制槽——这类槽可能永远不会被再次激活，但持续阻止清理。**注意**：`sys_squeeze` 启用后会在此处出现一个自身的 logical 槽位（通常 `slot_name` 含 `squeeze` 字样），不要误杀；如确认是 squeeze 已废弃但未清理的残留，再列入"建议删除"。

### 阶段三：实际膨胀数据采集与因果匹配

1. 遍历阶段一列出的每个数据库，使用 `references/bloat-estimation.sql` 中的统计信息估算方法（KingbaseES 默认无 `pgstattuple`），找出实际膨胀的表和索引。如已安装 KingbaseES 的 `sys_recovery` 扩展（`CREATE EXTENSION sys_recovery;`），可读取单个表的死元组详情；如计划使用 `sys_squeeze` 进行在线压缩，可在压缩完成后通过 `pg_relation_size` 对比前后体积差，得到精确回收量。
2. 对每个膨胀对象记录：库名、Schema 名、对象名（表/索引）、死元组数量、死元组占比、膨胀大小估算（MB）、最后一次 autovacuum/autoanalyze 时间。
3. 按以下优先级把膨胀对象与阶段二发现的根因匹配（一个对象可能匹配多个根因，全部列出）：
   - 存在长事务且其 `xact_start` 早于膨胀对象最后一次被清理之后的窗口 → 标记「长事务导致」；
   - 存在准备中的 2PC 事务 → 标记「2PC 未提交导致」；
   - 存在 `active=false` 或延迟严重的复制槽 → 标记「复制槽延迟导致」；
   - 备库存在长查询且 `hot_standby_feedback=on` → 标记「备库反馈导致」；
   - `autovacuum` 关闭、阈值过高，或长时间未触发 → 标记「autovacuum 配置不足」；
   - 以上均不匹配 → 标记「需进一步排查」。

### 阶段四：综合报告输出

按下方"输出格式"生成最终报告，不要跳过任何一个小节。

## 输出格式

```markdown
# KingbaseES 膨胀根因诊断报告

## 🛑 膨胀根因排序（按危害紧急度）
优先级固定为：未结束的 2PC > 复制槽失效 > 备库长查询反馈 > 长事务 > 长查询 > autovacuum 配置不足。
每条根因包含：类型 / 严重等级（Critical｜Warning｜Info）/ 影响范围（库.表清单）/ 发现来源（2PC gid｜事务 pid｜复制槽名｜备库查询 pid）/ 直接解决指令。

## 📊 膨胀详情表（按数据库分组）
| 库名 | 表名/索引名 | 死元组数 | 死元组占比(%) | 膨胀估算(MB) | 膨胀根因 | 风险等级 | 建议操作 |

## 📋 解决操作清单（可直接执行，需人工确认后执行）
```sql
-- 清理孤立的 2PC 事务
ROLLBACK PREPARED 'gid_xxx';

-- 终止指定的长事务/长查询
SELECT pg_terminate_backend(pid);

-- 删除失效的复制槽（确认无业务依赖后执行，注意区分 sys_squeeze 自身槽位）
SELECT pg_drop_replication_slot('slot_name');

-- 手动清理指定膨胀表
VACUUM (VERBOSE, ANALYZE) schema.table_name;

-- ===== KingbaseES 特有：在线压缩（sys_squeeze）=====
-- 1. 确认 wal_level=logical，max_replication_slots≥1，shared_preload_libraries 包含 sys_squeeze
-- 2. CREATE EXTENSION sys_squeeze;  -- 一次性安装
-- 3. SELECT squeeze.squeeze_table('schema_name', 'table_name');
--    该函数不全程加排他锁，业务低峰期执行效果最佳；
--    不支持复合类型表、不支持无主键/无唯一约束的表（必须有 IDENTITY INDEX），
--    需要约目标表 + 索引 + toast 总大小 1 倍的额外磁盘空间。

-- ===== KingbaseES 特有：sys_repack 命令行（无需逻辑解码）=====
-- sys_repack -h <host> -p <port> -U <user> -d <db> --table schema.table
-- 仅在切换 FILENODE 阶段持有非常短暂的排他锁，比 VACUUM FULL 影响小得多。
```
附：autovacuum 参数调整建议值及理由。

## ⏱️ 时间线总结
文字时间线：某时刻长事务/2PC/复制槽问题开始 → 期间哪些表发生了 DML → autovacuum 被阻塞的具体机制 → 膨胀累积至今的完整因果链。

## ⚠️ 执行前警告
- 终止后台进程、删除复制槽、回滚 2PC 事务均有业务风险，所有破坏性命令仅供人工复制执行，不由本次分析自动执行。
- 生产环境的 `VACUUM FULL` / `CLUSTER` / `squeeze.squeeze_table()` / `sys_repack` 等可能短暂加锁的操作，建议放在业务低峰期执行，并提前评估锁等待。
- KingbaseES 的 `sys_squeeze` 依赖逻辑解码，**启用前需评估主库 WAL 量增加**；`sys_repack` 不需要逻辑解码但需要服务器端部署 `sys_repack` 命令。
```

## Pitfalls & Solutions

| 坑点 | 现象 | 解决方案 |
|------|------|----------|
| 无 superuser / MONITOR 权限 | `pg_prepared_xacts`、`pg_stat_replication` 查询返回空或报错 | 报告中注明"权限不足，未能采集该项"，给出 `GRANT MONITOR TO <user>;` 提示（KingbaseES 使用 `MONITOR` 而非 PG 的 `pg_monitor`），其余部分正常输出 |
| `round(double, integer)` 不存在 | `function round(double precision, integer) does not exist` | KingbaseES 的 `round()` 只有 `(numeric, integer)` 重载，PG12 默认有 `(double, integer)`；把所有 `round(xxx / 60.0, 1)` 改为 `round((xxx / 60.0)::numeric, 1)`，本 skill 的 `references/queries.sql` 已统一处理 |
| `pg_stat_user_indexes.last_idx_scan` 不存在 | `column s.last_idx_scan does not exist` | KingbaseES 沿用 PG12 早期视图结构，无 `last_idx_scan`（PG13+ 已移除）；用 `idx_tup_read`/`idx_tup_fetch` 替代，本 skill 的 `references/bloat-estimation.sql` 已统一处理 |
| `max_prepared_transactions = 0`（默认） | `2pc are not enabled` 错误，调用 `PREPARE TRANSACTION` 失败；`[CAUSE-2]` 检测永远返回 0 行 | KingbaseES 默认关闭 2PC 支持；如需在 KingbaseES 上做涉及 2PC 的诊断/演练，需修改 `kingbase.conf` 中 `max_prepared_transactions = N`（N ≥ 1）后重启。如果目标库 2PC 关闭，应在报告"环境信息"章节明确标注"2PC 已被禁用，[CAUSE-2] 章节无需进一步排查"，并确认业务应用未使用分布式事务（XA） |
| 未安装 `pgstattuple`（KingbaseES 默认无） | `pgstattuple` 函数不存在 | 自动切换到 `references/bloat-estimation.sql` 中基于 `pg_stat_user_tables` / `pg_class` 统计信息的估算方法，并在报告中注明数值为"估算值"。如需精确数据，可启用 `sys_recovery` 扩展（`CREATE EXTENSION sys_recovery;`），或先 `CREATE EXTENSION sys_squeeze;` 然后对比压缩前后 `pg_relation_size` |
| 备库信息拿不到 | 用户无法提供备库连接信息 | 不阻塞流程，跳过阶段二第 5 项，仅基于主库侧复制槽延迟推断，并在报告中注明"备库反馈机制未验证" |
| 长事务与膨胀对象误匹配 | 长事务时间早于表膨胀产生窗口太多，强行归因不准确 | 只有当长事务 `xact_start` 早于目标表"最后一次成功 autovacuum 之后"时才判定为因果关联，否则归为"需进一步排查"，避免过度归因 |
| 密码泄露风险 | 直接把密码写进 SQL 脚本或 shell 历史 | 统一通过 `PGPASSWORD` 环境变量传递，禁止落盘；`scripts/run_query.sh` 已封装此逻辑 |
| 大库全量扫描膨胀太慢 | 对超大表跑 `sys_recovery` 或 `squeeze.squeeze_table` 导致长时间锁等待或高 IO | 优先用统计信息估算法做初筛，只对膨胀率明显异常（如死元组占比 > 20%）的对象再用精确方法核实；`sys_squeeze` / `sys_repack` 同样需要目标低峰期执行 |
| `sys_squeeze` 启用后被误判为残留 logical 槽 | 主库 `pg_replication_slots` 出现一个 `slot_type=logical` 的槽位，看似"孤儿" | 检查 `slot_name` 是否含 `squeeze` 字样、是否与 `CREATE EXTENSION sys_squeeze;` 同时存在；这是 `sys_squeeze` 自身的工作槽位，不应删除 |
| `sys_squeeze` 压缩失败"表无主键" | 调用 `squeeze.squeeze_table()` 报错要求 IDENTITY INDEX | 给目标表加主键或唯一约束后再压缩；若表确实无法加主键，改用 `sys_repack` 或 `VACUUM FULL`（需锁表许可） |

## 注意事项

- **只读约束**：所有诊断查询仅使用 `pg_catalog`、`information_schema`、`pg_stat_*` 视图及只读的扩展函数（`sys_recovery`、`sys_squeeze` 的只读视图），不修改任何数据或配置。
- **不自动执行破坏性操作**：不主动执行终止进程、删除复制槽、回滚/提交 2PC 事务、调用 `squeeze.squeeze_table()` 等操作，只在报告"解决操作清单"中给出精确命令，交由用户人工确认后自行执行。
- **权限声明**：部分视图需要 superuser 或 KingbaseES 的 `MONITOR` 角色，若目标账号权限不足，在报告中明确注明缺失项及授权命令（`GRANT MONITOR TO <user>;`），不影响其余部分的诊断结论。
- **主备关联分析依赖用户配合**：备库反馈机制排查（阶段二第 5 项）必须先暂停向用户索取备库连接信息，不能假设或跳过而不告知用户。
- **避免过度归因**：因果匹配需要满足时间先后逻辑（根因发生时间早于膨胀产生窗口）才能下结论，无法匹配时应诚实标注"需进一步排查"，不得为了报告完整性而牵强附会。
- **KingbaseES 特有修复手段优先级**：在修复建议中按"先回收活事务/复制槽，再 VACUUM（ANALYZE），最后才考虑 `squeeze.squeeze_table()` / `sys_repack` / `VACUUM FULL` 物理重写"——根因未解决时物理重写只能临时缓解，问题会复现。
- **输出语言为中文**，报告结构须完整覆盖"输出格式"中的五个小节，不可省略。