---
name: kingbase-find-unused-index
description: "KingbaseES（金仓）未使用索引检测专用技能。给定 KingbaseES（金仓）实例的连接串（host/port/user/password），自动列出实例下所有可连接数据库，逐库扫描未被使用的索引，按索引大小倒序输出索引名、索引大小、表大小及影响评估，并给出后续观察或操作建议。KingbaseES 默认采用 PG 兼容模式，因此 pg_stat_user_indexes / pg_index / pg_constraint 视图与 PostgreSQL 一致；KingbaseES 同时提供 sys_catalog.sys_stat_user_indexes / sys_catalog.sys_index / sys_catalog.sys_constraint 作为同义视图供 DBA 直接使用。触发条件：用户提到\"金仓未使用索引\"、\"金仓无用索引\"、\"金仓冗余索引\"、\"金仓索引瘦身\"、\"金仓哪些索引可以删\"、\"金仓 index bloat\"、\"金仓 unused index\"、\"金仓 idx_scan\"、\"金仓帮我检查一下这个库的索引\"、\"金仓索引优化建议\"、\"金仓数据库瘦身\"，或提供了 KingbaseES 连接串/账号密码并希望做索引健康检查、存储优化、性能调优时，必须使用本 skill。即使用户只说\"帮我看看这个金仓实例有没有浪费空间的索引\"或\"这个金仓库的索引是不是太多了\"，也应使用本 skill。"
tags: [KingbaseES, 金仓, 未使用索引, 优化]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# KingbaseES 未使用索引检测

作为 KingbaseES DBA 专家，扫描一个金仓实例下所有数据库，找出长期未被查询优化器使用的索引，量化其存储成本，给出可执行、可回滚的处理建议。

> KingbaseES 默认采用 **PG 兼容模式**：`pg_stat_user_indexes` / `pg_index` / `pg_constraint` / `pg_inherits` / `pg_partitioned_table` 等系统视图与 PostgreSQL 12 高度一致；同时 `sys_catalog` 下存在 `sys_stat_user_indexes` / `sys_index` / `sys_constraint` 等同义视图供 DBA 直接使用。本 skill 默认使用 `pg_*` 系列视图（PG 兼容），与 `sys_*` 系列数据等价。

## 前置要求

- 客户端需要 `psql`（金仓自带 KES client）或 Python `psycopg2` 驱动。检测与安装：

```bash
command -v psql || {
  echo "请手动安装 KingbaseES 客户端或在 KingbaseES 安装目录 bin/ 下使用 ksql、sys_ksql 等命令";
}

python3 -c "import psycopg2" 2>/dev/null || {
  echo "可选: pip install psycopg2-binary";
}
```

- 目标账号至少需要：对每个目标库有 `CONNECT` 权限；对 `pg_stat_user_indexes` 视图有可读性（默认所有登录角色可读自己有权限的对象的统计信息）。
- 若要看到**实例内所有数据库、所有 schema** 的完整索引统计，建议使用具备 `sys_monitor`（或更高）角色的账号连接；普通业务账号只能看到自己有权限访问的对象，结果会不完整，必须在报告中注明。
- **金仓默认账号**：本 skill 默认采用 `kingbase` / `123456` / 5432 与同名数据库。
- **安全约束**：
  - 绝不在命令行参数、日志、输出报告中明文回显密码。密码通过环境变量 `PGPASSWORD` 或 `~/.pgpass` 传递。
  - 绝不将连接串、密码、查询结果发送到本机以外的任何网络地址。
  - 只读操作：本技能全程只执行 `SELECT`，不修改任何数据库对象；如用户要求执行 `DROP INDEX`，需在"注意事项"一节的确认流程后，由用户显式批准才可执行，且默认使用 `CONCURRENTLY` 且不在本 skill 内自动执行。

## 连接约定

按优先级解析：

1. 用户明确提供的连接参数（host/port/user/password/dbname）；
2. 环境变量 `PGHOST` `PGPORT` `PGUSER` `PGPASSWORD` `PGDATABASE`（即使 KingbaseES 手册把这些变量写作 `KINGBASE_*`，本 skill **继续沿用 PG 风格**）；
3. 缺省值：`PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGPASSWORD=123456 PGDATABASE=kingbase`。

