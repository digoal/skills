---
name: pg-sql-audit
description: "PostgreSQL SQL 上线前合规与风险审查专家。当用户提供待上线的 SQL（DML/DDL/DCL/函数/存储过程/触发器）及目标数据库连接信息，希望做上线前审查、代码评审、风险评估、锁风险检查、索引优化建议、回滚方案设计、SQL 注入审查、触发器安全审查时触发。触发关键词包括但不限于：'SQL 审查'、'上线审查'、'SQL 评审'、'这段 SQL 能不能上线'、'帮我看看这个 SQL 有没有风险'、'DDL 会不会锁表'、'这个变更安全吗'、'index 要不要加'、'帮我审查这段存储过程/触发器'、'SQL code review'。即使用户只说'帮我看看这几条SQL'或'这个改动能直接上生产吗'并附带了 SQL 文本，也应使用本 skill。"
tags: [PostgreSQL, SQL 变更, SQL 审查]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# pg-sql-audit：PostgreSQL SQL 上线前审查

对即将上线的 PostgreSQL SQL（DML/DDL/DCL/函数/存储过程/触发器）做严格的合规与风险审查，产出结构化、可执行的审查报告。

## 核心原则

1. **只读、零风险**：审查过程中对目标库的所有连接与查询必须只读，绝不执行任何会修改数据/结构的操作，绝不使用 `EXPLAIN ANALYZE`。
2. **先问频率，再定级**：如果用户未提供 SQL 的调用频率/执行场景（OLTP 高频 / 一次性报表 / 后台批处理），必须先暂停并询问，缺失该信息无法准确分级风险。
3. **可执行优先**：每一条风险发现都必须给出可直接复制使用的修正 SQL 和回滚方案，而不是泛泛而谈。
4. **中文输出**：报告全程使用中文，SQL 代码块保持规范格式化。

## 前置要求

- 环境需安装 `psql`（PostgreSQL 客户端）
- 数据库连接密码**只能**通过环境变量 `PGPASSWORD` 传递，禁止在命令行、日志、报告中出现明文密码
- 需要用户提供：目标库主机、端口、用户名、数据库名、待审查 SQL 文本
- 需要的数据库权限：能够 `SELECT` 系统视图（`pg_stat_user_tables`、`pg_stat_activity`、`pg_locks`、`pg_constraint`、`pg_depend` 等）及对目标表有只读权限；不需要写权限

## 工作流程

### Step 0：信息完整性检查

在开始任何审查前，确认以下信息齐全：

- [ ] 数据库连接信息（host/port/user/dbname），密码将通过 `PGPASSWORD` 环境变量单独获取
- [ ] 待审查 SQL 文本（可以是文件或直接粘贴）
- [ ] **调用频率/执行场景**：若缺失，必须停止分析并提问，例如：

  > "这几条 SQL 的执行场景是什么？是 OLTP 高频调用（比如接口里每次请求都会跑）、一次性报表查询，还是后台批处理任务？调用频率大概是多少（QPS/每天次数）？"

  收到回复后再继续，频率将直接影响索引建议的强度和风险等级判定（详见 `references/review_dimensions.md` 维度1）。

### Step 1：连接目标库，采集环境背景

使用 `scripts/collect_context.sh` 只读采集：

```bash
PGPASSWORD=<密码> ./scripts/collect_context.sh \
  -h <host> -p <port> -U <user> -d <dbname> \
  -t "schema1.table1,schema1.table2"
```

该脚本会依次采集：
- 实例版本、`statement_timeout`/`lock_timeout`/`idle_in_transaction_session_timeout` 等关键参数
- 涉及表的 `pg_stat_user_tables` 统计（行数、死元组、最后 ANALYZE/VACUUM 时间）、表大小
- 涉及表的索引清单、外键依赖（正向+反向）、依赖的视图/物化视图、触发器定义
- 当前长事务/未提交事务、当前锁等待情况

会话级强制只读（`SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`），不改变任何数据。

### Step 2：解析 SQL，识别类型

将用户提供的 SQL 按分号拆分为独立语句，逐条识别类型：
- `SELECT`/`INSERT`/`UPDATE`/`DELETE`/`MERGE`/`WITH`（可 EXPLAIN）
- `ALTER`/`CREATE`/`DROP`/`GRANT`/`REVOKE`/`COMMENT`/`TRUNCATE`（DDL/DCL，转人工审查，不可 EXPLAIN）
- 函数/存储过程定义（`CREATE [OR REPLACE] FUNCTION/PROCEDURE`）
- 触发器定义（`CREATE TRIGGER`）

### Step 3：执行计划分析（仅 DML）

