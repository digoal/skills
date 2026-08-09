---
name: kingbase-sql-tuning-advisor
description: "以 KingbaseES（金仓）DBA 专家视角，给定一条 SQL 及目标金仓实例的连接信息，连接实例分析执行计划（EXPLAIN / EXPLAIN ANALYZE），结合表定义、索引定义、约束、统计信息（pg_stats）与相关 GUC 参数（work_mem、shared_buffers、effective_cache_size、random_page_cost 等），给出可落地的 SQL 优化建议（索引建议、SQL 改写、参数调整、统计信息维护、分区建议）。触发条件：用户提到\"金仓SQL优化\"、\"金仓执行计划分析\"、\"这条 SQL 慢\"、\"帮我看看这个执行计划\"、\"explain 分析\"、\"索引建议\"、\"这个查询怎么优化\"、\"帮我调优这条金仓 SQL\"、\"SQL tuning\"、\"慢查询分析\"、\"KingbaseES 调优\"，并提供了 SQL 语句 + 金仓实例连接信息（host/port/dbname/user/password）。即使用户只说\"帮我看看这条 SQL 在金仓上为什么慢\"并附上连接串，也应使用本 skill。默认假设金仓实例运行在 PG 兼容模式（database_mode=pg）。若 SQL 是 DML（INSERT/UPDATE/DELETE/MERGE），本 skill 强制要求在事务中执行、加语句超时后回滚，绝不提交；若 SQL 含 $1/$2 等绑定变量，本 skill 会主动构造合理示例参数或与用户确认后再取执行计划。"
tags: [KingbaseES, 金仓, SQL 优化, 执行计划]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# kingbase-sql-tuning-advisor：KingbaseES（金仓）SQL 调优顾问

给定一条 SQL 和一个金仓实例的连接信息，像资深 DBA 一样：拿到真实执行计划 → 结合库内对象定义与运行参数 → 定位瓶颈 → 给出可执行、可回滚验证的优化建议。本技能是 pg-sql-tuning-advisor 的金仓移植版，全部脚本与 SQL 已在 KingbaseES V009R001C010（PG 兼容模式）实测通过。

## 与 PostgreSQL 的兼容性说明（金仓差异，务必先读）

KingbaseES 默认采用 PG 兼容模式（`database_mode=pg`，对应 PG 12 语义，`server_version_num=120001`），因此本技能使用的系统目录/视图与 PostgreSQL 完全一致：`pg_stats`、`pg_stat_user_tables`、`pg_class`、`pg_indexes`、`pg_constraint`、`pg_settings` 等均可直接复用。以下为金仓特有差异，调优时必须注意：

| 项目 | PostgreSQL | KingbaseES（本技能按此执行） |
|---|---|---|
| 统计语句视图 | `pg_stat_statements` | `sys_stat_statements`（金仓版，位于 `public` schema，实测可查；`pg_stat_statements` 默认不存在） |
| 主配置文件 | `postgresql.conf` | `kingbase.conf`（用 `SHOW config_file;` 确认实际路径） |
| EXPLAIN 选项 | `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT)` | 语法兼容，实测可用；`BUFFERS` 必须配 `ANALYZE`（与 PG 12 相同） |
| `hash_mem_multiplier` | PG13+ 可用 | **V9R1C10 实测不存在**（PG12 兼容版无此参数），Hash 溢盘只能调 `work_mem` |
| 假设索引扩展 | `hypopg` | **V9R1C10 默认不提供**（`pg_available_extensions` 实测无），无法做假设索引实测，只能基于经验推断计划变化 |
| 在线建索引 | `CREATE INDEX CONCURRENTLY` | 实测支持，但同样**不能在事务块内执行**，必须单独会话/单独 `psql -c` |
| 扩展统计 | `CREATE STATISTICS` | 实测支持（`CREATE STATISTICS s ON a, b FROM t;` 可用） |
| 会话超时参数 | `statement_timeout`/`lock_timeout`/`idle_in_transaction_session_timeout` | 实测均可设置 |
| 客户端 | psql / psycopg2 / psycopg3 | PG 的 psql 可直接连接金仓 V9；python 驱动实测兼容 |
| 其他 | | `WITH ... NOT MATERIALIZED`、`SET LOCAL`、`SET TRANSACTION READ ONLY`、plpgsql `DO $$` 均已实测兼容 |