> KingbaseES 安装后默认会创建一个名为 `kingbase` 的数据库（注意：默认并**不**像 PostgreSQL 那样创建 `postgres` 库），列库脚本必须能容忍这种差异——直接查询 `pg_database` 即可，不要硬编码 `postgres`。

## 工作流程

### Step 1: 解析连接信息

从用户输入中提取（缺失项主动追问，不要猜测/硬编码）：

- host、port（默认 5432）
- 管理用户名、密码、目标 dbname

统一使用 libpq 连接串形式，密码通过环境变量注入，避免出现在进程列表中：

```bash
export PGPASSWORD='<password>'
ADMIN_CONN="host=<host> port=<port> user=<user> dbname=<admin_db> sslmode=prefer"
```

### Step 2: 列出实例下所有数据库

```bash
psql "$ADMIN_CONN" -tAc "
  SELECT datname FROM pg_database
  WHERE datistemplate = false AND datallowconn = true
  ORDER BY datname;"
```

记录数据库总数，作为后续逐库扫描的清单。若某个库连接失败（权限不足/库被禁止连接），在最终报告中列为"跳过"并说明原因，不要中断整体流程。

> 在 KingbaseES 上 `pg_database` 与 PostgreSQL 等价；如果 DBA 偏好使用金仓原生视图，可用 `sys_catalog.sys_database`。

### Step 3: 逐库扫描未使用索引

对每个数据库单独建立连接（金仓的统计信息 `pg_stat_user_indexes` 是**库级别**的，无法跨库一次查询），执行核心查询（完整版见 `scripts/find_unused_indexes.sql`）：

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
  AND n.nspname NOT IN (
        'sys_catalog','sys_hm','sysaudit','sysmac',
        'src_restrict','xlog_record_read',
        'dbms_job','dbms_scheduler','kdb_schedule','anon'
      )  -- 过滤 KingbaseES 内置 schema，避免误报
