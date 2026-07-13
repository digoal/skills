---
name: pg-top-sql-analyze
description: "基于 pg_stat_statements 对 PostgreSQL 实例做两阶段快照采集与差值分析，找出总耗时、单次最慢、高频调用、IO消耗、WAL生成量、返回行数异常等多维度 TOP SQL，并给出索引/改写/批量化等具体优化建议与健康评分。触发场景包括：'帮我分析一下这个库的慢SQL'、'找TOP SQL'、'pg_stat_statements 分析'、'数据库性能诊断'、'哪些SQL最耗资源'、'帮我看看这个实例的负载画像'、'SQL优化建议'、'缓存命中率低怎么排查'、用户给出 PostgreSQL 连接信息（host/port/user/password/dbname）并希望做性能巡检或SQL调优时。即使用户只说'帮我看看这个库最近跑得怎么样'或'这些SQL要怎么优化'并提供了连接信息，也应使用本技能。"
tags: [PostgreSQL, TOP SQL, 瓶颈分析]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# PostgreSQL TOP SQL 性能分析师

基于 `pg_stat_statements` 扩展，对指定 PostgreSQL 实例做两次快照采集、计算增量差值，输出多维度 TOP SQL 排行榜与逐条优化建议，最终给出全局健康评分与负载画像。适用于生产巡检、上线前后对比、慢查询专项治理。

## 前置要求

- 一个可用的 psql 客户端（或等效的 SQL 执行通道）以及目标实例的连接信息：host、port、user、password、dbname。
- 目标实例已安装并启用 `pg_stat_statements` 扩展。
- 连接账号至少具备读取 `pg_stat_statements` 视图和执行 `pg_stat_statements_reset()`（若使用重置模式）的权限。
- 不缓存、不外传密码等连接凭据；凭据仅用于当次连接，不写入日志或输出报告。

## 工作流程

### Step 0：连接与前置条件检查

1. 使用给定连接信息连接目标库，执行 `scripts/00_precheck.sql` 完成以下检查：
   - `pg_stat_statements` 扩展是否已安装（查询 `pg_extension`）。
   - `pg_stat_statements.track` 是否为 `all`（查询 `pg_settings`）；若为 `top` 或 `none`，非 SELECT 语句可能采集不到。
   - PostgreSQL 主版本号（决定是否有 `total_plan_time` 字段，13 以下版本跳过计划时间分析）。
2. 若扩展未安装或未启用，**立即终止**，向用户输出：
   ```
   检测到 pg_stat_statements 未启用。请在目标库执行：
     1. postgresql.conf 中添加：shared_preload_libraries = 'pg_stat_statements'
     2. 重启实例后执行：CREATE EXTENSION pg_stat_statements;
     3. 建议同时设置：pg_stat_statements.track = 'all'
   完成后重新运行本次分析。
   ```
3. 若 `track` 不是 `all`，给出警告但可继续（非 SELECT 语句统计可能不完整），并在最终报告中注明此局限。

### Step 1：选择采集模式

主动询问用户使用哪种模式（默认推荐"差值模式"，因为不影响全局统计数据）：

| 模式 | 做法 | 适用场景 | 风险 |
|------|------|----------|------|
| **重置模式**（默认不用） | 采集 → `pg_stat_statements_reset()` → 等待 → 再采集 | 需要精确的"纯增量"数据，且能接受清空历史统计 | 会清空全局统计计数器，影响其他正在依赖这些统计的监控/分析，仅在非生产核心时段或用户明确授权后执行 |
| **差值模式**（推荐默认） | 采集快照1（不 reset）→ 等待 → 采集快照2 → 对 calls/total_exec_time/rows 等累计字段做差值 | 生产环境常规巡检，不希望影响其他监控 | 若采集间隔内发生了 reset 或语句因 `pg_stat_statements.max` 被淘汰，某些 queryid 的差值可能为负或缺失，需要识别并在报告中注明 |

