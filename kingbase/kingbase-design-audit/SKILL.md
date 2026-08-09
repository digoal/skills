---
name: kingbase-design-audit
description: "KingbaseES（金仓）资深 DBA / 架构审查专家能力。给定 KingbaseES 实例连接信息（主机、端口、用户名、密码），对实例内所有数据库做全面只读扫描，找出设计不规范或存在潜在使用风险的对象和模式。KingbaseES 默认采用 PG 兼容模式，系统视图 / SQL 语法 / GUC 与 PostgreSQL 12 高度一致，本 skill 在此基础上做了金仓 schema 名单适配（排除 sys_catalog、sys_hm、sysaudit、sysmac、src_restrict 等内置 schema）。触发场景：用户提到\"金仓设计审查\"、\"KingbaseES 实例体检\"、\"金仓库检查\"、\"帮我审查这个金仓库\"、\"金仓表结构有没有问题\"、\"金仓索引设计\"、\"金仓命名规范\"、\"金仓字段类型\"、\"金仓缺主键\"、\"金仓大表分区\"、\"金仓冗余索引\"、\"金仓未使用索引\"，或提供了 KingbaseES 的 host/port/user/password 并希望做全面体检。即使用户只说\"帮我看看这个金仓库设计得怎么样\"或\"这个 KingbaseES 实例有什么问题\"，只要给出了连接信息，也应使用本技能。"
tags: [KingbaseES, 金仓, 设计检查, 设计规范检查]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# KingbaseES 设计与风险审查（kingbase-design-audit）

对一个 KingbaseES 实例的所有数据库做 7 大类只读扫描（命名规范、字段类型、注释缺失、大表分区、
索引设计、约束默认值、库级配置），产出按 🔴/🟡/🔵 三级风险分类的 Markdown 审查报告，
含问题总览表、综合健康评分（百分制）与 Top 10 整改建议。

## 与 pg-design-audit 的关系

本 skill 是 `pg-design-audit` 在 KingbaseES 上的等价实现，工作流与产出格式完全一致。
默认假设 KingbaseES 运行在 **PG 兼容模式**（KingbaseES V009R001C010 / V8R6 等版本默认值），
因此 `pg_catalog` / `information_schema` / `pg_stat_*` 系统视图以及 GUC、类型、约束行为
均与 PostgreSQL 12 行为一致。脚本中的 SQL 与 `pg-design-audit/scripts/queries/` 同构，
仅在 schema 排除名单上额外排除了 KingbaseES 内置 schema。

如果用户的实例启用了 **Oracle / MySQL 兼容模式**（v8 早期版本常见），部分字段类型映射可能
偏离 PG 风格（如 `NUMBER`、`DATE`、`tinyint` 等），本 skill 的字段类型检查项可能产生噪声，
需结合 `references/risk-scoring-map.md` 末尾的"兼容模式差异补丁"人工复核。

## 前置要求

- 目标实例可通过网络访问，且提供了 host、port、user、password（以及可选的目标数据库列表，
  默认扫描实例内全部非模板、允许连接的数据库）。
- 执行环境已安装以下任一客户端：
  - `psql` 客户端（KingbaseES 兼容 PG 协议，ksql 与 psql 协议相同，推荐 `psql`）
  - Python 3.x + `psycopg2-binary` 或 `psycopg`（psycopg3）任一驱动，用于 `run_audit.py` 路径
- 审计账号至少具备 `CONNECT` 权限；若需要完整的索引使用统计/表体积统计，建议被扫描实例
  为审计账号授予 `pg_monitor` 内置角色（只读，不含任何写权限）。详见
  `references/permission-requirements.md`。
- **密码处理**：仅通过环境变量 `PGPASSWORD` 传入，不写入脚本、不写入日志、不回显在终端历史中。
  会话结束后建议 `unset PGPASSWORD`。
  > **金仓手册惯用 KINGBASE_ 前缀**：金仓官方文档中连接串环境变量多以 `KINGBASE_HOST` /
  > `KINGBASE_PORT` / `KINGBASE_USER` / `KINGBASE_PASSWORD` 形式书写，但金仓客户端完全兼容
  > PostgreSQL 客户端协议，因此 `PGHOST` / `PGPORT` / `PGUSER` / `PGPASSWORD` 同样有效。
  > 本 skill 一律沿用 `PG*` 命名以减少心智负担。

## 执行约束（硬性，不可违反）

1. 所有操作仅为只读查询 `pg_catalog` / `information_schema` / `pg_stat_*`，**严禁执行任何
   DDL 或 DML**（包括看似无害的 `ANALYZE`、`VACUUM`、`SELECT ... INTO` 均不执行）。
2. 若某检查项因权限不足无法执行，在报告对应位置标记"权限不足，需授予 xxx 权限"，
   不得静默跳过或编造结果。
3. 对于需要人工判断的项（如字段是否存储明文敏感信息、隔离级别是否真实需要非默认值），
   标记为"需人工复核"，不给出确定性结论。