## 核心原则

1. **安全第一，绝不对生产数据造成副作用**：只读 SELECT 可直接 `EXPLAIN ANALYZE`；DML（INSERT/UPDATE/DELETE/MERGE）必须 `BEGIN` + `SET LOCAL statement_timeout` + `EXPLAIN ANALYZE` + **无条件 `ROLLBACK`**，绝不 COMMIT——`EXPLAIN ANALYZE` 会真实执行语句，事务回滚是唯一防线。
2. **先估算，再实测**：先跑一次不带 ANALYZE 的纯 `EXPLAIN` 估算代价/影响行数，再决定是否做真实 `ANALYZE` 测算；对未知大表从保守超时开始，不硬跑。
3. **可执行优先**：每条建议都要给出可复制的 SQL 和\"计划会如何变化\"的推理依据，按\"预期收益—改动成本—风险\"排序。
4. **中文输出**：报告全程使用中文，SQL 代码块保持规范格式化。

## 连接约定

按以下优先级解析连接参数（脚本已内置该逻辑，无需手工逐项传递）：

1. **用户明确提供的连接参数**（host/port/user/password/dbname，命令行参数优先）；
2. **环境变量** `PGHOST` `PGPORT` `PGUSER` `PGPASSWORD` `PGDBNAME`（`PGDATABASE` 作为 `PGDBNAME` 的等价别名）。脚本同时兼容金仓手册风格的 `KINGBASEHOST`/`KINGBASE_HOST`/`KINGBASEPORT`/`KINGBASE_PORT`/`KINGBASEUSER`/`KINGBASE_USER`/`KINGBASEPASSWORD`/`KINGBASE_PASSWORD` 等变体作为兜底；
3. **缺省值**：`PGHOST=127.0.0.1 PGPORT=5432 PGDBNAME=kingbase PGUSER=kingbase PGPASSWORD=123456`。

```bash
export PGHOST=127.0.0.1 PGPORT=5432 PGDBNAME=kingbase PGUSER=kingbase PGPASSWORD=123456
```

> 密码在 shell 通道**只能**通过环境变量 `PGPASSWORD` 传递，禁止在命令行、日志、报告中出现明文密码；python 通道可用 `--password` 参数，但同样推荐使用 `PGPASSWORD`。连接信息只在本次会话内存中使用，不写入任何持久化文件。

## 前置要求

- 可用的金仓连接通道，二选一：
  - `psql`（实测 PG 的 psql 可直接连接金仓 V9；金仓自带的 `ksql` 亦可）；
  - Python `psycopg2` 或 `psycopg[binary]`（psycopg3），脚本优先用 psycopg2，找不到时自动降级 psycopg3。
- 需要用户提供：目标库主机、端口、用户名、数据库名、待调优 SQL 文本。
- 需要的数据库权限：对目标表有只读权限 + 能查系统视图（`pg_stats`、`pg_stat_user_tables`、`pg_class`、`pg_indexes`、`pg_settings` 等）；不需要写权限（除非用户明确要求代为执行建议的 DDL）。
- 网络可达：目标机器需能访问金仓实例 host:port。若在受限网络沙箱中执行，需确认出网策略允许该目标地址，否则告知用户网络不通，无法直连，改为让用户提供本地执行的 `psql`/`EXPLAIN` 输出作为替代输入。

## 工作流程

### Step 0：收集输入并判断 SQL 类型

需要拿到：目标 SQL 全文、连接串（host/port/dbname/user）、密码。

判断 SQL 类型（决定后续安全策略）：

| 类型 | 特征 | 策略 |
|------|------|------|
| 只读查询 | `SELECT`、`WITH ... SELECT`（无 `FOR UPDATE`/`INTO`） | 可直接 `EXPLAIN ANALYZE`，风险低 |
| DML | `INSERT`/`UPDATE`/`DELETE`/`MERGE`，或带 `RETURNING`、`FOR UPDATE` 的 SELECT | 必须在事务中执行，超时保护，取到计划后强制 `ROLLBACK`，**绝不 COMMIT** |
| DDL | `CREATE`/`ALTER`/`DROP` 等 | 本 skill 不负责执行 DDL 本身，只分析\"若执行该 DDL 对现有查询计划的影响\"，如需真实执行必须与用户二次确认 |

