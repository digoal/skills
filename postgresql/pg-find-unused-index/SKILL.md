---
name: pg-find-unused-index
description: "PostgreSQL 未使用索引检测专用技能。给定 PostgreSQL 实例的连接串（host/port/user/password 或 postgresql:// URL），自动列出实例下所有可连接数据库，逐库扫描未被使用的索引，按索引大小倒序输出索引名、索引大小、表大小及影响评估，并给出后续观察或操作建议。触发条件：用户提到\"未使用索引\"、\"无用索引\"、\"冗余索引\"、\"索引瘦身\"、\"哪些索引可以删\"、\"index bloat\"、\"unused index\"、\"idx_scan\"、\"帮我检查一下这个库的索引\"、\"索引优化建议\"、\"数据库瘦身\"，或提供了 PostgreSQL 连接串/账号密码并希望做索引健康检查、存储优化、性能调优时，必须使用本 skill。即使用户只说\"帮我看看这个 PG 实例有没有浪费空间的索引\"或\"这个库的索引是不是太多了\"，也应使用本 skill。"
tags: [PostgreSQL, 未使用索引, 优化]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# PostgreSQL 未使用索引检测

作为 PostgreSQL DBA 专家，扫描一个 PG 实例下所有数据库，找出长期未被查询优化器使用的索引，量化其存储成本，给出可执行、可回滚的处理建议。

## 前置要求

- 客户端需要 `psql`（PostgreSQL client）。检测与安装：

```bash
command -v psql || {
  if command -v dnf &>/dev/null; then dnf install -y postgresql
  elif command -v yum &>/dev/null; then yum install -y postgresql
  elif command -v apt-get &>/dev/null; then apt-get install -y postgresql-client
  else echo "请手动安装 postgresql client"; fi
}
```

- 目标账号至少需要：对每个目标库有 `CONNECT` 权限；对 `pg_stat_user_indexes` 视图有可读性（默认所有登录角色可读自己有权限的对象的统计信息）。
- 若要看到**实例内所有数据库、所有 schema** 的完整索引统计，建议使用具备 `pg_monitor`（或更高）角色的账号连接；普通业务账号只能看到自己有权限访问的对象，结果会不完整，必须在报告中注明。
- **安全约束**：
  - 绝不在命令行参数、日志、输出报告中明文回显密码。密码通过环境变量 `PGPASSWORD` 或 `~/.pgpass` 传递。
  - 绝不将连接串、密码、查询结果发送到本机以外的任何网络地址。
  - 只读操作：本技能全程只执行 `SELECT`，不修改任何数据库对象；如用户要求执行 `DROP INDEX`，需在"注意事项"一节的确认流程后，由用户显式批准才可执行，且默认使用 `CONCURRENTLY` 且不在本 skill 内自动执行。

## 工作流程

### Step 1: 解析连接信息

从用户输入中提取（缺失项主动追问，不要猜测/硬编码）：

- host、port（默认 5432）
- 管理用户名、密码
- 是否使用 SSL（`sslmode`）

统一使用 libpq 连接串形式，密码通过环境变量注入，避免出现在进程列表中：

```bash
export PGPASSWORD='<password>'
CONN="host=<host> port=<port> user=<user> dbname=postgres sslmode=prefer"
```

### Step 2: 列出实例下所有数据库

```bash
psql "$CONN" -tAc "
  SELECT datname FROM pg_database
  WHERE datistemplate = false AND datallowconn = true
  ORDER BY datname;"
```

记录数据库总数，作为后续逐库扫描的清单。若某个库连接失败（权限不足/库被禁止连接），在最终报告中列为"跳过"并说明原因，不要中断整体流程。

### Step 3: 逐库扫描未使用索引

对每个数据库单独建立连接（PostgreSQL 的统计信息 `pg_stat_user_indexes` 是**库级别**的，无法跨库一次查询），执行核心查询（完整版见 `scripts/find_unused_indexes.sql`）：

```sql
SELECT
  n.nspname                                   AS schema_name,
  s.relname                                   AS table_name,
  s.indexrelname                              AS index_name,
  pg_relation_size(s.indexrelid)              AS index_size_bytes,
  pg_size_pretty(pg_relation_size(s.indexrelid)) AS index_size,
  pg_size_pretty(pg_relation_size(s.relid))   AS table_size,
  s.idx_scan,
  i.indisunique,
  i.indisprimary,
  i.indisexclusion,
  EXISTS (
    SELECT 1 FROM pg_constraint c
    WHERE c.conindid = s.indexrelid AND c.contype IN ('f','u','p')
  )                                            AS backs_constraint,
  pg_get_indexdef(s.indexrelid)               AS index_def
FROM pg_stat_user_indexes s
JOIN pg_index i      ON i.indexrelid = s.indexrelid
JOIN pg_class c       ON c.oid = s.relid
JOIN pg_namespace n   ON n.oid = c.relnamespace
WHERE s.idx_scan = 0
  AND NOT i.indisprimary
ORDER BY pg_relation_size(s.indexrelid) DESC;
```

同时采集两个上下文指标（用于判断 `idx_scan = 0` 是否可信）：

```sql
-- 统计信息是否被重置过、重置了多久
SELECT stats_reset FROM pg_stat_database WHERE datname = current_database();
-- 实例已运行多久（是否覆盖了完整业务周期，如月末结算、季度报表）
SELECT pg_postmaster_start_time();
```

可用 `scripts/find_unused_indexes.sh <host> <port> <user> [dbname_filter]` 一次性遍历所有数据库并输出汇总（密码从 `PGPASSWORD` 环境变量读取）。

### Step 4: 影响评估分级

对每条命中的索引，按以下规则给出"影响评估"标签，不要只罗列数据不做判断：

