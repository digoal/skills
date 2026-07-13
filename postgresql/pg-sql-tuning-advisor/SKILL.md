---
name: pg-sql-tuning-advisor
description: "以 PostgreSQL DBA 专家视角，给定一条 SQL 及目标实例的连接串/用户名密码，连接实例分析执行计划（EXPLAIN / EXPLAIN ANALYZE），结合表定义、索引定义、约束、统计信息（pg_stats）与相关 GUC 参数（work_mem、shared_buffers、effective_cache_size、random_page_cost 等），给出可落地的 SQL 优化建议（索引建议、SQL 改写、参数调整、统计信息维护、分区建议）。触发条件：用户提到\"SQL 优化\"、\"执行计划分析\"、\"这条 SQL 慢\"、\"帮我看看这个执行计划\"、\"explain 分析\"、\"索引建议\"、\"这个查询怎么优化\"、\"帮我调优这条 SQL\"、\"SQL tuning\"、\"慢查询分析\"，并提供了 SQL 语句 + 数据库连接信息（连接串/host+port+dbname+user+password）。即使用户只说\"帮我看看这条 SQL 为什么慢\"并附上连接串，也应使用本 skill。若 SQL 是 DML（INSERT/UPDATE/DELETE/MERGE），本 skill 强制要求在事务中执行、加语句超时后回滚，绝不提交；若 SQL 含 $1/$2 等绑定变量，本 skill 会主动构造合理示例参数或与用户确认后再取执行计划。"
tags: [PostgreSQL, SQL, 优化]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# PostgreSQL SQL 调优顾问

给定一条 SQL 和一个 PostgreSQL 实例的连接信息，像资深 DBA 一样：拿到真实执行计划 → 结合库内对象定义与运行参数 → 定位瓶颈 → 给出可执行、可回滚验证的优化建议。核心原则是**安全第一，绝不对生产数据造成副作用**。

## 前置要求

- 目标机器需能访问 PostgreSQL 实例的 host:port（TCP 直连）。若在受限网络沙箱中执行，需确认出网策略允许该目标地址，否则告知用户网络不通，无法直连，改为让用户提供本地执行的 `psql`/`EXPLAIN` 输出作为替代输入。
- 优先使用 `psql`（PostgreSQL 客户端）执行；如环境没有 `psql`，可退化为 Python + `psycopg2`/`psycopg`，二选一即可，不强制安装重量级依赖。
- 连接串/密码属于敏感信息：**绝不**将密码打印到最终输出、日志文件或保存到磁盘上的 markdown 报告中；命令行中避免用明文密码触发 shell history 持久化（优先用 `PGPASSWORD` 环境变量传入单次子进程，而不是拼进命令行参数）。

## 工作流程

### Step 1：收集输入并判断 SQL 类型

需要拿到：目标 SQL 全文、连接串（host/port/dbname/user，或标准 `postgresql://` DSN）、密码。

判断 SQL 类型（决定后续安全策略）：

| 类型 | 特征 | 策略 |
|------|------|------|
| 只读查询 | `SELECT`、`WITH ... SELECT`（无 `FOR UPDATE`/`INTO`） | 可直接 `EXPLAIN ANALYZE`，风险低 |
| DML | `INSERT`/`UPDATE`/`DELETE`/`MERGE`，或带 `RETURNING`、`FOR UPDATE` 的 SELECT | 必须在事务中执行，超时保护，取到计划后强制 `ROLLBACK`，**绝不 COMMIT** |
| DDL | `CREATE`/`ALTER`/`DROP` 等 | 本 skill 不负责执行 DDL 本身，只分析"若执行该 DDL 对现有查询计划的影响"，如需真实执行必须与用户二次确认且不属于本 skill 范围 |

如果 SQL 中包含 `$1`、`$2` 等绑定变量（说明来自应用层 prepared statement）：

1. 优先询问用户这些变量在生产中的典型取值（哪怕是示例值），因为 PostgreSQL 12+ 的执行计划会因参数值的选择性不同而变化（尤其是 `custom plan` vs `generic plan`）；
2. 若用户无法提供或希望你自己判断，通过以下方式合理构造：
   - 查看该列的 `pg_stats.most_common_vals`（高频值，测试"命中"场景）和一个不在 MCV 中的边界值（测试"稀疏"场景），两者都跑一遍计划，说明选择性对计划的影响；
   - 对于日期/时间类型，取近 7 天内的典型值；
   - 明确在最终报告中注明"该参数值为按统计信息自动推断，非真实业务值，如与实际分布差异较大结论可能失真"。
3. 用 `EXPLAIN EXECUTE`（先 `PREPARE`）或直接把参数值内联替换后 `EXPLAIN`，两种方式任选，但必须在报告中说明用的是哪种取值。

### Step 2：建立安全连接会话

统一先设置会话级超时，防止任何计划外的长时间阻塞或全库雪崩：

