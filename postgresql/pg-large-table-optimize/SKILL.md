---
name: pg-large-table-optimize
description: "PostgreSQL 大表识别与容量规划专家技能。给定实例连接信息（主机/端口/用户名/密码），自动发现大表、剔除膨胀水分得到真实数据量、分析每张大表的 DML/扫描/索引负载特征，判定负载类型（高频更新/纯写入/OLTP点查/分析型/混合型），并给出分区改造、autovacuum 调优、索引优化等针对性建议。触发条件：用户提到\"大表分析\"、\"大表优化\"、\"表膨胀\"、\"表变胖了\"、\"数据库容量规划\"、\"这张表要不要分区\"、\"autovacuum 调优\"、\"表统计信息分析\"、\"pg 性能诊断\"、\"帮我看看这个 PG 实例有哪些大表\"、\"数据库瘦身\"，或提供了 PostgreSQL 连接信息并希望做体检/优化建议。即使用户只说\"帮我看看我的库是不是该分区了\"或\"这个库是不是该做维护了\"，也应使用本 skill。全程只读，不执行任何 DDL/DML。"
tags: [PostgreSQL, 大表优化, 表分区, 大表工作负载分析]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# PostgreSQL 大表优化与容量规划

给定一个 PostgreSQL 实例的连接信息，识别真实大表（剔除膨胀干扰），分析每张大表的工作负载特征（DML 活跃度、读取模式、索引深度），按负载类型给出结构化优化建议（分区改造、autovacuum 调参、索引重构、归档策略等），最终产出一份可执行的优化优先级报告。

**核心原则：全程只读。** 本技能只查询系统视图和统计信息，**严禁执行任何 DDL 或 DML**（包括 VACUUM、ANALYZE、REINDEX 等维护性操作也只建议、不执行）。

## 前置要求

- 目标实例的连接信息：host、port、user、password（或等效的 `.pgpass` / 环境变量）、以及可选的目标 dbname（不指定则遍历全部非模板库）。
- 连接账号至少具备：登录权限 + 对目标库的 `CONNECT` 权限 + 默认情况下 `pg_stat_user_tables` / `pg_stat_user_indexes` 等统计视图对所有登录用户可读，无需额外授权；若实例开启了 `pg_stat_statements` 或安装了 `pgstattuple` 扩展可获得更精确结果，但**不是必需依赖**（缺失时自动降级为近似估算，见下文）。
- 运行环境需安装 `psql`（推荐，用于交互式采集）或 Python 3 + `psycopg2-binary`（用于批量脚本采集，见 `scripts/collect_large_tables.py`）。
- 网络需能访问目标数据库的 host:port。若在沙箱/受限网络环境执行，需向用户确认网络策略是否放行该目标地址。
- 不将连接密码写入任何日志文件、不上传到任何外部服务；采集完成后建议清理包含明文密码的临时连接串。

## 工作流程

### 阶段 0：连接与预检

1. 使用连接信息尝试连接实例，执行 `SELECT version();` 确认可连通。
2. 检测 `pgstattuple` 扩展是否已安装：
   ```sql
   SELECT extname FROM pg_extension WHERE extname = 'pgstattuple';
   ```
   已安装则后续膨胀估算可用 `pgstattuple()` 精确值；未安装则全程使用近似算法，并在最终报告中注明精度限制。
3. 列出所有非模板数据库：
   ```sql
   SELECT datname FROM pg_database WHERE datistemplate = false AND datallowconn = true;
   ```
   若用户指定了 dbname，只处理该库；否则逐库遍历（每个库需单独建立连接，PostgreSQL 不支持跨库查询）。

### 阶段 1：大表发现与膨胀修正

对每个数据库执行 `references/sql-queries.md` 中的 **1.1 大表初筛** 查询，取每库 TOP 20（或总大小 > 10GB）的表，输出：库名、Schema、表名、总大小（含索引+TOAST）、表本体大小、索引总大小、TOAST 大小、估算行数（reltuples）、是否分区表及分区数。

对每张候选表执行 **1.2 膨胀修正**：

- 死元组占比 = `n_dead_tup / (n_dead_tup + n_live_tup) * 100`
- 估算膨胀大小 ≈ 表本体大小 × 死元组占比 × 膨胀系数（默认 1.0）
- 修正后真实大小 = 表本体大小 − 估算膨胀大小
- 若 `pgstattuple` 可用，优先用其 `dead_tuple_percent` 和 `free_percent` 替代近似值，精度更高
- 死元组占比 > 20% 标记为「膨胀严重」，注明 VACUUM FULL / pg_repack 后预期缩减到的大小

**1.3 最终判定**：以修正后真实大小重排：
- 真实大小仍 > 10GB → 纳入「需要优化的大表」清单，进入阶段 2
- 真实大小 < 10GB 但膨胀前很大 → 输出「真实数据量不大，优先 VACUUM FULL / pg_repack 回收空间即可，无需结构性优化」，不再进入阶段 2

明确在报告中区分：**真大表（需结构优化）** vs **膨胀型虚胖表（只需回收空间）**。

### 阶段 2：工作负载特征分析

对每张「需要优化的大表」，执行 `references/sql-queries.md` 中的对应查询，采集三组画像：

1. **DML 活跃度**（写入比率、更新比率、HOT 更新效率、DML 密度）
2. **读取模式**（索引使用率、每次索引扫描平均行数、每次顺序扫描平均行数）
3. **索引深度**（每个索引的 idx_scan/idx_tup_read/idx_tup_fetch、索引列与类型、按索引大小推算的 B-Tree 层高，标记超过 3 层的索引）