**参数化 SQL（含 `$1`、`$2` 等绑定变量）的处理**：

1. 优先询问用户这些变量在生产中的典型取值（哪怕是示例值），因为执行计划会因参数值选择性不同而变化（custom plan vs generic plan）；
2. 若用户无法提供或希望你自己判断，通过以下方式合理构造：
   - 查看该列的 `pg_stats.most_common_vals`（高频值，测试\"命中\"场景）和一个不在 MCV 中的边界值（测试\"稀疏\"场景），两者都跑一遍计划，说明选择性对计划的影响；
   - 对于日期/时间类型，取近 7 天内的典型值；
   - 明确在最终报告中注明\"该参数值为按统计信息自动推断，非真实业务值，如与实际分布差异较大结论可能失真\"。
3. 用 `safe_explain` 脚本的 `--params` 参数内联替换 `$1/$2` 后 `EXPLAIN`，并在报告中说明用的是哪种取值。

### Step 1：建立安全连接会话

统一先设置会话级超时，防止任何计划外的长时间阻塞或全库雪崩：

```sql
SET statement_timeout = '30s';           -- 单条语句超时，按 SQL 预估复杂度调整，默认不超过 60s
SET lock_timeout = '5s';                 -- 拿不到锁就放弃，避免锁等待链
SET idle_in_transaction_session_timeout = '15s';  -- 防止事务忘记提交/回滚导致长事务
```

超时时长的选择：先跑一次纯 `EXPLAIN`（不带 ANALYZE，仅评估计划，不实际执行）估算数据量级，再决定 `ANALYZE` 阶段给多长超时；对未知大表，从保守值（如 5~10s）开始，超时则如实告知用户\"该语句在当前超时阈值内无法跑完真实执行，以下基于纯计划估算给出建议\"，不要一味调大超时去\"硬跑出结果\"。

### Step 2：获取执行计划（脚本）

使用 `scripts/safe_explain.sh`（psql 通道）或 `scripts/safe_explain.py`（python SDK 通道），**二选一，结果等价**：

```bash
# psql 通道
export PGPASSWORD=123456
./scripts/safe_explain.sh -h 127.0.0.1 -p 5432 -U kingbase -d kingbase \
  -f /tmp/test.sql                     # 只读 SELECT：直接 EXPLAIN ANALYZE
./scripts/safe_explain.sh ... -f /tmp/update.sql --dml   # DML：事务 + 回滚
./scripts/safe_explain.sh ... -f /tmp/param.sql --params '{"$1": 100}'   # 绑定变量内联替换
./scripts/safe_explain.sh ... -f /tmp/big.sql --no-analyze   # 纯计划估算（不实际执行）

# python SDK 通道（参数不传时按连接约定自动解析）
./scripts/safe_explain.py -f /tmp/test.sql
./scripts/safe_explain.py -f /tmp/update.sql --dml --timeout 10
./scripts/safe_explain.py -f /tmp/param.sql --params '{"$1": "2026-01-01"}'
```

脚本行为：

- **只读 SELECT**：`SET statement_timeout` 后执行 `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT) <sql>`；
- **DML**：`BEGIN; SET LOCAL statement_timeout = '...'; EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT) <dml>; ROLLBACK;` —— 无论成功/失败/超时，**一律 ROLLBACK，脚本不提供任何 COMMIT 路径**；若脚本中途异常退出，连接断开也会自动回滚（但要以显式 `ROLLBACK` 为主，不依赖隐式行为）；
- **`--no-analyze`**：仅 `EXPLAIN (VERBOSE, FORMAT TEXT)` 拿估算计划（无真实耗时/buffers），用于大表或高危 DML 的先行评估；
- **`--dml` 可自动识别**：脚本会剥离开头注释（`--` 行注释 / `/* */` 块注释）后按首关键字（INSERT/UPDATE/DELETE/MERGE）自动走 DML 安全路径，`--dml` 只是显式声明兜底；
- **`--params '{"$1": v, "$2": v}'`**：JSON 内联替换绑定变量，数值/布尔/null 不引号包裹，其余按字符串字面量加单引号（含 `''` 转义）；
- 高危 DML（无 WHERE 条件的 UPDATE/DELETE、预估影响行数很大）：先 `--no-analyze` 看预估影响行数，行数异常大时向用户确认是否仍要继续做 `ANALYZE` 真实执行测算。