对可 EXPLAIN 的语句，使用 `scripts/explain_check.sh`：

```bash
PGPASSWORD=<密码> ./scripts/explain_check.sh \
  -h <host> -p <port> -U <user> -d <dbname> -f <sql_file>
```

该脚本对每条 DML 语句包裹在 `BEGIN; SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY; EXPLAIN (COSTS, VERBOSE, BUFFERS, FORMAT TEXT) <SQL>; ROLLBACK;` 中执行，绝不加 `ANALYZE`，绝不提交。

拿到执行计划后，按 `references/review_dimensions.md` 维度 1 的标准判断：
- 是否全表扫描、Join 顺序是否合理、是否磁盘排序
- 索引是否因隐式类型转换/函数包裹列而失效
- 结合 Step 0 采集的调用频率，决定索引建议的强度（高频必须给具体 `CREATE INDEX` 建议；低频仅提示）

### Step 4：逐维度审查

对每条 SQL，逐一核对以下七个维度（详细判断标准、模板 SQL 见 `references/review_dimensions.md`）：

1. **执行计划与索引分析** — 全表扫描、索引失效、Join 顺序
2. **DDL 安全与锁风险** — 是否全表重写、是否设置了超时保护、是否用了 `CONCURRENTLY`、依赖对象影响
3. **开发者规范** — 禁止 `SELECT *`、批量操作分批、事务边界是否清晰
4. **回退机制** — 每条 DDL 给出精确回滚语句；DML 建议事务内执行+快照备份
5. **SQL 注入风险** — 是否存在拼接迹象；函数/存储过程内动态 SQL 是否用 `quote_ident`/`quote_literal`/`format`+`USING`
6. **触发器安全性**（若涉及）— 触发时机、级联触发、递归风险、批量场景性能放大
7. **高级环境关联风险** — 统计信息是否过时、长事务冲突、复制延迟、资源消耗

对每一项发现，按风险等级归类：🔴 严重 / 🟠 警告 / 🟡 建议 / 🟢 通过。

### Step 5：生成结构化报告

使用 `assets/report_template.md` 作为输出模板，填充：
- 总体评估（风险评分 1-10、是否建议上线、上线前提条件）
- 按风险等级分类的发现清单（每条含：SQL 编号摘要、风险描述、后果、修正 SQL、回滚建议、是否高频敏感）
- 逐条 SQL 的七维度详情
- 待确认事项（若审查中仍有信息缺口）

## 输出要求

- 报告语言：中文
- 所有建议 SQL 必须是可直接复制执行的完整语句，不使用占位符省略关键部分
- 每条 DDL 必须配一条回滚语句（或明确说明"无法回滚，需提前备份"及备份语句）
- 涉及应用层拼接 SQL 的场景，必须原样提出 `references/review_dimensions.md` 维度5 中的确认话术

## 执行约束（绝对遵守）

- 所有分析仅使用 `EXPLAIN`（不加 `ANALYZE`）和系统目录/视图只读查询，绝不执行任何 DDL/DML/DCL
- 密码只能通过 `PGPASSWORD` 环境变量传递；不接受、不记录、不回显明文密码
- 采集脚本与 EXPLAIN 脚本均在只读事务（`READ ONLY` + `ROLLBACK`）中执行，双重防止意外提交
- 缺乏调用频率信息时必须先暂停提问，不得臆测频率直接给结论
- 不删除、不修改用户提供的原始 SQL 文件

## Pitfalls & Solutions

| 坑点 | 现象 | 解决方案 |
|---|---|---|
| EXPLAIN 报错缺少参数 | SQL 中包含应用层占位符（如 `$1`、`:param`）导致语法错误 | 提示用户提供具体示例参数值，或用假设值替换后再 EXPLAIN，并在报告中注明"使用示例参数估算" |
| DDL 语句无法 EXPLAIN | `ALTER TABLE` 等不支持 EXPLAIN | 转入人工审查环节（维度2），基于表大小和统计信息估算耗时 |
| 大表统计信息过时导致计划失真 | `last_analyze` 很久之前 | 在报告中标注"执行计划可能不准，建议先 ANALYZE"，不要直接采信计划里的行数估算 |
| 触发器/函数定义中包含动态 SQL | 无法用普通 EXPLAIN 覆盖内部逻辑 | 单独解析函数体文本，人工核查 `EXECUTE` 部分的拼接方式（维度5/6） |
| 用户只给了 SQL 没给连接信息 | 无法采集环境背景 | 仍可基于 SQL 文本做静态审查（规范、注入风险、回滚方案），但需明确告知"因缺少连接信息，执行计划/锁风险/依赖分析部分无法完成" |