4. 不在对话或产出文件中回显完整密码；如需在报告中引用连接信息，仅展示 host/port/dbname，
   不展示密码。

## 工作流程

### Step 1：收集连接信息并测试连通性

向用户确认（若用户已在请求中给出则直接使用，不重复提问）：host、port、user、password，
以及是否限定扫描的数据库列表（默认全量）。

```bash
PGPASSWORD='<password>' psql -h <host> -p <port> -U <user> -d postgres -c "SELECT version();"
```

确认连接成功、记录 KingbaseES 大版本（`server_version_num` 决定兼容的 PG 版本，
本 skill 当前适配 KingbaseES V8R6 / V009R001C010，PG 12 协议）。例如：

```sql
SELECT version();                                  -- KingbaseES V009R001C010
SELECT current_setting('server_version');          -- 12.1
```

### Step 2：发现待扫描数据库

执行 `scripts/queries/00_list_databases.sql`，得到实例内所有 `datistemplate = false`
且 `datallowconn = true` 的数据库。若用户指定了数据库子集，仅扫描该子集。

### Step 3：对每个数据库执行 7 大类只读检查

提供两套等价路径，任选其一：

#### 路径 A：psql 编排脚本（推荐，最简单）

```bash
chmod +x scripts/run_audit.sh
PGPASSWORD='<password>' scripts/run_audit.sh -h <host> -p <port> -U <user> \
  [-d db1,db2] -o ./kb_audit_output
```

#### 路径 B：Python 编排脚本（兼容 psycopg2 / psycopg3）

```bash
python3 scripts/run_audit.py -H <host> -p <port> -U <user> [-d db1,db2] -o ./kb_audit_output
# 或直接走环境变量
PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGPASSWORD='xxx' \
  python3 scripts/run_audit.py
```

任一脚本都会对每个数据库依次执行以下查询文件，并将结果落盘到
`./kb_audit_output/<db>/<查询文件名>.txt`（stderr 落盘到同名 `.err`，用于识别权限不足）：

| 文件 | 检查类别 |
|---|---|
| `01_naming.sql` | 对象/字段/索引命名规范 |
| `02_data_types.sql` | 字段类型选择合理性（布尔/时间/JSON/PK-FK类型/超长文本/金额/IP） |
| `03_comments.sql` | 表/视图/字段注释缺失统计（含缺失率） |
| `04_large_tables_partition.sql` | 超过 1GB 大表、是否分区、分区数是否超过100 |
| `05_index_design.sql` | 重复索引、冗余前缀索引、未使用索引、宽索引 |
| `06_constraints_defaults.sql` | 缺主键、缺审计时间戳、外键缺索引、应有约束的可空字段 |
| `07_db_config.sql` | 事务隔离级别、数据校验和、public 模式建表与权限 |

若无法使用脚本（如仅有交互式数据库工具而无 shell），可手动对每个数据库依次执行
`scripts/queries/` 下各 `.sql` 文件，效果等价。

### Step 4：解析结果、映射风险等级

读取 `kb_audit_output/` 下所有文本结果，对照 `references/risk-scoring-map.md` 中的
issue 标记 → 风险等级映射表，将每条原始记录归入 🔴/🟡/🔵 三级之一。

关键计算规则：
- **注释缺失率**：取 `03_comments.sql` 第3条汇总查询的 `columns_without_comment / total_columns`，
  超过 30% 时在该库报告分区标红提示，但不重复扣分。
- **健康评分**：每个数据库单独计分，100 分起，🔴 每项 -10 分、🟡 每项 -3 分、🔵 每项 -1 分，
  下限 0 分（不出现负数）。
- **需人工复核项**（如 `unused_unique_or_pk_index_review_needed`、
  `db_level_isolation_override_review_needed`）不计入扣分，单独列入"需人工复核"章节。
- **权限不足项**：`.err` 文件中出现 `permission denied` 等字样时，不计分，单独列入
  "权限不足"章节并给出 `references/permission-requirements.md` 中对应的建议授权语句。

详细的 issue → 风险等级 → 扣分对照表见 `references/risk-scoring-map.md`，务必在生成报告前
完整读取该文件，不要凭经验臆断某个 issue 属于哪个等级。

### Step 5：生成报告

按 `references/report-template.md` 的结构生成最终 Markdown 报告，包含：

1. 问题总览表（按数据库汇总三级问题数量 + 健康评分）
2. 按数据库的详细问题清单（每条含：数据库名、Schema 名、对象名、问题描述、当前情况、
   潜在风险、修复建议），按 🔴 → 🟡 → 🔵 分段展示
3. 权限不足 / 需人工复核项汇总
4. 按优先级排序的整改建议 Top 10（高危优先，同级别按所属库健康评分从低到高排序，
   即"病得越重的库，问题排得越靠前"）

报告使用中文输出。若同时使用了 `docx` 等文档技能环境，也可将本报告转换为 Word 文档，
但默认产出 Markdown 文件。