ORDER BY pg_relation_size(s.indexrelid) DESC;
```

> KingbaseES 在 `pg_stat_user_indexes` 中会同时显示用户自定义 schema 和部分金仓内置 schema（取决于安装时的视图定义），上述 `n.nspname NOT IN (...)` 过滤可以避免把 `sysmac_policy_pkey` 这种内部对象误报为"未使用索引"。如果 DBA 确实想审计金仓内置 schema 的索引，可以删除该过滤并改用 `pg_stat_all_indexes`。

同时采集两个上下文指标（用于判断 `idx_scan = 0` 是否可信）：

```sql
-- 统计信息是否被重置过、重置了多久
SELECT stats_reset FROM pg_stat_database WHERE datname = current_database();
-- 实例已运行多久（是否覆盖了完整业务周期，如月末结算、季度报表）
SELECT pg_postmaster_start_time();
```

可用 `scripts/find_unused_indexes.sh <host> <port> <user> [dbname_filter]` 一次性遍历所有数据库并输出汇总（密码从 `PGPASSWORD` 环境变量读取）；亦可用 `scripts/find_unused_indexes.py <host> <port> <user> [dbname_filter]` 走 Python `psycopg2` SDK 走一遍，方便嵌入到更大的诊断流水线。

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
2. **主备架构提醒**：若实例存在金仓 RWC（读写分离集群）/HA 复制只读副本，主库和备库的 `pg_stat_user_indexes` 统计是**相互独立**的（备库上的只读查询不会体现在主库统计里，反之亦然）；必须在主库和所有承担读流量的备库上分别执行本扫描，取交集作为真正"全局未使用"的索引。
3. **删除前的安全动作**：
   - 先 `pg_get_indexdef` 导出索引定义做备份，而不是直接删除后才发现漏了业务场景。
   - 使用 `DROP INDEX CONCURRENTLY` 避免长时间锁表（不能在事务块内执行）。KingbaseES 同样支持该语法（金仓基于 PG 12，内核层未做阉割）。
   - 优先在低峰期分批处理，处理一批后观察应用错误率/慢查询变化，再处理下一批。
4. **不要仅凭 `idx_scan = 0` 下结论**：结合 Step 4 的 `backs_constraint`、索引大小占比、统计窗口长度综合判断。

## Pitfalls & Solutions

| 坑点 | 说明 | 解决方案 |
|------|------|----------|
| 统计信息刚被重置 | `pg_stat_reset()` 或实例刚重启会清零 `idx_scan`，误判为"未使用" | 先查 `stats_reset` 和 `pg_postmaster_start_time()`，窗口太短则提示观察期不足 |
| 分区表索引 | `pg_stat_user_indexes` 只统计具体分区上的索引，父表（`ONLY` 索引）本身不会有扫描计数 | 需要额外检查 `pg_partitioned_table`，对分区表的"未使用"判断要按各子分区分别核实 |
| 备库统计独立 | 只在主库跑扫描会漏掉"备库在用、主库未用"的索引 | 对每个承担读流量的节点分别扫描，取交集 |
| 外键无自动索引 | KingbaseES 不会给外键列自动建索引，误删"看似未用"的外键侧索引可能导致后续 DELETE/UPDATE 全表扫描 | Step3 查询里的 `backs_constraint` 字段已识别，标记为"谨慎-不建议删除" |
| 权限不足看不全 | 业务账号只能看到自己权限内的对象，容易漏报 | 报告中显式声明使用的账号权限级别，权限不足时提示换用 `sys_monitor` 角色账号复核 |
| 唯一/主键索引被误判 | 唯一约束索引哪怕 idx_scan=0 也不能删（会破坏约束） | Step3 查询已用 `NOT i.indisprimary` 过滤主键，唯一/排他约束在 `backs_constraint` 中标注 |
| KingbaseES 内置 schema 误报 | `sysmac` / `sys_hm` / `sysaudit` / `sys_catalog` 等内置 schema 的索引即便 `idx_scan=0` 也是金仓自身维护所需，不应删除 | SQL 已通过 `n.nspname NOT IN (...)` 过滤内置 schema；如需审计内置 schema，请改用 `pg_stat_all_indexes` 并人工甄别 |
| 默认搜索路径只含 public | `psql` 默认 `search_path = "$user",public`，sys_catalog / sys_hm 等需显式 schema 限定 | 本 skill 全部使用 `pg_*` 视图（在 pg_catalog 中），不受影响；如需走 `sys_*` 视图请加 `sys_catalog.` 前缀 |

## 注意事项

- 本技能**只读**，不会执行任何 DDL；如需真正执行 `DROP INDEX`，必须由用户在看到报告后明确批准具体索引名，且建议使用 `CONCURRENTLY` 并在维护窗口操作，同时保留索引定义作为回滚脚本。
- 需要 root/超级用户权限的场景仅限于希望获得"实例内所有库、所有 schema"的完整视图；常规扫描不需要 root。
- 密码等敏感信息不写入报告、不打印到终端历史、不通过网络发送到本机以外的地址。
- 对生产实例执行时，建议先在只读副本或低峰期验证连接串与权限，确认无误后再进行全库扫描。
- 详细的 SQL 与自动化脚本见 `scripts/find_unused_indexes.sql` / `scripts/find_unused_indexes.sh` / `scripts/find_unused_indexes.py`；边界场景（分区表、外键、主备统计差异、内置 schema 等）的补充说明见 `references/edge_cases.md`。
- 进一步的索引调优、SQL 调优、表/索引膨胀诊断，可参考同仓库的 `kingbase-design-audit`、`kingbase-find-bloat` 技能。
- 参考官方文档入口：[性能调优指南](https://docs.kingbase.com.cn/cn/KES-V9R1C10/category/%E6%80%A7%E8%83%BD%E8%B0%83%E4%BC%98%E6%8C%87%E5%8D%97) / [SQL 调优指南](https://docs.kingbase.com.cn/cn/KES-V9R1C10/category/sql%E8%B0%83%E4%BC%98%E6%8C%87%E5%8D%97) / [数据库概念](https://docs.kingbase.com.cn/cn/KES-V9R1C10/reference/system_principles/%E6%95%B0%E6%8D%AE%E5%BA%93%E6%A6%82%E5%BF%B5)。