具体公式和 SQL 见 `references/sql-queries.md` 第 2 节，逐项计算并记录中间结果，不要跳过任何一张大表。

### 阶段 3：负载分类与优化建议

依据阶段 2 的指标，将每张大表归类为下列五种类型之一，并套用对应的优化模板：

| 类型 | 判定条件（表真实大小已 > 10GB 为前提） | 核心问题 |
|---|---|---|
| A 高频 UPDATE/DELETE | 更新比率 > 40% 或 DML 密度 > 0.5 | autovacuum 压力大、freeze 开销高 |
| B 高频 INSERT ONLY | 写入比率 > 80%，更新删除极少 | 数据无限增长，全表扫描代价递增 |
| C OLTP 点查 | 索引使用率 > 70%，平均索引扫描行数 < 100 | 索引层级深，点查多次 IO |
| D 分析型负载 | 顺序扫描占比 > 60%，索引使用率低，真实大小 > 50GB | 大规模顺序扫描，IO 带宽瓶颈 |
| E 混合型 | 同时满足 A/B/C/D 中两种以上 | 需按优先级分层处理 |

每种类型的具体优化方案（分区键推荐逻辑、autovacuum 参数调整、部分索引/覆盖索引/BRIN 选择、归档 SQL 模板、cstore_fdw/物化视图/只读副本卸载建议等）在 `references/optimization-types.md` 中给出，**必须逐条引用对应类型的模板作答，不要泛泛而谈**。分区键若无法从统计信息推断，明确标注「需与业务方确认」。

### 阶段 4：报告输出

按 `references/output-template.md` 的结构生成最终中文报告，包含：大表总览表格、逐表详细分析（按优化优先级降序）、优化优先级 TOP 10、实例级参数调整建议。

## 采集方式

优先使用 `scripts/collect_large_tables.py` 一次性采集全部原始数据（JSON 格式），再基于采集结果做分析和报告撰写，避免逐条手工执行 SQL 导致遗漏或往返过多：

```bash
pip install psycopg2-binary --break-system-packages
python3 scripts/collect_large_tables.py \
  --host <HOST> --port <PORT> --user <USER> --password <PASSWORD> \
  [--dbname <DBNAME>] [--top-n 20] [--min-size-gb 10] \
  -o /tmp/pg_large_table_raw.json
```

若环境无法安装 Python 依赖或用户更倾向手工排查，退化为使用 `psql` 逐条执行 `references/sql-queries.md` 中的查询，人工汇总结果后再做分析。

## 输出格式

见 `references/output-template.md`，最终交付一份 Markdown 报告，结构固定为：

📋 大表总览 → 🔍 逐表详细分析 → 📊 优化优先级 TOP 10 → ⚙️ 实例级参数调整建议

报告语言为中文，SQL 模板需可直接复制执行（但报告本身不代表已执行，所有 DDL 均需业务方审核后手动执行）。

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|---|---|
| `pgstattuple` 未安装导致膨胀估算不精确 | 自动降级为 `n_dead_tup` 近似法，报告中注明「近似估算，误差可能在 ±20% 以内」 |
| 分区表的 `pg_stat_user_tables` 统计是按父表还是子表分别记录，容易漏算 | 对分区表额外查询 `pg_partition_tree` / `pg_inherits` 汇总各分区的统计量，并单独提示分区数量与最大分区 |
| `idx_scan` 为 0 导致除零错误（平均索引扫描行数） | 判断分母为 0 时直接跳过该比率计算，标注「无索引扫描记录」而非报错 |
| 统计计数器是自 `pg_stat_reset()` 以来的累积值，可能包含很久以前的旧数据，代表性不足 | 在报告结尾提醒用户：如需更精确的时段性负载分析，可在业务高峰期前后分别采集快照，做差值分析 |
| 大型实例（数千张表）逐表执行分析耗时过长 | 严格按「总大小 TOP 20 或 > 10GB」过滤候选表，不对全量表做逐一分析 |
| 密码通过命令行参数传递可能被 `ps` 等工具窥探 | 优先使用 `PGPASSWORD` 环境变量或 `.pgpass` 文件，而非命令行明文参数；采集完成后清除历史命令记录中的明文密码 |
| 跨库统计需要多次连接 | 每个数据库单独建立连接后采集，不要假设一次连接可跨库查询 |

## 注意事项

- **只读边界**：全程仅执行 `SELECT` 查询系统目录和统计视图，不执行 `VACUUM`、`ANALYZE`、`REINDEX`、`ALTER TABLE` 等任何维护或结构变更操作；所有此类操作只作为报告中的“建议 SQL”呈现，需业务方在维护窗口内手动执行并做好回滚方案（如分区改造前先在只读副本或测试环境验证）。
- **网络与凭据边界**：只连接用户明确提供的目标实例地址，不额外发起其他网络请求；密码仅用于建立数据库连接，不记录、不回显、不上传。
- 大表定义阈值（10GB / TOP 20）、膨胀系数（1.0）均为默认值，可由用户显式覆盖。
- 分区/归档等建议涉及业务语义（如分区键选择），当无法从统计信息中明确推断时，必须在报告中标注「需与业务方确认」，不要臆断。
- 若实例存在只读备库、连接池（pgbouncer）等中间件，报告中相关优化建议（如"路由到只读备库"）需说明前提是该组件已存在或需新增。