### Step 3：采集上下文对象定义与参数

围绕 SQL 涉及的每张表，使用 `scripts/collect_context.sh` / `collect_context.py`（psql / python 二选一）一次采集：

```bash
./scripts/collect_context.sh -h 127.0.0.1 -p 5432 -U kingbase -d kingbase \
  -t "public.pgbench_accounts,public.pgbench_branches" \
  -c "aid,abalance"     # -c 指定关心的列（用于 pg_stats），可选

# python SDK 通道（等价，参数不传时按连接约定自动解析）
./scripts/collect_context.py -t "public.pgbench_accounts" -c "aid,abalance"
```

脚本依次采集（也可直接用下面的 SQL 手工执行）：

- 实例版本、`database_mode`（期望 `pg`）、`config_file`、`statement_timeout`/`lock_timeout` 等关键参数；
- 内存类：`work_mem`、`shared_buffers`、`effective_cache_size`、`maintenance_work_mem`（注意：`hash_mem_multiplier` 在 V9R1C10 不存在，勿查）；
- 代价模型类：`random_page_cost`、`seq_page_cost`、`cpu_tuple_cost`、`cpu_index_tuple_cost`、`effective_io_concurrency`；
- 并行类：`max_parallel_workers_per_gather`、`max_parallel_workers`、`parallel_setup_cost`、`parallel_tuple_cost`、`min_parallel_table_scan_size`；
- 计划器开关与 JIT：`enable_seqscan`/`enable_nestloop`/`enable_hashjoin` 等、`jit`、`jit_above_cost`；
- 每张表：列定义（含类型、not null、默认值）、索引清单（`pg_indexes`）、约束（`pg_constraint`）、`pg_class.relpages/reltuples`、表大小 `pg_total_relation_size`、`pg_stat_user_tables` 的 `last_vacuum`/`last_analyze`/`n_dead_tup`/`n_live_tup`；
- 关心列的 `pg_stats` 统计（`null_frac`、`n_distinct`、`most_common_vals` 等）；
- `sys_stat_statements` 可用性与已记录语句量（用于交叉验证该 SQL 的历史执行情况）。

详细速查表见 `references/guc_checklist.md`。

### Step 4：诊断执行计划

对照 `references/plan_diagnostics.md` 中的诊断清单逐项排查，重点关注：

1. **估算行数 vs 实际行数偏差**（`rows=X` vs `actual rows=Y`，偏差超过一个数量级）→ 通常是统计信息过期（看 `last_analyze`）或列间相关性未被捕捉（考虑扩展统计 `CREATE STATISTICS`，金仓实测支持）；
2. **顺序扫描出现在大表上** 且上层有强选择性过滤条件 → 检查是否缺索引、索引是否因函数/类型转换失效（如 `WHERE col::text = ...`）；
3. **Nested Loop 驱动行数被严重低估** 导致对内表反复扫描 → 建议改写为 Hash Join 友好写法或修正统计信息；
4. **Sort/Hash 出现 \"Disk\" 而非 \"Memory\"**（`Sort Method: external merge  Disk: ...`）→ `work_mem` 不足，建议按会话/语句级 `SET work_mem` 而非直接改全局，避免连接数放大后内存耗尽（金仓无 `hash_mem_multiplier`，Hash 溢盘只能调 `work_mem`）；
5. **Bitmap Heap Scan 中 \"Recheck\" 比例很高** → `work_mem` 不够导致 bitmap 有损，或统计信息不准；
6. **JIT 编译耗时占比高但收益低**（小查询却触发 JIT）→ 检查 `jit_above_cost` 阈值设置是否合理；
7. **并行度未生效**（预期该走并行但计划里没有 `Workers Planned`）→ 检查 `max_parallel_workers_per_gather`、表是否够大过了并行扫描阈值、是否有并行不安全的函数；
8. **CTE / 子查询被物化导致重复计算或丢失下推条件**（关注 `MATERIALIZED`/`NOT MATERIALIZED` 提示，PG12+ 默认行为有变化）。

### Step 5：给出优化建议

建议必须按\"预期收益—改动成本—风险\"三维排序，且明确区分：