- 使用重置模式前，**必须**输出醒目警告：「⚠️ 即将执行 pg_stat_statements_reset()，将清空该实例全局 SQL 统计历史，请确认已获得授权」，并等待用户确认后才可执行。
- 差值模式下，若发现快照2中某 queryid 的 calls/total_exec_time 小于快照1（说明期间发生过重置或该记录被淘汰后新生成），将该记录标记为「数据不连续，本次已剔除」，不纳入排行榜。

### Step 2：两阶段数据采集

1. 记录 `snapshot1_time`，执行 `scripts/01_snapshot.sql` 采集全量 `pg_stat_statements` 数据（含 references/collected_fields.md 中列出的全部字段）保存到上下文/临时表。
2. 重置模式：执行 `SELECT pg_stat_statements_reset();`；差值模式：跳过此步。
3. 输出提示：「快照 1 已采集（共 N 条 SQL 记录）。建议等待 **5-15 分钟**（覆盖一个完整业务波峰更佳）后进行第二次采集。」
   - 若用户要求"现在就采集"，可缩短等待，但需提醒采集时长过短会导致样本量不足、TOP排行代表性下降。
4. 到达约定时间后，记录 `snapshot2_time`，再次执行 `scripts/01_snapshot.sql` 采集数据。
5. 计算实际采集间隔 `interval = snapshot2_time - snapshot1_time`，在报告开头注明。

### Step 3：差值计算

对两次快照按 `queryid` 关联，计算：

- 重置模式：快照2的值即为增量值（因为计数器已清零）。
- 差值模式：`delta = snapshot2.value - snapshot1.value`，对 `calls`、`total_exec_time`、`total_plan_time`、`rows`、`shared_blks_hit`、`shared_blks_read`、`wal_bytes` 等累计字段逐一做差值；`mean_exec_time = delta.total_exec_time / delta.calls`（`delta.calls = 0` 时跳过该条，不计入任何排行）。
- 剔除 Step 1 中标记为「数据不连续」的记录。
- `userid` 转换为可读用户名（关联 `pg_authid` 或 `pg_user`）。
- `query` 字段截取前 500 字符用于展示；完整语句仅用于内部分析参数化改写。

### Step 4：多维度 TOP SQL 排序

基于差值数据，对以下 7 个维度各产出 TOP 10（每个维度独立成表，模板见 `references/report_template.md`）：

| 维度 | 排序依据 | 过滤条件 | 关注点 |
|------|----------|----------|--------|
| 总耗时 TOP | `total_exec_time` 降序 | 无 | 占用数据库时间最多，最值得优先优化 |
| 单次最慢 TOP | `mean_exec_time` 降序 | `calls >= 5` | 排除偶发的单次慢查询噪音，聚焦真实慢查询模式 |
| 执行频率 TOP | `calls` 降序 | 无 | 高频调用，单次快也易成瓶颈 |
| 总 IO 消耗 TOP | `shared_blks_read` 降序 | 无 | 磁盘读最多，缓存命中率低 |
| WAL 生成量 TOP | `wal_bytes` 降序 | 无 | 写入压力最大，识别高频 DML |
| 单次返回行数异常 TOP | `rows / calls` 降序 | `calls >= 1` | 疑似全表扫描返回大量行 |
| 总扫描行数 TOP | `rows` 降序 | 无 | 对数据库整体扫描压力最大 |

每张表列：排名、SQL 文本(截取)、用户名、执行次数、平均耗时(ms)、总耗时(ms)、缓存命中率(%)（`shared_blks_hit / (shared_blks_hit + shared_blks_read)`）、返回/影响总行数、WAL 生成量。

若目标版本 < PG13（无 `total_plan_time`），在总耗时表旁注明"本版本不支持计划时间拆分，total_exec_time 已含计划耗时"。

### Step 5：逐条优化建议（每维度 TOP 3）

对每个维度的 TOP 3 SQL，按 `references/diagnosis_playbook.md` 中的诊断框架逐一产出：

