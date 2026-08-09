---
name: kingbase-large-table-optimize
description: "KingbaseES（金仓）大表识别与容量规划专家技能。给定 KingbaseES 实例连接信息（主机/端口/用户名/密码，或 PGHOST/PGPORT/PGDBNAME/PGUSER/PGPASSWORD 环境变量），自动发现大表、剔除膨胀水分得到真实数据量、分析每张大表的 DML/扫描/索引负载特征，判定负载类型（高频更新/纯写入/OLTP点查/分析型/混合型），并给出分区改造、autovacuum 调优、索引优化等针对性建议。触发条件：用户提到\"大表分析\"、\"大表优化\"、\"金仓表膨胀\"、\"金仓表变胖了\"、\"金仓容量规划\"、\"这张表要不要分区\"、\"autovacuum 调优\"、\"金仓表统计信息分析\"、\"kingbase 性能诊断\"、\"帮我看看这个金仓实例有哪些大表\"、\"金仓数据库瘦身\"，或提供了 KingbaseES 连接信息并希望做体检/优化建议。即使用户只说\"帮我看看我的金仓库是不是该分区了\"或\"这个金仓实例是不是该做维护了\"，也应使用本 skill。全程只读，不执行任何 DDL/DML。"
tags: [KingbaseES, 金仓, 大表优化, 表分区, 大表工作负载分析]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# KingbaseES（金仓）大表优化与容量规划

给定一个 KingbaseES（金仓）实例的连接信息，识别真实大表（剔除膨胀干扰），分析每张大表的工作负载特征（DML 活跃度、读取模式、索引深度），按负载类型给出结构化优化建议（分区改造、autovacuum 调参、索引重构、归档策略等），最终产出一份可执行的优化优先级报告。

**核心原则：全程只读。** 本技能只查询系统视图和统计信息，**严禁执行任何 DDL 或 DML**（包括 VACUUM、ANALYZE、REINDEX、CREATE EXTENSION 等操作也只建议、不执行，除非用户明确授权）。

## 连接信息与默认值

- **兼容模式假设**：KingbaseES 默认运行在 PostgreSQL 兼容模式，本技能全部使用 `pg_*` 目录视图/函数（已在 V9R1C10 PG 兼容模式下实测可用）。若实例被配置为其他兼容模式（如 Oracle 模式），先提示用户确认/切换。
- 连接参数优先级（从高到低）：
  1. 用户在当前对话中显式提供的 host/port/user/password/dbname；
  2. 环境变量：`PGHOST`、`PGPORT`、`PGDBNAME`（兼容标准 PG 的 `PGDATABASE`）、`PGUSER`、`PGPASSWORD`；
  3. 内置默认值：`PGHOST=127.0.0.1 PGPORT=5432 PGDBNAME=kingbase PGUSER=kingbase PGPASSWORD=123456`。
- 默认 dbname 为 `kingbase`（金仓默认管理库）；用户未指定 dbname 时遍历全部非模板库（`pg_database WHERE datistemplate=false AND datallowconn=true`）。
- 密码只用于建立连接：不写入日志、不回显、不上传；优先用 `PGPASSWORD` 环境变量或 `.pgpass` 传递，避免出现在命令行参数中被 `ps` 等工具窥探。

## 前置要求

- 连接账号需具备：登录权限 + 目标库 `CONNECT` 权限；`pg_stat_user_tables` / `pg_stat_user_indexes` 等统计视图默认对登录用户可读，无需额外授权。若要以精确模式分析膨胀，需安装 `kbstattuple` 扩展（见阶段 0，安装属 DDL，须用户授权）。
- 运行环境：`psql`（推荐，shell 采集）或 Python 3 + `psycopg2-binary`（批量采集脚本）。KingbaseES 兼容 PG 网络协议，标准 `psql` / `psycopg2` 可直接连接；金仓自带客户端为 `ksql`，同样适用。
- 网络需能访问目标 host:port。
- 已在 V9R1C10（PG 兼容模式）实测可用的目录对象：`pg_class / pg_namespace / pg_extension / pg_database / pg_inherits / pg_partitioned_table / pg_stat_user_tables / pg_stat_user_indexes / pg_am / pg_proc`、`pg_partition_tree()`、`pg_total_relation_size() / pg_relation_size() / pg_indexes_size()`。注意 **`sys_extension` 目录在 V9R1C10 中不存在**，扩展检测一律用 `pg_extension`。

## 工作流程

### 阶段 0：连接与预检

1. 按上文优先级解析连接参数，执行 `SELECT version();` 确认连通；用 `SELECT current_setting('server_version_num');` 记录兼容的 PG 版本基线（V9R1C10 为 120001，即 PG 12.1，SQL 语法以 PG12 为基线，不支持 PG13+ 语法）。
2. 检测精确分析能力（**金仓用 `kbstattuple` 而非 PG 的 `pgstattuple`**）：
   ```sql
   SELECT extname, extversion FROM pg_extension WHERE extname IN ('kbstattuple', 'pageinspect');
   ```
   - 已安装 `kbstattuple` → 精确模式：`kbstattuple()` 实测死元组占比、`kbstatindex()` 实测 B-Tree 层高（见阶段 1/2）；
   - 未安装 → 近似模式：用 `n_dead_tup` 估算，报告注明「近似估算，误差可能在 ±20% 以内」；在报告「实例级建议」中提示（须用户授权后执行）：`CREATE EXTENSION kbstattuple;`（金仓官方插件，安装包随实例发行）。