- **零风险类**：`ANALYZE <table>` 更新统计信息、创建扩展统计 `CREATE STATISTICS`；
- **低风险类**：会话/语句级 `SET work_mem` 调整、SQL 改写（不改变语义，附带改写前后对比）；
- **需评审类**：新建索引（给出 `CREATE INDEX CONCURRENTLY` 语句——金仓实测支持但**不能放事务块里**，需单独会话执行；说明索引大小估算、写放大代价、对现有写入路径的影响）、分区改造；
- **需业务确认类**：修改全局 GUC、修改表结构（加列/改约束）。

每条建议都要给出可复制的 SQL，并尽量给出\"预期计划会如何变化\"的推理依据（而不是空泛地说\"加个索引应该会快\"）。金仓 V9R1C10 无 `hypopg` 扩展，假设索引/统计的验证只能基于经验推断，报告中须注明\"未经假设索引实测\"。

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
| DML 直接 EXPLAIN ANALYZE 会真实修改数据 | 必须 `BEGIN` + `SET LOCAL statement_timeout` + `ROLLBACK`，全程不 COMMIT（`safe_explain` 脚本已内置该路径） |
| 大表 EXPLAIN ANALYZE 直接跑爆连接 / 长时间阻塞 | 先跑纯 `EXPLAIN`（`--no-analyze`）估算代价，超时阈值从小到大试探，不要一上来给很长超时 |
| 参数化 SQL（`$1`）计划因参数值剧烈变化 | 用 MCV 值与非 MCV 值各测一次（`--params` 替换），说明选择性对计划的影响；不要只测一个\"看起来正常\"的值就下结论 |
| 密码明文出现在命令行 / 日志 / 报告中 | 用 `PGPASSWORD` 环境变量传递，报告和过程输出中一律脱敏为 `****` |
| 统计信息过期导致估算行数严重失真 | 检查 `pg_stat_user_tables.last_analyze`，必要时先 `ANALYZE` 再重新取计划对比 |
| 单纯调大 `work_mem` 全局生效 | 全局调大会按并发连接数线性放大内存占用，优先建议会话/语句级 `SET work_mem`，全局调整需评估最大连接数 |
| 高危 DML 无 WHERE 条件 | 先看纯 EXPLAIN 的预估影响行数，异常大时向用户确认再决定是否做 ANALYZE 真实测算 |
| 误以为 `pg_stat_statements` 存在 | 金仓用 `sys_stat_statements`（public schema）；`pg_stat_statements` 默认不存在 |
| 误以为有 `hash_mem_multiplier`/`hypopg` | V9R1C10 实测均无；Hash 溢盘调 `work_mem`，假设索引只能经验推断 |
| `CREATE INDEX CONCURRENTLY` 放事务块里报错 | 单独会话/单独 `psql -c` 执行，不能与 BEGIN/COMMIT 同事务 |

## 注意事项

- **DML 语句执行前必须设置语句超时，且必须在事务中执行，拿到 EXPLAIN ANALYZE 结果后必须 ROLLBACK，绝不 COMMIT。** 这是本 skill 的硬性红线，任何情况下都不能省略。
- 连接信息（密码）只在本次会话内存中使用，不写入任何持久化文件（包括最终 markdown 报告、脚本参数文件）。
- 不对生产实例执行任何 DDL 或真正提交的数据变更；如用户明确要求执行建议的 DDL（如建索引），需在报告中给出语句由用户自行执行，或在用户二次明确确认\"现在就执行\"后才可代为执行，且优先用 `CONCURRENTLY` 降低锁影响。
- 网络不可达目标实例时，如实告知用户，转而请求用户在本地跑 `EXPLAIN` 命令并粘贴结果作为替代输入，不要编造执行计划。
- 涉及多张大表、复杂 CTE 的 SQL，诊断可能需要多轮采集（先看整体计划定位问题节点，再针对性采集该节点相关表/索引/参数），不要一次性无差别采集所有对象信息。
- 参考文档：金仓官方\"性能调优\"指南 https://docs.kingbase.com.cn/cn/KES-V9R1C10/administration/Config_Mgmt/performance-optimization （入口 https://docs.kingbase.com.cn/cn/KES-V9R1C10/introduction ）。若实例行为与本文档描述不符，以实测为准并反馈。
