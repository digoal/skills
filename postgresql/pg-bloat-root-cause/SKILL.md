---
name: pg-bloat-root-cause
description: "PostgreSQL 表/索引膨胀根因诊断专家。当用户提供 PostgreSQL 实例连接信息（主机、端口、用户名、密码）并希望排查表膨胀、索引膨胀、死元组过多、autovacuum 不生效、vacuum 卡住等问题时触发。关键词包括：'表膨胀'、'索引膨胀'、'膨胀根因'、'为什么会膨胀'、'死元组'、'dead tuple'、'autovacuum 没生效'、'vacuum 不清理'、'空间不回收'、'bloat'、'2PC 未提交事务'、'长事务导致膨胀'、'复制槽延迟'、'hot_standby_feedback'、'备库反馈膨胀'、'磁盘空间异常增长排查'。即使用户只说'帮我看看这个库为什么这么大'或'这张表怎么一直变大'，只要涉及 PostgreSQL 实例且怀疑膨胀，也应使用本 skill。本 skill 强调因果链分析而非仅报告膨胀数值：必须把膨胀数据与长事务、未提交 2PC 事务、长查询快照、复制槽延迟、备库 hot_standby_feedback 等根因逐一关联，给出可执行的诊断报告和只读安全的修复建议。"
tags: [PostgreSQL, 表膨胀, 索引膨胀, 膨胀潜在隐患]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# PostgreSQL 膨胀根因诊断（pg-bloat-root-cause）

深入诊断 PostgreSQL 表/索引膨胀的**根本原因**，而不只是报告膨胀量。将膨胀现象与长事务、未结束的 2PC 事务、长时间运行的查询、复制槽延迟、备库 hot_standby_feedback 等阻塞 vacuum 的机制建立因果链，最终产出一份可直接用于修复决策的诊断报告。

## 前置要求

- 客户端需要能够访问目标 PostgreSQL 实例（主机、端口、用户名、密码，以及可选的备库连接信息）。
- 推荐使用 `psql` 命令行工具执行只读查询；如果目标环境已安装 `psql`，直接调用；未安装时按平台执行 `apt-get install -y postgresql-client` 或 `yum install -y postgresql`（如为 Anolis/RHEL 系）。
- 若需要精确膨胀大小（而非估算值），目标库需安装 `pgstattuple` 扩展（`CREATE EXTENSION IF NOT EXISTS pgstattuple;`）；无权限安装时自动降级为基于统计信息的估算方法（见 `references/bloat-estimation.sql`）。
- 部分视图（如 `pg_prepared_xacts`、`pg_stat_replication`）需要 superuser 或 `pg_monitor` 角色权限，权限不足时在报告中注明并给出授权命令，不中断整体分析。
- **不要将密码写入磁盘文件或提交到版本库**。运行 `psql` 时通过环境变量 `PGPASSWORD` 传递密码，仅在当前会话生效；`scripts/run_query.sh` 已按此方式封装。
- 输出语言：中文。

## 工作流程

严格按以下四个阶段推进，每个阶段的产出都是下一阶段因果匹配的输入。所有查询语句集中在 `references/queries.sql`，按章节编号组织，需要哪一节就去查该文件对应编号，避免把全部 SQL 都塞进正文。

### 阶段一：环境信息采集

连接目标实例后，依次执行 `references/queries.sql` 中 `-- [ENV]` 标记的查询，采集：

1. PostgreSQL 版本及编译信息（`SELECT version();`）。
2. 实例角色：`SELECT pg_is_in_recovery();`——`true` 为备库，`false` 为主库。
3. 当前所有数据库及大小（`pg_database` + `pg_database_size`）。
4. autovacuum 相关参数：`autovacuum`、`autovacuum_vacuum_scale_factor`、`autovacuum_vacuum_threshold`、`autovacuum_vacuum_cost_delay`、`vacuum_defer_cleanup_age`、`idle_in_transaction_session_timeout`。
5. `hot_standby_feedback` 当前值——如果本实例是主库，记下此项，提示后续阶段需要向用户询问备库信息。

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

因果说明：2PC 事务一旦 `PREPARE` 但未 `COMMIT PREPARED`/`ROLLBACK PREPARED`，它持有的事务快照和锁会无限期存在，是最隐蔽、危害最大的膨胀根因——因为它不会出现在 `pg_stat_activity` 里，很容易被运维忽略。

**3. 长时间运行的查询检测**
筛选 `pg_stat_activity` 中 `state = 'active'` 且 `now() - query_start > 10 分钟` 的查询，输出 `pid`、`usename`、`query_start`、`query`（截取）、已运行时长。重点标注查询目标表是否为高频 DML 表。

因果说明：无论隔离级别如何，运行时间很长的查询本身持有的快照会阻止其涉及表的死元组被回收，直到该查询结束。

**4. 复制槽延迟检测（主库上执行）**
查询 `pg_replication_slots`，输出 `slot_name`、`slot_type`、`active`、`restart_lsn`，并计算 `restart_lsn` 与当前 WAL 位置（`pg_current_wal_lsn()`）之间的差距（MB）。**`active = false` 的复制槽标记为 Critical**（不再被消费但持续阻止清理与保留 WAL）。

因果说明：复制槽的 `restart_lsn` 之前的资源被保留，同时该复制槽（尤其是逻辑复制槽）会将 vacuum 所需回收的 xmin 水位线钉在很旧的位置，是主库表/索引膨胀的常见成因。

