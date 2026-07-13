# 执行计划诊断清单

按以下顺序逐层排查 `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` 输出。

## 1. 先看总耗时与顶层节点

- `Execution Time` 是否远大于用户可接受阈值；
- 顶层节点是 Limit/Sort/Aggregate/Gather 中的哪一种，决定后续关注重点。

## 2. 逐节点核对"估算 vs 实际"

每个计划节点都有 `rows=<估算> ... actual rows=<实际> loops=<次数>`。

- 偏差在 2~3 倍以内：正常范围；
- 偏差超过一个数量级：优化器统计信息或相关性建模失真，是绝大多数次优计划的根因，优先排查：
  - `pg_stat_user_tables.last_analyze` / `last_autoanalyze` 是否过旧；
  - 该列是否存在与其他列的相关性未被捕捉（考虑 `CREATE STATISTICS (dependencies)`）；
  - 是否有函数索引/表达式导致统计信息不适用。

## 3. 扫描方式是否合理

| 现象 | 可能问题 | 排查方向 |
|------|----------|----------|
| 大表上 Seq Scan，且上层有强选择性 Filter | 缺索引或索引失效 | 检查 `WHERE` 条件类型是否与索引列类型一致，是否有隐式类型转换/函数包裹 |
| Index Scan 但 `Rows Removed by Filter` 很高 | 索引选择性不足，只是"能用"但不是"好用" | 考虑复合索引把过滤条件也纳入 |
| Bitmap Heap Scan 出现 `Heap Blocks: exact` 变 `lossy` | `work_mem` 不足导致 bitmap 有损 | 提高 `work_mem` 或缩小结果集 |
| Index Only Scan 但 `Heap Fetches` 很高 | 可见性图（visibility map）陈旧，未真正走到"仅索引" | 检查 VACUUM 频率，考虑手动 VACUUM |

## 4. 连接方式是否合理

| 现象 | 可能问题 | 排查方向 |
|------|----------|----------|
| Nested Loop 驱动表估算行数远小于实际，导致对内表反复扫描 | 驱动表估算过低 | 修正统计信息；或改写 SQL 提示优化器（如拆分子查询、加 CTE 边界） |
| 大数据量下选择了 Merge Join 但两边都需要额外 Sort | 索引不支持天然有序输出 | 建复合索引匹配 Join 键顺序，消除多余 Sort |
| Hash Join 的 `Batches` 数很大（如 >1） | 哈希表溢出到磁盘，`work_mem` 不够 | 调大 `work_mem`/`hash_mem_multiplier`，或减少参与 Join 的行数（提前过滤） |

## 5. 排序与聚合

- `Sort Method: external merge  Disk: NkB` → 排序溢盘，调大 `work_mem`；
- `Sort Method: quicksort  Memory` → 内存排序，通常无需处理；
- `GroupAggregate` 前有额外 `Sort` 节点而 `HashAggregate` 本可避免排序 → 检查 `enable_hashjoin`/`work_mem` 是否限制了优化器选择 HashAggregate。

## 6. 并行执行

- 预期应并行但计划中无 `Gather`/`Workers Planned`：
  - 表/查询规模是否达到并行扫描阈值（`min_parallel_table_scan_size` 等）；
  - 查询中是否包含并行不安全的函数（自定义函数需标记 `PARALLEL SAFE`）；
  - `max_parallel_workers_per_gather`、`max_worker_processes`、`max_parallel_workers` 是否被占满。
- `Workers Planned` 与 `Workers Launched` 不一致 → 系统当前并行 worker 资源不足，是运行时资源争抢问题而非 SQL 本身问题。

## 7. CTE / 子查询

- PG12+ 默认 `NOT MATERIALIZED`（除非被引用多次或含副作用），若看到不期望的 `Materialize` 节点，检查是否可以显式加 `NOT MATERIALIZED` 提示消除额外物化开销；
- 反之，若一个 CTE 被多处引用且各处都重新计算，可显式加 `MATERIALIZED` 避免重复计算。

## 8. Buffers 统计（需要 `BUFFERS` 选项）

- `shared hit` 远小于 `shared read`：缓存命中率低，考虑是否 `shared_buffers`/`effective_cache_size` 设置过小，或该查询确实是冷数据的一次性扫描；
- `temp read`/`temp written` 出现：明确的磁盘临时文件使用（排序/哈希溢盘），是 `work_mem` 不足的直接证据。

## 9. JIT 开销

- 若 `JIT` 部分的 `Timing` 总和占 `Execution Time` 相当大比例，而查询本身数据量不大 → JIT 阈值设置不合理，考虑调高 `jit_above_cost` 或对短连接场景关闭 JIT。