1. **SQL 可读化**：尝试将 `$1`、`$2` 等参数还原为示例值或类型占位（如 `$1::int`），无法还原则保留原文并说明。
2. **性能摘要**：一句话概括核心问题（如"平均执行 5.2 秒，缓存命中率仅 23%，calls=1200"）。
3. **问题诊断**：从 `references/diagnosis_playbook.md` 的 6 个方向逐一排查（缺索引 / 索引失效 / JOIN 不佳 / 子查询可改写 / 缺 LIMIT 分页 / 高频 DML 可合并），只列出实际命中的方向，不逐条罗列不相关项。
4. **具体建议**：给出可直接执行的 SQL（如 `CREATE INDEX idx_xxx ON table(user_id);`），建议须保守、兼容现有业务，避免破坏性改造（如禁止建议直接删除索引/表而不给回滚说明）。
5. **预估收益**：高 / 中 / 低，并说明判断依据（如"预计缓存命中率可从23%提升至90%以上，收益：高"）。

### Step 6：综合汇总

1. **健康评分（百分制）**：
   - 缓存命中率 30% + 平均执行时间合理性 30% + 全表扫描比例 20% + WAL 生成合理性 20%
   - 具体计分公式与分档标准见 `references/health_score.md`
2. **Top 3 最值得优化的 SQL**：合并 7 个维度中重复出现的高频项，给出最终优先级排序及理由。
3. **整体负载画像**：一句话总结（如"读密集型，Top SQL 中 60% 存在全表扫描"或"写入密集型，WAL 生成量集中在 3 条批量 UPDATE"）。

## 输出格式

完整报告结构模板见 `references/report_template.md`，整体分为：

1. 采集元信息（实例信息脱敏展示、采集模式、采集间隔、版本信息、track 设置提示）
2. 7 张 TOP SQL 排行表
3. 逐条优化建议（每维度 TOP 3，共最多 21 条，去重后合并展示）
4. 健康评分卡 + Top 3 优先级 + 负载画像
5. 附录：本次分析的局限性说明（如差值模式下被剔除的不连续记录数量）

输出语言为中文；报告中不得包含真实密码等连接凭据。

## Pitfalls & Solutions

| 坑点 | 现象 | 解决方案 |
|------|------|----------|
| track 未设为 all | UPDATE/INSERT/DELETE 未被统计 | Step 0 检测并警告，报告中注明可能存在遗漏 |
| 差值模式下计数器倒退 | 某 queryid 快照2值小于快照1 | 判定为期间发生过 reset 或语句被淘汰，剔除该条并在附录说明数量 |
| pg_stat_statements.max 太小 | 高频新查询挤出老查询，采样失真 | 报告中提示当前 `pg_stat_statements.max` 配置值，建议按需调大 |
| PG13 以下无 total_plan_time | 计划时间列为空或报错 | Step 0 检测版本，跳过计划时间相关分析并注明 |
| 采集间隔过短 | 样本量不足，TOP排行代表性差 | 建议至少 5-15 分钟，覆盖一次业务波峰 |
| query 文本被截断丢失关键 WHERE 条件 | 参数化 SQL 难以判断具体过滤列 | 结合 `pg_stat_statements.query` 全文（内部使用）+ `EXPLAIN`（如用户授权）辅助判断，仍无法确定则如实说明"需要结合执行计划进一步确认" |
| 重置模式误清空监控依赖的统计 | 其他监控系统数据丢失 | 执行前必须走"醒目警告 + 用户确认"，默认引导使用差值模式 |

## 注意事项

- `pg_stat_statements_reset()` 属于高风险操作，仅在用户明确授权后执行；默认使用差值模式。
- 连接凭据（尤其密码）不写入最终报告、不记录到 `references/` 或 `scripts/` 之外的任何持久化文件。
- 所有优化建议须遵循 PostgreSQL 最佳实践，避免激进的、可能破坏兼容性的改造建议（如不建议盲目删除现有索引）。
- 高危 DDL 类建议（如建索引）应提示"建议先在测试环境或低峰期执行，大表建索引可加 `CONCURRENTLY`"。
- 若目标是云数据库托管实例（如 RDS for PostgreSQL），`pg_stat_statements_reset()` 权限可能受限，需提示用户改用差值模式或联系云厂商支持。
