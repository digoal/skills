---
name: kingbase-stat-snapshot
description: "为 KingbaseES（金仓）实例建立统计信息快照采集、存储、差值计算与历史清理的基础设施。当用户提到"金仓快照采集"、"KingbaseES stat snapshot"、"sys_stat_statements 差值分析"、"金仓 TOP SQL 分析基础设施"、"金仓表/索引 DML 增量分析"、"金仓性能诊断基础设施"、"金仓统计信息历史留存"、"需要两个时间点对比金仓统计信息"、或提供了 KingbaseES 实例连接信息（host/port/user/password）并希望搭建可重复调用的金仓性能快照系统时触发。即使用户只说"帮我给这个金仓库建个统计快照"或"我要能对比两个时刻的 sys_stat_statements"，也应使用本技能。本技能只负责基础设施搭建、采集、差值计算与清理，不产出最终分析报告——报告类需求应转交 kingbase-top-sql-analyze / kingbase-large-table-optimize / kingbase-bloat-root-cause 等下游技能。KingbaseES 默认采用 PG 兼容模式（database_mode=pg），因此大部分视图名与 PostgreSQL 一致，但 TOP SQL 取自 public.sys_stat_statements 而非 pg_stat_statements，且无 sys_stat_statements_info 视图，需用 sys_stat_statements_get_reset_time() 函数取重置时间。"
tags: [KingbaseES, 创建统计信息快照]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# KingbaseES 统计快照基础设施 (kingbase-stat-snapshot)

为一个 KingbaseES（金仓）实例建立可重复调用的统计信息快照系统：定时采集 `sys_stat_statements` / `pg_stat_*` 系列视图到历史表，支持任意两个快照之间的差值计算，并提供按时间/按数量的历史清理能力。这是所有"两阶段采集对比"类性能分析技能（TOP SQL、表膨胀、索引使用率等）的公共基座，其他技能应直接消费本技能建立的历史表，不应重复造轮子。

## 与 PostgreSQL 的关键差异

KingbaseES 默认采用 PG 兼容模式（`database_mode=pg`），因此绝大部分视图、SQL 语法与 PostgreSQL 高度一致，但以下差异必须显式处理：

| 差异点 | PostgreSQL | KingbaseES (KES R1C10, server_version_num=12xxxx) |
|---|---|---|
| 慢 SQL 统计视图 | `pg_stat_statements`（位于 `pg_catalog`） | **`public.sys_stat_statements`**（位于 `public` schema，作为扩展安装） |
| 重置时间获取 | `pg_stat_statements_info` 视图 | **`sys_stat_statements_get_reset_time()` 函数**（无对应视图） |
| 重置函数 | `pg_stat_statements_reset()` | **`public.sys_stat_statements_reset()`** |
| WAL 统计（PG14+） | `pg_stat_wal` | **不存在**（R1C10 基于 PG12 内核，无该视图） |
| Checkpointer（PG17+） | `pg_stat_checkpointer` | **不存在** |
| 所有常规视图 | `pg_catalog.pg_*` | `pg_catalog.pg_*` **+** `sys_catalog.sys_*` 同义视图 |

> 安装扩展的方式：`CREATE EXTENSION sys_stat_statements;`（与 PG 语法完全一致，但扩展名不同）

## 前置要求

- 已知目标实例的连接信息：host、port、user、password（或已配置 `.pgpass` / 环境变量 `PGPASSWORD`）。
- 客户端已安装 `psql`（用于执行 DDL/DML）或 Python `psycopg`/`psycopg2`（脚本会自动选择）。
- 目标账号权限：
  - 创建 `stat_snapshot` schema 及表 —— 需要在目标库有 `CREATE` 权限（超级用户或库 owner 最省事）。
  - 读取 `public.sys_stat_statements` —— 需要扩展已 `CREATE EXTENSION sys_stat_statements`，且账号有权限查询。
  - 读取 `pg_stat_activity` 全部字段（含 query 文本）—— 通常需要超级用户或 `pg_read_all_stats` 角色（KES R1C10 也支持）。
- 不需要联网；所有操作均在目标实例内部完成。
- 权限不足时，不要静默降级，直接输出对应的 `GRANT`/`CREATE EXTENSION` 语句让用户以有权限账号执行（见"权限不足处理"一节）。

## 工作流程

### Step 0：连接探测与版本识别

先执行只读探测，禁止在未确认版本前直接跑固定版本的 DDL：

```bash
psql "host=<HOST> port=<PORT> user=<USER> dbname=<DB>" -Atc "SELECT current_setting('server_version_num'), current_setting('server_version');"
psql "host=<HOST> port=<PORT> user=<USER> dbname=<DB>" -Atc "SELECT datname FROM pg_database WHERE datistemplate = false;"
psql "host=<HOST> port=<PORT> user=<USER> dbname=<DB>" -Atc "SELECT extname, extversion FROM pg_extension WHERE extname = 'sys_stat_statements';"
```