### Step 6：交付

将生成的报告文件与 `kb_audit_output/` 原始扫描结果一并提供给用户，并口头提示：
本次扫描的高危项数量、涉及数据库数、以及最值得优先处理的 1-2 个问题。

## 输出格式要求（复述执行约束，务必遵守）

- 风险分三级：🔴 高危（直接影响数据正确性/性能）、🟡 警告（增加维护成本/隐患）、
  🔵 建议（影响可维护性）。
- 每一项包含：数据库名、Schema 名、对象名、问题描述、当前情况、潜在风险、修复建议。
- 结尾必须包含：问题总览表、综合健康评分、Top 10 整改建议。

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|---|---|
| KingbaseES 自带 schema 多（sys_catalog / sys_hm / sysaudit / sysmac / src_restrict / anon / dbms_job / dbms_scheduler / kdb_schedule / perf / xlog_record_read / pg_bitmapindex）可能污染业务结果 | 所有 `.sql` 已将其加入 `nspname NOT IN (...)` 排除名单；如业务有同名 schema 需排除，自己扩展名单 |
| `sys_catalog.sys_stat_*` 与 `pg_catalog.pg_stat_*` 是两套视图 | 本 skill 全部走 `pg_catalog`（PG 兼容模式标准），不要切换到 `sys_*` |
| `sys_stat_statements` 与 `pg_stat_statements` 行为相似，但金仓默认可能改名 | 本 skill 不依赖 `*_stat_statements`，无需担心 |
| "未使用索引"判断基于 `idx_scan=0`，但集群刚重启或统计刚 reset 会导致误判 | 查询 `pg_stat_database.stats_reset`，若距今不足 7 天，在该项旁标注"统计时间过短，需人工复核"，不直接建议删除 |
| 主键/唯一索引即使 `idx_scan=0` 也不代表可删除 | 单独查询区分 `unused_unique_or_pk_index_review_needed`，不计入常规冗余索引扣分 |
| varchar 无长度限制在 `atttypmod` 上表现为 `-1` | 已在 `02_data_types.sql` 中处理，判断 `atttypmod = -1` 而非 `format_type` 字符串匹配长度 |
| 分区子表本身也可能是"大表"，会与父表重复统计 | `04_large_tables_partition.sql` 已用 `NOT EXISTS (pg_inherits ...)` 排除子分区，只统计顶层对象 |
| Oracle / MySQL 兼容模式下 `format_type()` 返回值偏离 PG 风格 | 在报告中对字段类型相关 issue 加注"兼容模式需复核"，不要直接扣分到底 |
| 启用了 oracle 模式时，时间字段可能用 `DATE`（映射到 `timestamp without time zone`）会被正常识别；金额可能用 `NUMBER(10,2)`（映射到 `numeric`） | 大概率不影响；但若大批量出现 type 不匹配警告，结合 `server_version` 与 `compatible_mode` GUC 复核 |
| 部分实例（如部署在裸金属或容器内）不开放 `pg_stat_activity`/`pg_monitor` 等权限 | 按 `references/permission-requirements.md` 建议客户单独授权，或在报告中如实标注"权限不足" |
| 密码不应出现在 `ps aux`、shell 历史或日志中 | 统一通过 `PGPASSWORD` 环境变量传递，脚本内不 `echo` 密码，不将连接串写入日志文件 |
| 用户使用金仓命名习惯（KINGBASE_* 变量） | 一律拒绝改回 PG 变量，明确告知"金仓兼容 PG 客户端，沿用 PG 变量" |

## 注意事项

- 本 skill 面向"设计与风险审查"，不涉及任何写操作，不做自动修复，所有修复建议仅为文字建议，
  由用户自行评估执行。
- 大规模实例（数百个数据库/数万张表）建议先与用户确认是否限定数据库子集，避免单次扫描
  耗时过长；`run_audit.sh` / `run_audit.py` 均支持 `-d db1,db2` 指定子集。
- 若目标实例为生产环境，建议提示用户选择业务低峰期执行（`pg_total_relation_size` 等函数
  对超大表会有一定 I/O 开销，但均为只读、不加排他锁）。
- 报告中的"人工复核"标记不可省略或替用户下结论，这是保证审查专业性和可信度的关键约束。
- 推荐在执行本 skill 之后，使用 KingbaseES 原生治理工具落地整改：
  - 在线收缩大表：`sys_squeeze` 扩展（基于逻辑解码，类似 pg_squeeze）
  - 在线重建表：`sys_repack` 命令行工具
  - 表 / 索引膨胀定量：`pg-find-bloat` 已对应 `kingbase-find-bloat` / 直接走 `pg-stat-snapshot`
  - 性能画像：`sys_stat_statements`（金仓名为 sys_stat_statements，对应 PG `pg_stat_statements`）
  - 自动快照：`sys_kwr`（类似 Oracle AWR）
