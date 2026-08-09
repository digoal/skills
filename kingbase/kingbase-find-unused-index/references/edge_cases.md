# 边界情况补充说明

本文档补充 SKILL.md 中未展开的细节，供 Agent 在遇到对应场景时按需查阅。

> **KingbaseES 适配说明**：KingbaseES 默认采用 PG 兼容模式，`pg_stat_user_indexes` / `pg_index` / `pg_constraint` / `pg_inherits` / `pg_partitioned_table` 与 PostgreSQL 12 高度一致；除第 6 节内置 schema 过滤规则外，其余处理方式与 PostgreSQL 等价。

## 1. 分区表（Partitioned Table）

`pg_stat_user_indexes` 只统计**具体分区**上的索引扫描次数，分区表本身的"逻辑索引"（`ONLY` 语义下创建的索引定义）不会单独出现扫描计数。

处理方式：

```sql
-- 找出分区表及其索引在各子分区上的实际扫描情况
SELECT
  pt.relname                       AS partitioned_table,
  child.relname                    AS partition_name,
  s.indexrelname,
  s.idx_scan
FROM pg_partitioned_table p
JOIN pg_class pt        ON pt.oid = p.partrelid
JOIN pg_inherits inh    ON inh.inhparent = pt.oid
JOIN pg_class child     ON child.oid = inh.inhrelid
JOIN pg_stat_user_indexes s ON s.relid = child.oid
ORDER BY pt.relname, child.relname, s.idx_scan;
```

对分区表下结论时，需要看**所有子分区**的 `idx_scan` 之和是否为 0，而不是只看某一个分区。如果只有个别历史分区（如冷数据分区）未被扫描，而近期分区仍在使用，不应判定为整体未使用索引。

> KingbaseES 同时支持**二级分区**（subpartition），可查询 `sys_catalog.sys_subpartition_table`（注意该视图不在默认 `search_path` 中，需要 schema 限定），或继续走 PG 兼容的 `pg_partitioned_table`（仅含一级）。

## 2. 主备 / 读写分离集群

KingbaseES 的 RWC（读写分离集群）、HA、流复制等架构下，`pg_stat_user_indexes` 的统计是**每个物理节点独立维护**的：

- 只读查询打到备库上，只会累加备库自己的 `idx_scan`，主库对应索引的 `idx_scan` 不会变化。
- 反之，写路径（INSERT/UPDATE/DELETE 触发的索引维护）不产生 `idx_scan`，`idx_scan` 只反映**读扫描**次数。

因此：

1. 必须对主库和所有承担读流量的备库分别执行本技能的扫描流程。
2. 只有当某个索引在**所有节点**上 `idx_scan` 均为 0 时，才能判定为"全局未使用"。
3. 如果应用做了读写分离（如通过中间件按 SQL 类型路由），务必确认扫描覆盖到实际承担查询的那个节点，而不是只查主库。

## 3. 外键约束与索引

KingbaseES **不会**为外键引用列自动创建索引（与 PostgreSQL 一致；这与 MySQL InnoDB 不同）。这意味着：

- 如果 DBA 手工为外键列建了索引以避免子表删除/父表更新时的全表扫描，这类索引即使 `idx_scan = 0`（因为它只在特定 DML 触发的隐式检查中被使用，而不是被显式 SELECT 使用），也不应被简单删除。
- SKILL.md 中的 `backs_constraint` 字段通过 `pg_constraint.conindid` 识别这种情况，命中时标记为"谨慎-不建议删除"。
- 如果确实要删除，需要先确认该外键关系的子表 DML 频率极低，且删除后可接受相应操作退化为全表扫描的性能代价。

## 4. 统计信息被重置的常见原因

- 手工执行 `SELECT pg_stat_reset();`（KingbaseES 同样支持）
- 实例重启（`pg_stat_*` 视图基于共享内存，重启后清零，`pg_postmaster_start_time()` 会变化但注意某些云厂商托管实例重启不等于统计重置，需以 `stats_reset` 字段为准）。
- 某些云厂商的托管服务会在维护窗口自动重启实例，此时看到 `idx_scan = 0` 可能只是维护窗口后的正常现象，务必检查 `stats_reset` 的实际时间。

## 5. 权限不足导致的漏报