根据 `server_version_num` 决定：
- 120001-129999（KES R1C10）：使用本 skill 默认模板，不包含 `pg_stat_wal` / `pg_stat_checkpointer`。
- ≥130000（未来版本若引入 WAL 统计）：`ddl_optional.sql` 会自动探测并按需建表。

若 `sys_stat_statements` 扩展未安装，输出：
```
CREATE EXTENSION IF NOT EXISTS sys_stat_statements;  -- 需要在 kingbase.conf 中已配置 shared_preload_libraries='sys_stat_statements' 并重启生效
```
并提示这一步无法绕过（该扩展依赖共享内存预加载，不能只靠 `CREATE EXTENSION` 生效，必须确认已重启过）。

### Step 1：初始化基础设施（幂等）

1. 连接到控制库（默认 `${PGDBNAME:-kingbase}`），检查 `stat_snapshot` schema 是否存在：
   ```sql
   SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'stat_snapshot');
   ```
2. **不存在** → 执行 `references/ddl_core.sql` 中的元数据表和实例级历史表 DDL（`snapshots`、`stat_statements_history`、`stat_activity_history`），并对每个非模板数据库执行 `references/ddl_perdb.sql`（库级历史表）。
3. **已存在** → 对每张 `*_history` 表执行结构比对：
   ```sql
   -- 以 stat_statements_history 为例，对比源视图字段与历史表字段的差集
   SELECT a.attname FROM pg_attribute a
   JOIN pg_class c ON a.attrelid = c.oid
   JOIN pg_namespace n ON c.relnamespace = n.oid
   WHERE n.nspname = 'public' AND c.relname = 'sys_stat_statements' AND a.attnum > 0 AND NOT a.attisdropped
   EXCEPT
   SELECT column_name FROM information_schema.columns
   WHERE table_schema = 'stat_snapshot' AND table_name = 'stat_statements_history';
   ```
   若有差集（新增字段），提示用户是否执行 `ALTER TABLE ... ADD COLUMN`（给出具体语句，不擅自执行破坏性变更）；若历史表比源视图多出字段（版本降级/字段被移除），只需保留，不删除历史列。
4. 建表方式统一使用"动态建表"，避免手写字段：
   ```sql
   CREATE TABLE IF NOT EXISTS stat_snapshot.stat_statements_history AS
   SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, s.*
   FROM public.sys_stat_statements s LIMIT 0;
   ALTER TABLE stat_snapshot.stat_statements_history ALTER COLUMN snapshot_id DROP DEFAULT;
   ```
   完整版本（含索引、query 长度适配）见 `references/ddl_core.sql`。
5. 所有 DDL 必须带 `IF NOT EXISTS`，可重复执行不报错。
6. 扩展采集：检查 `pg_stat_wal`（PG14+ / 未来版本）、`pg_stat_replication`、`pg_stat_database`、`pg_stat_bgwriter` 是否存在数据，存在则按 `stat_snapshot.<视图名去掉pg_前缀>_history` 命名规则动态建表，逻辑与核心表一致，模板见 `references/ddl_optional.sql`。

### Step 2：执行一次采集

实例级采集（金仓核心差异：`sys_stat_statements` 在 `public` schema，重置时间用函数而非视图）：

```sql
BEGIN;
INSERT INTO stat_snapshot.snapshots (snapshot_level, source_reset_time, comment)
VALUES ('instance',
        (SELECT sys_stat_statements_get_reset_time()),
        '手动采集')
RETURNING snapshot_id \gset

INSERT INTO stat_snapshot.stat_statements_history
SELECT :snapshot_id, :'snapshot_time', s.* FROM public.sys_stat_statements s;

INSERT INTO stat_snapshot.stat_activity_history
SELECT :snapshot_id, :'snapshot_time', a.* FROM pg_stat_activity a
WHERE a.state IS DISTINCT FROM 'idle' OR (SELECT count(*) FROM pg_stat_activity) <= 100;
COMMIT;
```

对每个非模板数据库，另起一个连接（同一顶层事务无法跨库），依次采集库级视图并写入对应 `snapshot_id`（沿用同一个 `snapshot_id`，`snapshot_level='database'` 的元数据行需要每库单独插入一条，携带 `database_name`）：

```sql
BEGIN;
INSERT INTO stat_snapshot.snapshots (snapshot_level, database_name, source_reset_time)
VALUES ('database', current_database(), (SELECT stats_reset FROM pg_stat_database WHERE datname = current_database()))
RETURNING snapshot_id \gset

INSERT INTO stat_snapshot.stat_user_tables_history SELECT :snapshot_id, now(), t.* FROM pg_stat_user_tables t;
INSERT INTO stat_snapshot.stat_user_indexes_history SELECT :snapshot_id, now(), i.* FROM pg_stat_user_indexes i;
INSERT INTO stat_snapshot.statio_user_tables_history SELECT :snapshot_id, now(), t.* FROM pg_statio_user_tables t;
INSERT INTO stat_snapshot.statio_user_indexes_history SELECT :snapshot_id, now(), i.* FROM pg_statio_user_indexes i;
COMMIT;
```

