---
name: pg-design-audit
description: "PostgreSQL 资深 DBA/架构审查专家能力。给定实例连接信息（主机、端口、用户名、密码），对实例内所有数据库做全面只读扫描，找出设计不规范或存在潜在使用风险的对象和模式。触发场景：用户提到\"数据库设计审查\"、\"PG 实例体检\"、\"帮我审查一下这个库\"、\"数据库规范检查\"、\"表结构有没有问题\"、\"索引设计审查\"、\"命名规范检查\"、\"字段类型是否合理\"、\"有没有缺主键的表\"、\"大表要不要分区\"、\"冗余索引/未使用索引检查\"、\"给我一份数据库健康评分\"，或提供了 PostgreSQL 的 host/port/user/password 并希望做全面体检。即使用户只说\"帮我看看这个 PG 库设计得怎么样\"或\"这个实例有什么问题\"，只要给出了连接信息，也应使用本技能。"
tags: [PostgreSQL, 设计检查, 设计规范检查]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# PostgreSQL 设计与风险审查（pg-design-audit）

对一个 PostgreSQL 实例的所有数据库做 7 大类只读扫描（命名规范、字段类型、注释缺失、大表分区、
索引设计、约束默认值、库级配置），产出按 🔴/🟡/🔵 三级风险分类的 Markdown 审查报告，
含问题总览表、综合健康评分（百分制）与 Top 10 整改建议。

## 前置要求

- 目标实例可通过网络访问，且提供了 host、port、user、password（以及可选的目标数据库列表，
  默认扫描实例内全部非模板、允许连接的数据库）。
- 执行环境已安装 `psql` 客户端（PostgreSQL 官方命令行工具）。
- 审计账号至少具备 `CONNECT` 权限；若需要完整的索引使用统计/表体积统计，建议被扫描实例
  为审计账号授予 `pg_monitor` 内置角色（只读，不含任何写权限）。详见
  `references/permission-requirements.md`。
- **密码处理**：仅通过环境变量 `PGPASSWORD` 传入，不写入脚本、不写入日志、不回显在终端历史中。
  会话结束后建议 `unset PGPASSWORD`。

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

确认连接成功、记录 PostgreSQL 大版本（不同版本部分系统视图有差异，例如 `pg_stat_user_indexes`
在所有受支持版本均可用，但 `data_checksums` 需 PG 12+；PG 15+ 默认收紧了 `public` 模式的
`CREATE` 权限，7.4 检查项的解读需结合版本判断）。

### Step 2：发现待扫描数据库

执行 `scripts/queries/00_list_databases.sql`，得到实例内所有 `datistemplate = false`
且 `datallowconn = true` 的数据库。若用户指定了数据库子集，仅扫描该子集。

### Step 3：对每个数据库执行 7 大类只读检查

优先使用编排脚本一次性完成（推荐）：

```bash
chmod +x scripts/run_audit.sh
PGPASSWORD='<password>' scripts/run_audit.sh -h <host> -p <port> -U <user> \
  [-d db1,db2] -o ./pg_audit_output
```

该脚本会对每个数据库依次执行以下查询文件，并将结果落盘到
`./pg_audit_output/<db>/<查询文件名>.txt`（stderr 落盘到同名 `.err`，用于识别权限不足）：

| 文件 | 检查类别 |
|---|---|
| `01_naming.sql` | 对象/字段/索引命名规范 |
| `02_data_types.sql` | 字段类型选择合理性（布尔/时间/JSON/PK-FK类型/超长文本/金额/IP） |
| `03_comments.sql` | 表/视图/字段注释缺失统计（含缺失率） |
| `04_large_tables_partition.sql` | 超过 1GB 大表、是否分区、分区数是否超过100 |
| `05_index_design.sql` | 重复索引、冗余前缀索引、未使用索引、宽索引 |
| `06_constraints_defaults.sql` | 缺主键、缺审计时间戳、外键缺索引、应有约束的可空字段 |
| `07_db_config.sql` | 事务隔离级别、数据校验和、public 模式建表与权限 |

若无法使用脚本（如仅有交互式数据库工具而非 shell），可手动对每个数据库依次执行
`scripts/queries/` 下各 `.sql` 文件，效果等价。

### Step 4：解析结果、映射风险等级

读取 `pg_audit_output/` 下所有文本结果，对照 `references/risk-scoring-map.md` 中的
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

将生成的报告文件与 `pg_audit_output/` 原始扫描结果一并提供给用户，并口头提示：
本次扫描的高危项数量、涉及数据库数、以及最值得优先处理的 1-2 个问题。

## 输出格式要求（复述执行约束，务必遵守）

- 风险分三级：🔴 高危（直接影响数据正确性/性能）、🟡 警告（增加维护成本/隐患）、
  🔵 建议（影响可维护性）。
- 每一项包含：数据库名、Schema 名、对象名、问题描述、当前情况、潜在风险、修复建议。
- 结尾必须包含：问题总览表、综合健康评分、Top 10 整改建议。

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|---|---|
| "未使用索引"判断基于 `idx_scan=0`，但集群刚重启或统计刚 reset 会导致误判 | 查询 `pg_stat_database.stats_reset`，若距今不足 7 天，在该项旁标注"统计时间过短，需人工复核"，不直接建议删除 |
| 主键/唯一索引即使 `idx_scan=0` 也不代表可删除 | 单独查询区分 `unused_unique_or_pk_index_review_needed`，不计入常规冗余索引扣分 |
| varchar 无长度限制在 `atttypmod` 上表现为 `-1` | 已在 `02_data_types.sql` 中处理，判断 `atttypmod = -1` 而非 `format_type` 字符串匹配长度 |
| 分区子表本身也可能是"大表"，会与父表重复统计 | `04_large_tables_partition.sql` 已用 `NOT EXISTS (pg_inherits ...)` 排除子分区，只统计顶层对象 |
| 部分实例（如托管云 RDS）不开放 `pg_stat_activity`/`pg_monitor` 等权限 | 按 `references/permission-requirements.md` 建议客户单独授权，或在报告中如实标注"权限不足" |
| 密码不应出现在 `ps aux`、shell 历史或日志中 | 统一通过 `PGPASSWORD` 环境变量传递，脚本内不 `echo` 密码，不将连接串写入日志文件 |
| PG 15+ 默认收紧了 `public` 模式的 `CREATE` 权限，7.4 检查项在新旧版本上结论不同 | Step 1 记录 PG 大版本，Step 4 解读 `public_role_can_create` 时结合版本号判断是否属实际风险 |

## 注意事项

- 本技能面向"设计与风险审查"，不涉及任何写操作，不做自动修复，所有修复建议仅为文字建议，
  由用户自行评估执行。
- 大规模实例（数百个数据库/数万张表）建议先与用户确认是否限定数据库子集，避免单次扫描
  耗时过长；`run_audit.sh` 支持 `-d db1,db2` 指定子集。
- 若目标实例为生产环境，建议提示用户选择业务低峰期执行（`pg_total_relation_size` 等函数
  对超大表会有一定 I/O 开销，但均为只读、不加排他锁）。
- 报告中的"人工复核"标记不可省略或替用户下结论，这是保证审查专业性和可信度的关键约束。
