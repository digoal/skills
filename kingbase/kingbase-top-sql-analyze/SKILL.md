---
name: kingbase-top-sql-analyze
description: "基于 sys_stat_statements 对 KingbaseES（金仓）实例做两阶段快照采集与差值分析，找出总耗时、单次最慢、高频调用、IO消耗、写放大、返回行数异常等多维度 TOP SQL，并给出索引/改写/批量化等具体优化建议与健康评分。触发场景包括：'帮我分析一下这个金仓库的慢SQL'、'金仓找TOP SQL'、'sys_stat_statements 分析'、'KingbaseES 性能诊断'、'哪些SQL最耗资源'、'帮我看看这个金仓实例的负载画像'、'SQL优化建议'、'缓存命中率低怎么排查'、'金仓 TOP SQL'、'kingbase top sql'、用户给出 KingbaseES 连接信息（host/port/user/password/dbname）并希望做性能巡检或SQL调优时。即使用户只说'帮我看看这个金仓库最近跑得怎么样'或'这些SQL要怎么优化'并提供了连接信息，也应使用本技能。KingbaseES 默认采用 PG 兼容模式（database_mode=pg），但 TOP SQL 取数视图是 public.sys_stat_statements 而非 pg_stat_statements，且 KES V9R1C10 无 wal_bytes 字段，写放大用 shared_blks_dirtied 等字段替代。"
tags: [KingbaseES, 金仓, TOP SQL, 瓶颈分析, sys_stat_statements]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# KingbaseES TOP SQL 性能分析师

基于 `sys_stat_statements` 扩展，对指定 KingbaseES（金仓）实例做两次快照采集、计算增量差值，输出多维度 TOP SQL 排行榜与逐条优化建议，最终给出全局健康评分与负载画像。适用于生产巡检、上线前后对比、慢查询专项治理。

## 与 PostgreSQL 的关键差异（务必先读）

KingbaseES 默认采用 PG 兼容模式（`database_mode=pg`），绝大多数 SQL/视图与 PostgreSQL 一致，但以下差异必须显式处理：

| 差异点 | PostgreSQL | KingbaseES（KES V9R1C10） |
|---|---|---|
| 慢 SQL 统计视图 | `pg_catalog.pg_stat_statements` | **`public.sys_stat_statements`**（作为扩展安装在 public schema） |
| 扩展名 / 安装 | `CREATE EXTENSION pg_stat_statements;` | **`CREATE EXTENSION sys_stat_statements;`**（需 `shared_preload_libraries='sys_stat_statements'` 并重启） |
| 重置函数 | `pg_stat_statements_reset()` | **`public.sys_stat_statements_reset()`** |
| 重置时间获取 | `pg_stat_statements_info` 视图 | **`sys_stat_statements_get_reset_time()` 函数**（无对应视图） |
| 参数名 | `pg_stat_statements.track` / `.max` / `.save` | **`sys_stat_statements.track`** / **`.max`** / **`.save`**，另有 `track_parse`/`track_plan`/`track_utility` |
| WAL 字节统计 | `wal_bytes`（PG13+） | **不存在**。写放大改用 `shared_blks_dirtied` / `shared_blks_written` 评估 |
| 版本字段判定 | 按 `server_version_num`（13+/14+） | **不能**按版本判断：KES R1C10 的 `server_version_num=120001`（PG12 兼容），但其 `sys_stat_statements` 1.11 实际采用 PG14+ 字段集（含 `total_plan_time`/`mean_plan_time`/`blk_read_time`/`temp_blks_*` 等）。**必须用 `information_schema.columns` 动态探测字段**后再构造采集 SQL |
| 当前会话可见性 | 视图含当前会话自身语句 | `sys_stat_statements` 默认**排除当前会话**自身语句；需要包含时可用函数 `sys_stat_statements_all()` |
| queryid 归一化 | 文本归一化后同一 SQL 基本同 queryid | 实测同一 SQL 因字面量书写方式不同（如常量直接出现 vs 参数化）可能生成**不同 queryid**，调用计数会被拆分到多个条目，汇总时注意按 query 文本归一化合并 |

## 连接信息解析（所有脚本共用，优先级从上到下）