| 条件 | 影响评估 | 建议 |
|------|----------|------|
| `backs_constraint = true`（支撑外键/唯一约束） | ⚠️ 谨慎-不建议删除 | 即使 idx_scan=0，也可能在做约束校验、防止全表锁；仅建议观察，不建议删除 |
| 索引大小 > 表大小的 30% 且 idx_scan = 0 | 🔴 高收益-建议删除 | 存储浪费显著，且无读收益，写放大成本高，是优先处理对象 |
| 索引大小较小（如 < 100MB）且 idx_scan = 0 | 🟡 低优先级-可观察 | 收益有限，可延后处理，优先处理体积更大的 |
| 距上次 `stats_reset` 或实例启动 < 30 天 | 🔵 证据不足-需延长观察 | idx_scan=0 可能只是因为统计窗口太短，尚未覆盖月末/季末等低频业务场景 |
| 存在同名前缀/字段重叠的其他索引（复合索引可覆盖） | 🟠 冗余-建议合并 | 可能是历史遗留的重复索引，建议核对是否可被现有复合索引替代 |

同一条索引可能命中多条规则，取风险最高（最保守）的一条作为最终结论。

### Step 5: 输出报告格式

按数据库分组，每个数据库内按索引大小倒序，使用如下表格：

```markdown
## 数据库: <dbname>

统计信息重置时间: <stats_reset> | 实例运行时长: <uptime>

| 序号 | Schema | 表名 | 索引名 | 索引大小 | 表大小 | idx_scan | 影响评估 |
|---|---|---|---|---|---|---|---|
| 1 | public | orders | idx_orders_old_status | 2.1 GB | 5.4 GB | 0 | 🔴 高收益-建议删除 |
| 2 | public | orders | idx_orders_fk_customer | 340 MB | 5.4 GB | 0 | ⚠️ 谨慎-不建议删除（支撑FK） |

**该库可回收存储空间合计**: <sum of 🔴 + 🟡 index sizes>
```

全部数据库扫描完成后，附加一节**跨库汇总**：总扫描库数、总命中未使用索引数、可回收空间总计（按评估等级拆分）、Top 5 最大未使用索引。

最后给出**后续观察或操作建议**（固定包含以下几类，结合实际扫描结果调整措辞）：

1. **观察周期建议**：若实例运行时间或统计重置时间不足一个完整业务周期（建议 ≥ 1 个月，覆盖月末/季度结算等低频场景），建议先观察满一个周期再做删除决策。
2. **主备架构提醒**：若实例存在流复制只读副本，主库和备库的 `pg_stat_user_indexes` 统计是**相互独立**的（备库上的只读查询不会体现在主库统计里，反之亦然）；必须在主库和所有承担读流量的备库上分别执行本扫描，取交集作为真正"全局未使用"的索引。
3. **删除前的安全动作**：
   - 先 `pg_get_indexdef` 导出索引定义做备份，而不是直接删除后才发现漏了业务场景。
   - 使用 `DROP INDEX CONCURRENTLY` 避免长时间锁表（不能在事务块内执行）。
   - 优先在低峰期分批处理，处理一批后观察应用错误率/慢查询变化，再处理下一批。
4. **不要仅凭 `idx_scan = 0` 下结论**：结合 Step 4 的 `backs_constraint`、索引大小占比、统计窗口长度综合判断。

## Pitfalls & Solutions

| 坑点 | 说明 | 解决方案 |
|------|------|----------|
| 统计信息刚被重置 | `pg_stat_reset()` 或实例刚重启会清零 `idx_scan`，误判为"未使用" | 先查 `stats_reset` 和 `pg_postmaster_start_time()`，窗口太短则提示观察期不足 |
| 分区表索引 | `pg_stat_user_indexes` 只统计具体分区上的索引，父表（`ONLY` 索引）本身不会有扫描计数 | 需要额外检查 `pg_partitioned_table`，对分区表的"未使用"判断要按各子分区分别核实 |
| 备库统计独立 | 只在主库跑扫描会漏掉"备库在用、主库未用"的索引 | 对每个承担读流量的节点分别扫描，取交集 |
| 外键无自动索引 | PostgreSQL 不会给外键列自动建索引，误删"看似未用"的外键侧索引可能导致后续 DELETE/UPDATE 全表扫描 | Step3 查询里的 `backs_constraint` 字段已识别，标记为"谨慎-不建议删除" |
| 权限不足看不全 | 业务账号只能看到自己权限内的对象，容易漏报 | 报告中显式声明使用的账号权限级别，权限不足时提示换用 `pg_monitor` 角色账号复核 |
| 唯一/主键索引被误判 | 唯一约束索引哪怕 idx_scan=0 也不能删（会破坏约束） | Step3 查询已用 `NOT i.indisprimary` 过滤主键，唯一/排他约束在 `backs_constraint` 中标注 |

## 注意事项

- 本技能**只读**，不会执行任何 DDL；如需真正执行 `DROP INDEX`，必须由用户在看到报告后明确批准具体索引名，且建议使用 `CONCURRENTLY` 并在维护窗口操作，同时保留索引定义作为回滚脚本。
- 需要 root/超级用户权限的场景仅限于希望获得"实例内所有库、所有 schema"的完整视图；常规扫描不需要 root。
- 密码等敏感信息不写入报告、不打印到终端历史、不通过网络发送到本机以外的地址。
- 对生产实例执行时，建议先在只读副本或低峰期验证连接串与权限，确认无误后再进行全库扫描。
- 详细的 SQL 与自动化脚本见 `scripts/find_unused_indexes.sql` 与 `scripts/find_unused_indexes.sh`；边界场景（分区表、外键、主备统计差异等）的补充说明见 `references/edge_cases.md`。