- 普通业务账号在 `pg_stat_user_indexes` 中只能看到自己有权限访问的表对应的索引统计，其余对象不会出现在结果集里（而不是报错），容易让 Agent 误判为"该库没有更多索引"。
- 建议在报告开头显式声明当前使用账号的角色（是否具备 `sys_monitor` 或 superuser），并提示："如需完整扫描全部 schema，请使用具备 sys_monitor 角色或更高权限的账号重新执行。"
- KingbaseES 的 `sys_monitor` 角色是 PG `pg_monitor` 角色的同义映射；如使用 PG 风格的 `pg_monitor` 也能识别。

## 6. 表/索引本身处于极低频访问的正当业务场景

某些索引即使 `idx_scan = 0` 也可能是正当设计，例如：

- 支撑月末/季度末批处理任务的索引，若统计窗口不足一个月/一个季度，会被误判。
- 灾备/合规审计用途的表，平时几乎不被查询，但在稽核时会被使用。

处理建议：报告中不要给出"建议立即删除"这类绝对化结论，而是按 SKILL.md Step 4 的分级给出"观察-建议"式结论，最终删除决策交给业务方/DBA 确认。

## 7. KingbaseES 内置 schema 的特殊处理

KingbaseES 在安装时会创建一组系统 / 内置 schema，例如本实例可见的：

```
anon             -- 数据脱敏扩展
dbms_job         -- 兼容 Oracle DBMS_JOB
dbms_scheduler   -- 兼容 Oracle DBMS_SCHEDULER
kdb_schedule     -- KDB 调度子系统
perf             -- 性能视图（部分 AWR 风格指标）
src_restrict     -- 安全/受限对象
sys_catalog      -- 系统字典（sys_* 视图的宿主）
sys_hm           -- 健康监控
sysaudit         -- 审计
sysmac           -- 强制访问控制（MAC）
xlog_record_read -- WAL 解析辅助
```

这些 schema 中：

- `sys_catalog` / `sys_hm` / `sysaudit` / `sysmac` / `src_restrict` / `xlog_record_read` 等是金仓自身的元数据 / 安全 / 审计机制，**其索引为金仓内部维护所需，绝不应删除**。本 skill SQL 已通过 `n.nspname NOT IN (...)` 把它们过滤掉。
- `dbms_job` / `dbms_scheduler` / `kdb_schedule` 是调度子系统容器（通常无表无索引），过滤是防御性的。
- `anon` 是数据脱敏扩展容器，过滤是防御性的。
- `perf` 是 DBA 自建的性能 schema（默认空），保留以便 DBA 在此自定义视图。

如果 DBA 真的想审计内置 schema 的索引，请改用 `pg_stat_all_indexes` 并对结果逐条人工甄别，**不要**直接删除。

## 8. KingbaseES 原生 sys_* 视图与 pg_* 视图的关系

金仓提供两套等价视图：

| PG 兼容视图 (`pg_catalog`) | KingbaseES 原生 (`sys_catalog`) |
|----------------------------|-----------------------------------|
| `pg_stat_user_indexes`     | `sys_catalog.sys_stat_user_indexes` |
| `pg_index`                 | `sys_catalog.sys_index`           |
| `pg_constraint`            | `sys_catalog.sys_constraint`      |
| `pg_database`              | `sys_catalog.sys_database`        |
| `pg_class`                 | `sys_catalog.sys_class`           |
| `pg_namespace`             | `sys_catalog.sys_namespace`       |
| `pg_inherits`              | `sys_catalog.sys_inherits`        |
| `pg_partitioned_table`     | `sys_catalog.sys_partitioned_table` |

二者列名、列序、语义均一致，可互换。本 skill 统一走 `pg_*` 视图，是为了避免业务库 `search_path` 不包含 `sys_catalog` 时报"relation does not exist"。如果 DBA 偏好金仓原生视图，把脚本里的 `pg_` 前缀换成 `sys_catalog.sys_` 即可，前提是连接账号对 `sys_catalog` 有 USAGE 权限。

> 默认 `psql` 的 `search_path` 是 `"$user", public`，**不含 sys_catalog**。如果想直接用 `sys_stat_user_indexes`（不加 schema 限定），可以在 psql 中执行 `SET search_path TO sys_catalog, public;`，或者直接走本 skill 默认的 `pg_*` 系列。