完整可执行脚本（含错误捕获、逐库循环、行数统计）见：
- `scripts/run_snapshot.sh`：基于 `psql` 子进程，跨平台稳定。
- `scripts/run_snapshot.py`：基于 Python `psycopg`/`psycopg2`，更易做二次开发与 CI 集成。

**约束（必须遵守）**：
- 每次采集必须在事务内完成"元数据插入 + 数据写入"，保证同一个 `snapshot_id` 下的数据不会因为中途失败而部分写入；失败必须 `ROLLBACK`，不得留下悬挂事务。
- 单个视图采集失败（如权限不足）不应中断整体流程：捕获错误、记录到输出、继续采集下一个视图，最终在采集报告中列出失败项。
- `pg_stat_activity` 属于瞬时快照，只做切片存储，不参与差值计算，采集时按连接数决定是否过滤 `idle` 连接（见前置要求）。

### Step 3：采集结果输出（每次采集后必须给出）

```
✅ 快照采集完成
  快照 ID: <snapshot_id>
  快照时间: <snapshot_time>
  实例级视图:
    - public.sys_stat_statements: 采集 N 行
    - pg_stat_activity: 采集 N 行（已过滤 idle，原始连接数 M）
  库级视图（共 K 个数据库）:
    - db1.pg_stat_user_tables: N 行
    - db1.pg_stat_user_indexes: N 行
    ...
  失败项: <视图名 - 错误原因>（如无则写"无"）
  总耗时: X 秒
```

### Step 4：差值计算

差值不要求用户手写 SQL，直接调用 `references/ddl_core.sql` 中定义的 `stat_snapshot.compute_delta()` 函数，或直接使用 `references/delta_templates.sql` 中的模板（TOP SQL、表 DML 增量、索引使用增量、IO 命中率增量）。

调用前必须先做一致性校验：
```sql
SELECT s1.source_reset_time = s2.source_reset_time AS reset_consistent
FROM stat_snapshot.snapshots s1, stat_snapshot.snapshots s2
WHERE s1.snapshot_id = <begin_id> AND s2.snapshot_id = <end_id>;
```
若为 `false`，报错「快照区间内发生过统计重置，差值无效」并停止，不得强行输出误导性的负数差值。

对差值字段的处理原则：
- 累积计数器（`calls`、`total_exec_time`、`rows`、`n_tup_ins` 等）：`end - begin`。
- 比率型字段（`mean_exec_time`、命中率等）：基于差值重新计算，不能直接对两个快照的比率做减法（比率不可加减）。
- 文本/标识字段（`query`、`indexrelname` 等）：取 `end` 快照的值。
- 若 `end.calls - begin.calls < 0`（发生过 `public.sys_stat_statements_reset()` 但未被上面的 reset_time 校验捕获到，例如驱逐后 queryid 复用），该行需要被过滤而非报负数，在结果中标注「疑似统计条目被驱逐重建，已跳过」。

### Step 5：历史清理

两种清理方式二选一或组合使用，均在 `references/cleanup.sql` 中提供：
- 按时间：`CALL stat_snapshot.cleanup_snapshots(retention_days => 7);`
- 按数量：`CALL stat_snapshot.cleanup_by_count(retain_count => 100);`

定时任务建议（金仓 R1C10 默认含 `kdb_schedule` 扩展，等同 PG 的 `pg_cron`）：
```sql
-- 若实例已装 kdb_schedule（在控制库中创建）
CALL kdb_schedule.schedule('kingbase-stat-snapshot-cleanup', '0 3 * * *',
    $$CALL stat_snapshot.cleanup_snapshots(7)$$);
```
```bash
# 若使用 crontab（psql 方式，需配置好 .pgpass 免密）
0 3 * * * PGPASSWORD="$(cat /etc/kingbase-stat-snapshot.pgpass)" psql "host=<HOST> port=<PORT> user=<USER> dbname=kingbase" -c "CALL stat_snapshot.cleanup_snapshots(7);"
```

## 输出格式（初始化完成后必须给出）