```sql
SET statement_timeout = '30s';           -- 单条语句超时，按 SQL 预估复杂度调整，默认不超过 60s
SET lock_timeout = '5s';                 -- 拿不到锁就放弃，避免锁等待链
SET idle_in_transaction_session_timeout = '15s';  -- 防止事务忘记提交/回滚导致长事务
```

超时时长的选择：先跑一次 `EXPLAIN`（不带 ANALYZE，仅评估计划，不实际执行）估算数据量级，再决定 `ANALYZE` 阶段给多长超时；对未知大表，从保守值（如 5~10s）开始，超时则如实告知用户"该语句在当前超时阈值内无法跑完真实执行，以下基于纯计划估算给出建议"，不要一味调大超时去"硬跑出结果"。

### Step 3：获取执行计划

**只读 SELECT：**

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT) <原始 SQL>;
```

若用户明确不希望真实执行（例如涉及大表全表扫描、代价过高），改用：

```sql
EXPLAIN (VERBOSE, FORMAT TEXT) <原始 SQL>;
```

仅拿到估算计划（无真实耗时/buffers），并在报告中注明这一点。

**DML（INSERT/UPDATE/DELETE/MERGE）— 强制走事务 + 回滚，绝不提交：**

```sql
BEGIN;
SET LOCAL statement_timeout = '10s';   -- 事务内单独设置，比会话级更保守
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT) <原始 DML>;
ROLLBACK;   -- 无论成功/失败/超时，都必须回滚，不允许 COMMIT
```

执行细节：

- 用同一个数据库连接/同一个事务块跑完 `BEGIN → EXPLAIN ANALYZE → ROLLBACK` 三步，中间不能断开连接（断开会自动回滚，效果等价，但要在报告中确认最终连接状态确实已回滚/已断开）；
- 如果语句触发超时中断，`ROLLBACK` 仍要执行（事务已因超时被标记为 aborted，`ROLLBACK` 用于清理该事务，这是正常且必需的收尾动作）；
- 对高风险 DML（无 WHERE 条件的 UPDATE/DELETE、影响行数预估很大），先跑一次纯 `EXPLAIN`（不 ANALYZE）看预估影响行数，行数异常大时向用户确认是否仍要继续做 `ANALYZE` 真实执行测算，避免长事务占锁；
- 绝不使用会跳过回滚的写法（例如让脚本在拿到结果前异常退出导致连接池自动提交等不确定行为）——用显式的 `ROLLBACK` 语句，不依赖连接断开的隐式行为。

**DDL：** 不实际执行，仅基于目标表/索引当前定义 + 统计信息做"假设性分析"（例如"如果加这个索引，计划预计会变成……"），可以用 `hypopg` 扩展（如果实例已安装）做假设索引验证；未安装 `hypopg` 则明确说明这是基于经验的推断，不是实测。

### Step 4：采集上下文对象定义与参数

围绕 SQL 涉及的每张表，采集：

```sql
\d+ <table>                    -- 列、类型、索引、约束、存储参数（含 fillfactor、toast）
SELECT * FROM pg_stats WHERE tablename = '<table>' AND attname IN (...涉及的列...);
SELECT relpages, reltuples, relkind FROM pg_class WHERE relname = '<table>';
SELECT pg_size_pretty(pg_total_relation_size('<table>'));
SELECT last_vacuum, last_autovacuum, last_analyze, last_autoanalyze, n_dead_tup, n_live_tup
  FROM pg_stat_user_tables WHERE relname = '<table>';