1. **用户显式提供**：用户消息中给出的 host/port/user/password/dbname（或脚本命令行参数）
2. **环境变量**：`PGHOST` / `PGPORT` / `PGDBNAME` / `PGUSER` / `PGPASSWORD`
3. **内置默认值**：`PGHOST=127.0.0.1` `PGPORT=5432` `PGDBNAME=kingbase` `PGUSER=kingbase` `PGPASSWORD=123456`

> 金仓官方手册中相关变量可能写作 `KINGBASEHOST`/`KINGBASE_HOST` 等，本 skill 一律使用 PG 兼容环境变量名，不做 `KINGBASE_*` 兜底。

## 脚本与双连接方式

- `scripts/00_precheck.sql`、`scripts/01_snapshot.sql`：纯 SQL，可直接用 psql/ksql 执行（`psql "host=... port=... user=... dbname=..." -f ...`）。`snapshot_diff.py` 内含等价逻辑（预检与动态列拼接），两者任选其一即可，不要同时重复执行。
- `scripts/snapshot_diff.py`：一站式「预检 → 快照1 → 等待 → 快照2 → 差值 → 多维度 TOP 排行」脚本，**自动选择连接后端**：
  - python SDK 模式：优先 `psycopg`（v3），其次 `psycopg2`；
  - psql shell 模式：调用系统 `psql`（或 `ksql`）子进程；
  - `--mode auto|sdk|psql` 可强制指定，默认 `auto`（有 SDK 用 SDK，否则退化为 psql）。

## 前置要求

- 一个可用的 psql/ksql 客户端或 Python `psycopg`/`psycopg2`，以及目标实例连接信息。
- 目标实例已安装并启用 `sys_stat_statements` 扩展（KES V9R1C10 默认随 `shared_preload_libraries` 启用）。
- 连接账号至少具备读取 `public.sys_stat_statements` 的权限；重置模式还需 `sys_stat_statements_reset()` 执行权限。
- 不缓存、不外传密码等连接凭据；凭据仅用于当次连接，不写入日志或输出报告。

## 工作流程

### Step 0：连接与前置条件检查

1. 按「连接信息解析」确定连接参数。
2. 执行 `scripts/00_precheck.sql`（psql）或 `python3 scripts/snapshot_diff.py --precheck-only`（SDK/psql 均可）完成检查：
   - `sys_stat_statements` 扩展是否已安装（`pg_extension`），记录扩展版本。
   - `sys_stat_statements.track` 是否为 `all`；KES 默认是 `top`，若为 `top`/`none`，函数/存储过程内部的非顶层语句可能采集不到，需警告。
   - `server_version_num`（报告标注用）与 `sys_stat_statements.max`（采样容量）。
   - **动态探测 `public.sys_stat_statements` 的可用列**（`information_schema.columns`），据此确定本次可用的分析维度。
3. 若扩展未安装或未启用，**立即终止**，向用户输出：
   ```
   检测到 sys_stat_statements 未启用。请在目标库执行：
     1. kingbase.conf 中添加：shared_preload_libraries = 'sys_stat_statements'
     2. 重启实例后执行：CREATE EXTENSION sys_stat_statements;
     3. 建议同时设置：sys_stat_statements.track = 'all'
   完成后重新运行本次分析。
   ```
4. 若 `track` 不是 `all`，给出警告但可继续，并在最终报告中注明局限。
5. 若 `track_io_timing=off`，`blk_read_time`/`blk_write_time` 恒为 0，报告中注明 IO 耗时维度不可用（可提示临时 `SET track_io_timing=on` 属会话级，不持久）。

### Step 1：选择采集模式

主动询问用户使用哪种模式（默认推荐「差值模式」，不影响全局统计数据）：

| 模式 | 做法 | 适用场景 | 风险 |
|------|------|----------|------|
| **重置模式**（默认不用） | 采集 → `sys_stat_statements_reset()` → 等待 → 再采集 | 需要精确的「纯增量」数据，且能接受清空历史统计 | 会清空全局统计计数器，影响其他依赖这些统计的监控/分析，仅在非生产核心时段或用户明确授权后执行 |
| **差值模式**（推荐默认） | 采集快照1（不 reset）→ 等待 → 采集快照2 → 对 calls/total_exec_time/rows 等累计字段做差值 | 生产环境常规巡检，不希望影响其他监控 | 若采集间隔内发生了 reset 或语句因 `sys_stat_statements.max` 被淘汰，某些 queryid 的差值可能为负或缺失，需识别并在报告中注明 |