```
📦 已创建的基础设施
| Schema | 对象名 | 类型 | 用途 |
|---|---|---|---|
| stat_snapshot | snapshots | 表 | 快照元数据 |
| stat_snapshot | stat_statements_history | 表 | sys_stat_statements 快照历史 |
| stat_snapshot | stat_activity_history | 表 | pg_stat_activity 快照切片 |
| stat_snapshot | stat_user_tables_history | 表（每库） | 表级 DML/扫描历史 |
| stat_snapshot | stat_user_indexes_history | 表（每库） | 索引使用历史 |
| stat_snapshot | statio_user_tables_history / statio_user_indexes_history | 表（每库） | IO 命中率历史 |
| stat_snapshot | compute_delta() | 函数 | 通用差值计算 |
| stat_snapshot | cleanup_snapshots() / cleanup_by_count() | 存储过程 | 历史清理 |

🔄 建议采集频率
- sys_stat_statements：每 10-30 分钟
- pg_stat_activity：每 1-5 分钟
- 库级统计视图：每 30-60 分钟
（可通过 crontab/kdb_schedule 调整，间隔越短差值粒度越细，但存储与写入开销越大）

📊 后续协作
本基础设施建立后，可直接被以下技能消费，无需重复采集：
- kingbase-top-sql-analyze → 消费 stat_statements_history 差值
- kingbase-large-table-optimize → 消费 stat_user_tables_history 差值
- kingbase-bloat-root-cause → 结合多时间点快照回溯膨胀窗口
```

## 权限不足处理

若初始化或采集过程中遇到权限错误，不要尝试绕过或用超级用户内建函数强行读取，直接原样输出需要的授权语句，并说明谁需要执行（通常是超级用户或库 owner）：

```sql
-- 建 schema/表需要的权限
GRANT CREATE ON DATABASE kingbase TO <user>;

-- 读取 sys_stat_statements
GRANT pg_read_all_stats TO <user>;

-- 读取 pg_stat_activity 全部字段（含其他用户的 query 文本）
GRANT pg_read_all_stats TO <user>;
```

## Pitfalls & Solutions

| 坑点 | 现象 | 解决方案 |
|---|---|---|
| `sys_stat_statements` 未预加载 | `CREATE EXTENSION` 报错或视图查询报"relation does not exist" | 检查 `shared_preload_libraries`，需重启实例后才能生效，不能仅靠扩展安装绕过 |
| `query` 字段被截断 | 长 SQL 历史记录不完整 | 历史表 `query` 列长度需跟随 `track_activity_query_size`（KES 默认 1024），建表时统一用 `text` 类型避免二次截断 |
| 重置时间取错 | 用 `pg_stat_statements_info` 视图报"relation does not exist" | KES 必须改用 `public.sys_stat_statements_get_reset_time()` 函数 |
| 视图名/路径写错 | 把 `sys_stat_statements` 写成 `pg_stat_statements` | KES 视图位于 `public` schema，必须带前缀 `public.sys_stat_statements`（其他视图如 `pg_stat_*` 可省略 schema） |
| 差值出现负数 | `calls` 变小 | 说明区间内发生过 `public.sys_stat_statements_reset()` 或该 queryid 被驱逐后复用，需先做 `source_reset_time` 校验，异常行过滤而非硬算 |
| 库级采集遗漏新建库 | 新建的数据库没有历史表 | 每次采集前先执行 `SELECT datname FROM pg_database WHERE datistemplate=false` 动态发现，而不是硬编码库名列表 |
| `pg_stat_activity` 写爆存储 | 连接数很大时历史表膨胀极快 | 按前置要求，连接数 > 100 时只保留非 idle 连接，并在采集报告中注明过滤策略 |
| 历史表跨版本字段不一致 | 升级 KES 大版本后差值函数报字段不存在 | Step 1.3 的结构比对必须在每次初始化/采集前跑一次，而不是只跑一次性检查 |
| 悬挂事务 | 采集脚本异常退出后连接卡在事务中 | 所有采集/清理逻辑必须显式 `COMMIT`/`ROLLBACK`，脚本捕获异常后主动 `ROLLBACK` 再退出 |

## 注意事项

- 本技能只负责基础设施与差值计算，不负责撰写面向用户的分析报告（报告类需求转交下游技能）。
- 所有 DDL 必须 `IF NOT EXISTS`，保证脚本可重复执行。
- 涉及密码的连接串不要写入日志或输出内容，采集脚本应通过 `.pgpass`、环境变量或参数传递密码，不得在命令行明文拼接后原样打印。
- `pg_stat_activity` 中的 `query` 字段可能包含敏感数据（如误写入 SQL 的明文密码），历史表默认不做脱敏，若用户环境敏感，应在 Step 1 提示是否需要对 `query` 字段做脱敏处理再入库。
- 生产环境首次全量采集前，建议先确认 `stat_snapshot` schema 不会与用户现有对象冲突（本技能全程使用独立 schema，理论上不冲突，但仍需一次性确认）。
- 连接参数优先级：脚本参数（`--host/--port/--user/--password/--dbname`）> 环境变量（`PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDBNAME`）> 默认值（`127.0.0.1:5432/kingbase/kingbase/123456`）。