```

围绕计划中出现的问题节点，按需采集相关 GUC（会话级 `SHOW` 或 `SELECT name, setting, unit FROM pg_settings WHERE name IN (...)`）：

- 内存类：`work_mem`、`shared_buffers`、`effective_cache_size`、`maintenance_work_mem`、`hash_mem_multiplier`
- 代价模型类：`random_page_cost`、`seq_page_cost`、`cpu_tuple_cost`、`cpu_index_tuple_cost`、`effective_io_concurrency`
- 并行类：`max_parallel_workers_per_gather`、`parallel_setup_cost`、`parallel_tuple_cost`、`min_parallel_table_scan_size`
- 计划器行为类：`enable_seqscan`/`enable_nestloop`/`enable_hashjoin` 等开关（仅用于诊断对比，不建议长期关闭）、`jit`、`jit_above_cost`
- 版本信息：`SELECT version();`（不同大版本的优化器行为、并行能力、增量排序等特性差异很大，结论必须结合版本）

详细速查表见 `references/guc_checklist.md`。

### Step 5：诊断执行计划

对照 `references/plan_diagnostics.md` 中的诊断清单逐项排查，重点关注：

1. **估算行数 vs 实际行数偏差**（`rows=X` vs `actual rows=Y`，偏差超过一个数量级）→ 通常是统计信息过期（看 `last_analyze`）或列间相关性未被捕捉（考虑扩展统计 `CREATE STATISTICS`）；
2. **顺序扫描出现在大表上** 且上层有强选择性过滤条件 → 检查是否缺索引、索引是否因函数/类型转换失效（如 `WHERE col::text = ...`）；
3. **Nested Loop 驱动行数被严重低估** 导致对内表反复扫描 → 建议改写为 Hash Join 友好写法或修正统计信息；
4. **Sort/Hash 出现 "Disk" 而非 "Memory"**（`Sort Method: external merge  Disk: ...`）→ `work_mem` 不足，建议按会话/语句级 `SET work_mem` 而非直接改全局，避免连接数放大后内存耗尽；
5. **Bitmap Heap Scan 中 "Recheck" 比例很高** → `work_mem` 不够导致 bitmap 有损，或统计信息不准；
6. **JIT 编译耗时占比高但收益低**（小查询却触发 JIT）→ 检查 `jit_above_cost` 阈值设置是否合理；
7. **并行度未生效**（预期该走并行但计划里没有 `Workers Planned`）→ 检查 `max_parallel_workers_per_gather`、表是否够大过了并行扫描阈值、是否有并行不安全的函数；
8. **CTE / 子查询被物化导致重复计算或丢失下推条件**（关注 `MATERIALIZED`/`NOT MATERIALIZED` 提示，PG12+ 默认行为有变化）。

### Step 6：给出优化建议

建议必须按"预期收益—改动成本—风险"三维排序，且明确区分：

- **零风险类**：`ANALYZE <table>` 更新统计信息、创建扩展统计 `CREATE STATISTICS`；
- **低风险类**：会话/语句级 `SET work_mem` 调整、SQL 改写（不改变语义，附带改写前后对比）；
- **需评审类**：新建索引（给出 `CREATE INDEX CONCURRENTLY` 语句，说明索引大小估算、写放大代价、对现有写入路径的影响）、分区改造；
- **需业务确认类**：修改全局 GUC、修改表结构（加列/改约束）。

每条建议都要给出可复制的 SQL，并尽量给出"预期计划会如何变化"的推理依据（而不是空泛地说"加个索引应该会快"）。

## 输出格式

```markdown
# SQL 调优报告：<一句话概括这条 SQL 做什么>

## 基本信息
- 实例版本 / 目标表 / 语句类型（只读 / DML，已确认执行后已回滚）

## 执行计划摘要
（贴关键的 EXPLAIN ANALYZE 片段，标注问题节点）

## 问题定位
1. ...
2. ...

## 优化建议（按优先级）
### 建议 1：<标题>（预期收益：高/中/低，风险：低/中/高）
- SQL / 参数变更
- 依据

## 验证方式
（建议用户如何在测试环境验证，如再次 EXPLAIN ANALYZE 对比）
```

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|------|----------|
| DML 直接 EXPLAIN ANALYZE 会真实修改数据 | 必须 `BEGIN` + `SET LOCAL statement_timeout` + `ROLLBACK`，全程不 COMMIT |
| 大表 EXPLAIN ANALYZE 直接跑爆连接 / 长时间阻塞 | 先跑纯 `EXPLAIN` 估算代价，超时阈值从小到大试探，不要一上来给很长超时 |
| 参数化 SQL（`$1`）计划因参数值剧烈变化 | 用 MCV 值与非 MCV 值各测一次，说明选择性对计划的影响；不要只测一个"看起来正常"的值就下结论 |
| 密码明文出现在命令行 / 日志 / 报告中 | 用 `PGPASSWORD` 环境变量传递，报告和过程输出中一律脱敏为 `****` |
| 统计信息过期导致估算行数严重失真 | 检查 `pg_stat_user_tables.last_analyze`，必要时先 `ANALYZE` 再重新取计划对比 |
| 单纯调大 `work_mem` 全局生效 | 全局调大会按并发连接数线性放大内存占用，优先建议会话/语句级 `SET work_mem`，全局调整需评估最大连接数 |
| 高危 DML 无 WHERE 条件 | 先看纯 EXPLAIN 的预估影响行数，异常大时向用户确认再决定是否做 ANALYZE 真实测算 |

## 注意事项

- **DML 语句执行前必须设置语句超时，且必须在事务中执行，拿到 EXPLAIN ANALYZE 结果后必须 ROLLBACK，绝不 COMMIT。** 这是本 skill 的硬性红线，任何情况下都不能省略。
- 连接信息（密码）只在本次会话内存中使用，不写入任何持久化文件（包括最终 markdown 报告、脚本参数文件）。
- 不对生产实例执行任何 DDL 或真正提交的数据变更；如用户明确要求执行建议的 DDL（如建索引），需在报告中给出语句由用户自行执行，或在用户二次明确确认"现在就执行"后才可代为执行，且优先用 `CONCURRENTLY` 降低锁影响。
- 网络不可达目标实例时，如实告知用户，转而请求用户在本地跑 `EXPLAIN` 命令并粘贴结果作为替代输入，不要编造执行计划。
- 涉及多张大表、复杂 CTE 的 SQL，诊断可能需要多轮采集（先看整体计划定位问题节点，再针对性采集该节点相关表/索引/参数），不要一次性无差别采集所有对象信息。