3. 列出非模板库：`SELECT datname FROM pg_database WHERE datistemplate=false AND datallowconn=true;` 指定 dbname 则只处理该库，否则逐库遍历（KES 与 PG 一样不支持跨库查询，每库单独建连）。

### 阶段 1：大表发现与膨胀修正

对每个数据库执行 `references/sql-queries.md` 的 **1.1 大表初筛**（每库 TOP 20 或总大小 > 10GB，阈值可覆盖），输出：库名、Schema、表名、总大小、表本体、索引总大小、TOAST、估算行数、是否分区表及分区数。

对每张候选表执行 **1.2 膨胀修正**：
- 近似法：死元组占比 = `n_dead_tup/(n_live_tup+n_dead_tup)*100`；估算膨胀 ≈ 表本体大小 × 死元组占比 × 膨胀系数（默认 1.0）；修正后真实大小 = 表本体 − 估算膨胀。
- 精确法（已装 `kbstattuple`）：直接取 `kbstattuple('schema.table')` 的 `dead_tuple_percent` / `free_percent`（全表扫描，成本较高，只对候选大表调用）；超大表可用 `kbstattuple_approx()` 抽样加速。
  - **口径提醒（已在实例实测）**：`kbstattuple` 是堆物理扫描实测值；`pg_stat_user_tables.n_dead_tup` 则是自上次 VACUUM/autovacuum 以来的累计计数器（vacuum 后会清零），两者在同一时刻可能明显不一致（例如大 UPDATE 后立即采集 vs autovacuum 已触发后再采集）。**以 `kbstattuple` 为准评估物理可回收空间**（可回收 ≈ 死元组 + 页内空闲空间，对应 `dead_tuple_percent` + `free_percent` 占表体大小的比例）；`n_dead_tup` 用于判断膨胀趋势与 autovacuum 触发压力。报告应同时呈现两者并注明采集时刻的 `last_autovacuum`。
- 死元组占比 > 20% 标记「膨胀严重」，注明 VACUUM FULL / sys_squeeze 后预期缩减到的大小。

**1.3 最终判定**：
- 真实大小仍 > 10GB → 纳入「需要优化的大表」，进入阶段 2；
- 真实大小 < 10GB 但膨胀前很大 → 输出「真实数据量不大，优先 VACUUM FULL / sys_squeeze 回收空间即可，无需结构性优化」。

报告中明确区分：**真大表（需结构优化）** vs **膨胀型虚胖表（只需回收空间）**。

### 阶段 2：工作负载特征分析

对每张「需要优化的大表」采集三组画像（SQL 见 `references/sql-queries.md` 第 2 节）：
1. **DML 活跃度**（写入/更新比率、HOT 更新效率、DML 密度）
2. **读取模式**（索引使用率、每次索引/顺序扫描平均行数）
3. **索引深度**：已装 `kbstattuple` 时用 `kbstatindex('<index>')` 的 `tree_level` 直接获得**精确层高**（金仓优势，优于按大小估算）；未装则用大小估算公式；可选用 `pageinspect` 的 `bt_metap()` 交叉验证。`tree_level > 3` 标记「索引偏深」。

### 阶段 3：负载分类与优化建议

按 `references/optimization-types.md` 的五类模板归类（A 高频 UPDATE/DELETE / B 高频 INSERT ONLY / C OLTP 点查 / D 分析型 / E 混合型），**逐条引用对应类型模板，不要泛泛而谈**。分区键若无法从统计信息推断，明确标注「需与业务方确认」。

### 阶段 4：报告输出

按 `references/output-template.md` 生成中文报告：📋 大表总览 → 🔍 逐表详细分析 → 📊 优化优先级 TOP 10 → ⚙️ 实例级参数调整建议。

## 采集方式

优先用 `scripts/collect_large_tables.py`（JSON 输出）或 `scripts/collect_large_tables.sh`（psql 文本/CSV 输出）一次性采集全部原始数据，再基于采集结果分析与写报告。两个脚本的连接参数解析逻辑一致（命令行 > 环境变量 > 默认值）：

```bash
# Python 方式（需 psycopg2）
pip install psycopg2-binary --break-system-packages
python3 scripts/collect_large_tables.py [--host H] [--port P] [--user U] [--password PW] \
  [--dbname DB] [--top-n 20] [--min-size-gb 10] [-o /tmp/kingbase_large_table_raw.json]

# psql shell 方式（无需 Python 依赖）
bash scripts/collect_large_tables.sh --top-n 20 --min-size-gb 10 --output-dir /tmp/kb_lto
```

不传任何参数且未设置环境变量时，两个脚本均按默认值 `127.0.0.1:5432/kingbase/kingbase/123456` 连接。