- 使用重置模式前，**必须**输出醒目警告：「⚠️ 即将执行 sys_stat_statements_reset()，将清空该实例全局 SQL 统计历史，请确认已获得授权」，并等待用户确认后才可执行。
- 差值模式下，若发现快照2中某 queryid 的 calls/total_exec_time 小于快照1（说明期间发生过重置或该记录被淘汰后新生成），将该记录标记为「数据不连续，本次已剔除」，不纳入排行榜。

### Step 2：两阶段数据采集

1. 记录 `snapshot1_time`，执行 `scripts/01_snapshot.sql` 采集全量 `sys_stat_statements` 数据（字段清单见 `references/collected_fields.md`）保存到上下文/临时表；
   **推荐**直接运行 `python3 scripts/snapshot_diff.py --interval-seconds <N> --output <file>.json` 一步完成快照1→等待→快照2→差值（此时等待由脚本内部完成）。
2. 重置模式：执行 `SELECT public.sys_stat_statements_reset();`；差值模式：跳过此步。
3. 输出提示：「快照 1 已采集（共 N 条 SQL 记录）。建议等待 **5-15 分钟**（覆盖一个完整业务波峰更佳）后进行第二次采集。」
   - 若用户要求「现在就采集」，可缩短等待，但需提醒采集时长过短会导致样本量不足、TOP 排行代表性下降。
   - 若使用 `snapshot_diff.py`，等待在脚本内完成，`--interval-seconds` 可由用户指定（验证/演示场景可用 30-60 秒）。
4. 到达约定时间后，记录 `snapshot2_time`，再次采集。
5. 计算实际采集间隔 `interval = snapshot2_time - snapshot1_time`，在报告开头注明。

### Step 3：差值计算

对两次快照按 `queryid` 关联，计算：

- 重置模式：快照2的值即为增量值（计数器已清零）。
- 差值模式：`delta = snapshot2.value - snapshot1.value`，对 `calls`、`total_exec_time`、`total_plan_time`、`rows`、`shared_blks_hit`、`shared_blks_read`、`shared_blks_dirtied`、`shared_blks_written`、`temp_blks_written`、`blk_read_time`、`blk_write_time` 等累计字段逐一做差值；`mean_exec_time = delta.total_exec_time / delta.calls`（`delta.calls = 0` 时跳过该条，不计入任何排行）。
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
| 写放大 TOP | `shared_blks_dirtied` 降序 | 无 | 脏块/写压力最大（KES 无 wal_bytes，以写放大近似 WAL 生成量维度） |
| 单次返回行数异常 TOP | `rows / calls` 降序 | `calls >= 1` | 疑似全表扫描返回大量行 |
| 总扫描行数 TOP | `rows` 降序 | 无 | 对数据库整体扫描压力最大 |

每张表列：排名、SQL 文本(截取)、用户名、执行次数、平均耗时(ms)、总耗时(ms)、缓存命中率(%)（`shared_blks_hit / (shared_blks_hit + shared_blks_read)`）、返回/影响总行数、写放大（脏块数，或对应维度指标）。

- 若某字段在目标实例的 `sys_stat_statements` 中不存在（动态探测发现），跳过对应维度并在报告中注明。
- `track_io_timing=off` 时 `blk_read_time`/`blk_write_time` 全为 0，不作为单独维度，仅作补充。

### Step 5：逐条优化建议（每维度 TOP 3）

对每个维度的 TOP 3 SQL，按 `references/diagnosis_playbook.md` 中的诊断框架逐一产出：

1. **SQL 可读化**：尝试将 `$1`、`$2` 等参数还原为示例值或类型占位（如 `$1::int`），无法还原则保留原文并说明。
2. **性能摘要**：一句话概括核心问题（如「平均执行 5.2 秒，缓存命中率仅 23%，calls=1200」）。
3. **问题诊断**：从 `references/diagnosis_playbook.md` 的 6 个方向逐一排查（缺索引 / 索引失效 / JOIN 不佳 / 子查询可改写 / 缺 LIMIT 分页 / 高频 DML 可合并），只列出实际命中的方向，不逐条罗列不相关项。
4. **具体建议**：给出可直接执行的 SQL（如 `CREATE INDEX idx_xxx ON table(user_id);`），建议须保守、兼容现有业务，避免破坏性改造。
5. **预估收益**：高 / 中 / 低，并说明判断依据。

