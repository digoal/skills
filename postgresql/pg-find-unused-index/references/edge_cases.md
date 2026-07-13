# 边界情况补充说明

本文档补充 SKILL.md 中未展开的细节，供 Agent 在遇到对应场景时按需查阅。

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

## 2. 流复制主备架构

`pg_stat_user_indexes` 的统计是**每个物理节点独立维护**的：

- 只读查询打到备库上，只会累加备库自己的 `idx_scan`，主库对应索引的 `idx_scan` 不会变化。
- 反之，写路径（INSERT/UPDATE/DELETE 触发的索引维护）不产生 `idx_scan`，`idx_scan` 只反映**读扫描**次数。

因此：

1. 必须对主库和所有承担读流量的备库分别执行本技能的扫描流程。
2. 只有当某个索引在**所有节点**上 `idx_scan` 均为 0 时，才能判定为"全局未使用"。
3. 如果应用做了读写分离（如通过 pgpool/pgbouncer/中间件按 SQL 类型路由），务必确认扫描�covering 到实际承担查询的那个节点，而不是只查主库。

## 3. 外键约束与索引

PostgreSQL **不会**为外键引用列自动创建索引（这与 MySQL InnoDB 不同）。这意味着：

- 如果 DBA 手工为外键列建了索引以避免子表删除/父表更新时的全表扫描，这类索引即使 `idx_scan = 0`（因为它只在特定 DML 触发的隐式检查中被使用，而不是被显式 SELECT 使用），也不应被简单删除。
- SKILL.md 中的 `backs_constraint` 字段通过 `pg_constraint.conindid` 识别这种情况，命中时标记为"谨慎-不建议删除"。
- 如果确实要删除，需要先确认该外键关系的子表 DML 频率极低，且删除后可接受相应操作退化为全表扫描的性能代价。

## 4. 统计信息被重置的常见原因

- 手工执行 `SELECT pg_stat_reset();`
- 实例重启（`pg_stat_*` 视图基于共享内存，重启后清零，`pg_postmaster_start_time()` 会变化但注意某些云厂商托管实例重启不等于统计重置，需以 `stats_reset` 字段为准）。
- 某些云厂商的托管 PG 服务会在维护窗口自动重启实例，此时看到 `idx_scan = 0` 可能只是维护窗口后的正常现象，务必检查 `stats_reset` 的实际时间。

## 5. 权限不足导致的漏报

- 普通业务账号在 `pg_stat_user_indexes` 中只能看到自己有权限访问的表对应的索引统计，其余对象不会出现在结果集里（而不是报错），容易让 Agent 误判为"该库没有更多索引"。
- 建议在报告开头显式声明当前使用账号的角色（是否具备 `pg_monitor` 或 superuser），并提示："如需完整扫描全部 schema，请使用具备 pg_monitor 角色或更高权限的账号重新执行。"

## 6. 表/索引本身处于极低频访问的正当业务场景

某些索引即使 `idx_scan = 0` 也可能是正当设计，例如：

- 支撑月末/季度末批处理任务的索引，若统计窗口不足一个月/一个季度，会被误判。
- 灾备/合规审计用途的表，平时几乎不被查询，但在稽核时会被使用。

处理建议：报告中不要给出"建议立即删除"这类绝对化结论，而是按 SKILL.md Step 4 的分级给出"观察-建议"式结论，最终删除决策交给业务方/DBA 确认。