**注意两个脚本的行为差异**：`collect_large_tables.py` 在未指定 dbname 时**遍历全部非模板库**；而 `collect_large_tables.sh` 只采集**单个数据库**（默认 `kingbase`，或 `--dbname` 指定的库）——需要多库采集时对每个库分别执行一次，或直接改用 Python 脚本。

## 输出格式

见 `references/output-template.md`。最终交付中文 Markdown 报告，结构固定为：

📋 大表总览 → 🔍 逐表详细分析 → 📊 优化优先级 TOP 10 → ⚙️ 实例级参数调整建议

报告中的 SQL 模板可直接复制执行（但仅代表建议、未实际执行）；所有 DDL 需业务方审核后在维护窗口手动执行。

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|---|---|
| 实例未装 `kbstattuple`，膨胀只能近似估算 | 自动降级为 `n_dead_tup` 近似法，报告注明「近似估算，误差可能在 ±20% 以内」；报告中建议（需授权后执行）`CREATE EXTENSION kbstattuple` |
| `n_dead_tup`（pg_stat_user_tables）与 `kbstattuple` 实测值不一致 | 两者口径不同：前者是自上次 VACUUM 起的累计计数器（autovacuum 后会清零），后者是堆物理扫描实测。以 `kbstattuple` 评估可回收空间，以 `n_dead_tup` 看膨胀趋势；报告中同时呈现，并注明 `last_autovacuum` 采集时刻，必要时在业务低峰重测 |
| 误以为存在 `sys_extension` 目录 | V9R1C10 PG 兼容模式下 `sys_extension` 不存在，扩展检测一律用 `pg_extension` |
| 实例非 PG 兼容模式（如 Oracle 模式），`pg_*` 视图不可用 | 连接后先 `SELECT version();` + `current_setting('server_version_num')` 探明兼容模式，要求确认/切换回 PG 兼容模式 |
| 分区表统计按父表/子表分别记录，容易漏算 | 用 `pg_partition_tree()` 汇总各叶子分区统计量，单独提示分区数量与最大分区 |
| `idx_scan` 为 0 导致除零 | 分母为 0 时跳过比率计算，标注「无索引扫描记录」而非报错 |
| 统计计数器是自统计重置以来的累积值，代表性不足 | 报告末尾提醒：如需时段性负载分析，可用 `sys_stat_statements` 或高峰期前后两次快照差值；KES 自带 `sys_kwr` 工作负载仓库可交叉验证 |
| 大型实例（数千张表）逐表分析耗时过长 | 严格按「TOP 20 或 > 10GB」过滤候选表，不对全量表逐一分析 |
| 密码通过命令行传递被 `ps` 窥探 | 优先 `PGPASSWORD` 环境变量或 `.pgpass`；采集完成后清除历史命令记录中的明文密码 |
| 跨库统计需要多次连接 | 每个数据库单独建连采集，不假设一次连接可跨库查询 |
| 金仓系统 schema（`sys_hm` / `sysmac` / `sysaudit` 等）混入候选表 | 大表初筛时排除金仓内置系统 schema（默认排除列表见 `references/sql-queries.md`），仅聚焦业务库表 |

## 参考资料（金仓官方文档，KES-V9R1C10）

- 插件参考：`kbstattuple`（精确膨胀/索引层高分析）：`https://docs.kingbase.com.cn/cn/KES-V9R1C10/reference/database/插件参考/kbstattuple`
- 插件参考：`sys_stat_statements`（TOP SQL/时段负载分析）：`https://docs.kingbase.com.cn/cn/KES-V9R1C10/reference/database/插件参考/sys_stat_statements`
- 插件参考：`cstore_fdw`（列存）：`https://docs.kingbase.com.cn/cn/KES-V9R1C10/reference/database/插件参考/cstore_fdw`
- 数据库管理·运行时参数：autovacuum：`https://docs.kingbase.com.cn/cn/KES-V9R1C10/administration/Config_Mgmt/runtime-config-autovacuum`
- 系统视图：`sys_partitioned_table` 等：`https://docs.kingbase.com.cn/cn/KES-V9R1C10/reference/database/系统视图/kes_views/metadata_views/sys_partitioned_table`

## 注意事项

- **只读边界**：全程仅执行 `SELECT` 查询系统目录和统计视图；`VACUUM` / `ANALYZE` / `REINDEX` / `ALTER TABLE` / `CREATE EXTENSION` 等一律只作为报告中的「建议 SQL」呈现，需用户授权并在维护窗口手动执行，且做好回滚方案（如分区改造前先在只读副本或测试环境验证）。
- **网络与凭据边界**：只连接用户明确提供的目标实例地址，不额外发起其他网络请求；密码仅用于建立数据库连接，不记录、不回显、不上传。
- 大表定义阈值（10GB / TOP 20）、膨胀系数（1.0）均为默认值，可由用户显式覆盖。
- 分区/归档等建议涉及业务语义（分区键选择），无法从统计信息明确推断时必须在报告中标注「需与业务方确认」，不要臆断。
- 若实例存在只读备库、连接池（pgbouncer）等中间件，报告中相关建议（如「路由到只读备库」）需说明前提是该组件已存在或需新增。