### Step 6：综合汇总

1. **健康评分（百分制）**：
   - 缓存命中率 30% + 平均执行时间合理性 30% + 全表扫描比例 20% + 写放大合理性 20%
   - 具体计分公式与分档标准见 `references/health_score.md`
2. **Top 3 最值得优化的 SQL**：合并 7 个维度中重复出现的高频项，给出最终优先级排序及理由。
3. **整体负载画像**：一句话总结（如「读密集型，Top SQL 中 60% 存在全表扫描」或「写入密集型，写放大集中在 3 条批量 UPDATE」）。

## 输出格式

完整报告结构模板见 `references/report_template.md`，整体分为：

1. 采集元信息（实例信息脱敏展示、采集模式、采集间隔、版本信息、track 设置提示、可用维度列表）
2. 7 张 TOP SQL 排行表
3. 逐条优化建议（每维度 TOP 3，共最多 21 条，去重后合并展示）
4. 健康评分卡 + Top 3 优先级 + 负载画像
5. 附录：本次分析的局限性说明（如差值模式下被剔除的不连续记录数量）

输出语言为中文；报告中不得包含真实密码等连接凭据。

## Pitfalls & Solutions

| 坑点 | 现象 | 解决方案 |
|------|------|----------|
| 误用 `pg_stat_statements` | 查询报错：relation "pg_stat_statements" does not exist | KES 必须用 `public.sys_stat_statements`，本 skill 所有 SQL/脚本均已适配 |
| track 未设为 all | 函数/存储过程内部的 SQL 未被统计 | Step 0 检测并警告（KES 默认 top），报告中注明可能存在遗漏 |
| 差值模式下计数器倒退 | 某 queryid 快照2值小于快照1 | 判定为期间发生过 reset 或语句被淘汰，剔除该条并在附录说明数量 |
| sys_stat_statements.max 太小 | 高频新查询挤出老查询，采样失真 | 报告中提示当前 `sys_stat_statements.max` 配置值，建议按需调大 |
| 按 server_version_num 误判字段 | R1C10 显示 120001，但实际有 total_plan_time | 一律用 `information_schema.columns` 动态探测字段，不用版本号判断 |
| 误用 wal_bytes 字段 | 列不存在报错 | KES 无 wal_bytes；写放大维度用 `shared_blks_dirtied`/`shared_blks_written` |
| queryid 被拆分 | 同一 SQL 出现多个 queryid，calls 分散，TOP 排行偏低 | 实测 KES 对同文本 SQL 可能按字面量书写方式生成不同 queryid；报告时按 query 文本归一化后合并统计，并在附录注明 |
| 采集间隔过短 | 样本量不足，TOP 排行代表性差 | 建议至少 5-15 分钟，覆盖一次业务波峰 |
| query 文本被截断丢失关键 WHERE 条件 | 参数化 SQL 难以判断具体过滤列 | 结合 `sys_stat_statements.query` 全文（内部使用）+ `EXPLAIN`（如用户授权）辅助判断，仍无法确定则如实说明「需要结合执行计划进一步确认」 |
| 重置模式误清空监控依赖的统计 | 其他监控系统数据丢失 | 执行前必须走「醒目警告 + 用户确认」，默认引导使用差值模式 |
| 本机无 psycopg2 也无 psql | 无法连接 | `pip install psycopg2-binary --break-system-packages` 或安装金仓自带 ksql 客户端 |

## 注意事项

- `sys_stat_statements_reset()` 属于高风险操作，仅在用户明确授权后执行；默认使用差值模式。
- 连接凭据（尤其密码）不写入最终报告、不记录到 `references/` 或 `scripts/` 之外的任何持久化文件。
- 所有优化建议须遵循 KingbaseES/PostgreSQL 最佳实践，避免激进的、可能破坏兼容性的改造建议（如不建议盲目删除现有索引）。
- 高危 DDL 类建议（如建索引）应提示「建议先在测试环境或低峰期执行，大表建索引可加 `CONCURRENTLY`」。
- 若目标是云托管实例（如云上 KingbaseES），`sys_stat_statements_reset()` 权限可能受限，需提示用户改用差值模式或联系厂商支持。
- 金仓内置 KWR/`sys_stat_sql` 系列是快照历史表，与本次「两阶段做差」互不干扰；不要手动调用 `kwr_snap`/`kwr_report` 等过程。