**5. 备库反馈机制检测（需要用户配合）**
如果阶段一判定本实例为主库，**在此暂停并向用户提问**：

> 检测到本实例为主库，需要分析备库侧情况以判断 `hot_standby_feedback` 是否造成了膨胀。请提供备库的连接信息（主机、端口、用户名、密码），若备库不止一个请全部提供。如无法提供，将跳过此步骤并仅基于主库侧指标（如复制槽延迟）推断。

获得备库信息后，逐个连接备库执行：
- 查询备库 `pg_stat_activity`，筛选运行时长 > 5 分钟的长事务/长查询；
- 检查备库 `hot_standby_feedback` 参数值。

若备库 `hot_standby_feedback = on` 且存在上述长事务/长查询，判定为因果关联：备库的查询快照通过 feedback 机制回传主库，导致主库 vacuum 无法回收该快照之后产生的死元组。输出受影响备库的 `pid`、`usename`、`query`、`xact_start`/`query_start`、持续时长。

**6. 孤儿准备事务与失效复制槽的补充检查**
- 检查 `pg_prepared_xacts.gid` 中是否包含逻辑复制相关前缀（可能是逻辑复制初始化过程中残留的孤儿 2PC 事务）。
- 检查 `pg_replication_slots` 中 `active = false` 且 `slot_type = 'logical'` 的复制槽——这类槽可能永远不会被再次激活，但持续阻止清理。

### 阶段三：实际膨胀数据采集与因果匹配

1. 遍历阶段一列出的每个数据库，使用 `pgstattuple`（若已安装）或 `references/bloat-estimation.sql` 中的统计信息估算方法，找出实际膨胀的表和索引。
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
# PostgreSQL 膨胀根因诊断报告

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
-- 删除失效的复制槽（确认无业务依赖后执行）
SELECT pg_drop_replication_slot('slot_name');
-- 手动清理指定膨胀表
VACUUM (VERBOSE, ANALYZE) schema.table_name;
```
附：autovacuum 参数调整建议值及理由。

## ⏱️ 时间线总结
文字时间线：某时刻长事务/2PC/复制槽问题开始 → 期间哪些表发生了 DML → autovacuum 被阻塞的具体机制 → 膨胀累积至今的完整因果链。

## ⚠️ 执行前警告
- 终止后台进程、删除复制槽、回滚 2PC 事务均有业务风险，所有破坏性命令仅供人工复制执行，不由本次分析自动执行。
- 生产环境的 `VACUUM FULL`/`CLUSTER` 等会加排他锁的操作，建议放在业务低峰期执行，并提前评估锁等待。
```

## Pitfalls & Solutions

| 坑点 | 现象 | 解决方案 |
|------|------|----------|
| 无 superuser 权限 | `pg_prepared_xacts`、`pg_stat_replication` 查询返回空或报错 | 报告中注明"权限不足，未能采集该项"，给出 `GRANT pg_monitor TO <user>;` 提示，其余部分正常输出 |
| 未安装 pgstattuple | 精确膨胀查询报错 `function pgstattuple does not exist` | 自动切换到 `references/bloat-estimation.sql` 中基于 `pg_stat_user_tables`/`pg_class` 统计信息的估算方法，并在报告中注明数值为"估算值"而非精确值 |
| 备库信息拿不到 | 用户无法提供备库连接信息 | 不阻塞流程，跳过阶段二第 5 项，仅基于主库侧复制槽延迟推断，并在报告中注明"备库反馈机制未验证" |
| 长事务与膨胀对象误匹配 | 长事务时间早于表膨胀产生窗口太多，强行归因不准确 | 只有当长事务 `xact_start` 早于目标表"最后一次成功 autovacuum 之后"时才判定为因果关联，否则归为"需进一步排查"，避免过度归因 |
| 密码泄露风险 | 直接把密码写进 SQL 脚本或 shell 历史 | 统一通过 `PGPASSWORD` 环境变量传递，禁止落盘；`scripts/run_query.sh` 已封装此逻辑 |
| 大库全量扫描膨胀太慢 | 对超大表跑 `pgstattuple` 导致长时间锁等待或高 IO | 优先用统计信息估算法做初筛，只对膨胀率明显异常（如死元组占比 > 20%）的对象再用 `pgstattuple` 精确核实 |

## 注意事项

- **只读约束**：所有诊断查询仅使用 `pg_catalog`、`information_schema`、`pg_stat_*` 视图及只读的 `pgstattuple` 函数，不修改任何数据或配置。
- **不自动执行破坏性操作**：不主动执行终止进程、删除复制槽、回滚/提交 2PC 事务等操作，只在报告"解决操作清单"中给出精确命令，交由用户人工确认后自行执行。
- **权限声明**：部分视图需要 superuser 或 `pg_monitor` 角色，若目标账号权限不足，在报告中明确注明缺失项及授权命令，不影响其余部分的诊断结论。
- **主备关联分析依赖用户配合**：备库反馈机制排查（阶段二第 5 项）必须先暂停向用户索取备库连接信息，不能假设或跳过而不告知用户。
- **避免过度归因**：因果匹配需要满足时间先后逻辑（根因发生时间早于膨胀产生窗口）才能下结论，无法匹配时应诚实标注"需进一步排查"，不得为了报告完整性而牵强附会。
- **输出语言为中文**，报告结构须完整覆盖"输出格式"中的五个小节，不可省略。
