# 金仓 GUC 参数速查表（SQL 调优相关）

采集方式：`SELECT name, setting, unit, category, short_desc FROM pg_settings WHERE name IN (...);`
或对单个参数直接 `SHOW <name>;`

> 本表参数已在 KingbaseES V009R001C010（PG 兼容模式，server_version_num=120001）实测存在。
> **注意：`hash_mem_multiplier` 是 PG13+ 特性，V9R1C10 实测不存在**，Hash 相关溢盘只能调 `work_mem`。

## 内存类

| 参数 | 作用 | 调优提示 |
|------|------|----------|
| `work_mem` | 单个排序/哈希操作可用内存，每个并发的每个操作节点独立占用 | 优先语句级 `SET work_mem`；全局调大会被 `连接数 × 并发排序节点数` 放大，需结合 `max_connections` 评估 |
| `shared_buffers` | 共享内存缓冲区大小 | 一般建议物理内存的 25%，需重启生效，改动前评估是否需要业务窗口 |
| `effective_cache_size` | 告诉优化器操作系统层大致可用缓存，不实际分配内存 | 影响索引扫描 vs 全表扫描的代价估算，通常设为物理内存的 50%~75% |
| `maintenance_work_mem` | `VACUUM`/`CREATE INDEX`/`ALTER TABLE` 等维护操作用内存 | 建索引慢可临时调大，不影响正常查询 |

## 代价模型类（影响优化器选择计划）

| 参数 | 作用 | 调优提示 |
|------|------|----------|
| `random_page_cost` | 随机读一页的相对代价（默认 4.0） | SSD/云盘环境可调低至 1.1~2.0，会让优化器更倾向选索引扫描 |
| `seq_page_cost` | 顺序读一页的相对代价（默认 1.0） | 一般不动，作为基准 |
| `cpu_tuple_cost` / `cpu_index_tuple_cost` / `cpu_operator_cost` | CPU 处理每行/索引项/操作符的相对代价 | 极少需要调，除非有明显证据表明 CPU 密集型计划被低估代价 |
| `effective_io_concurrency` | 单个会话预取的并发 IO 数（bitmap heap scan 生效） | SSD/云盘可适当调大（如 200），机械盘保持默认 |

## 并行查询类

| 参数 | 作用 | 调优提示 |
|------|------|----------|
| `max_parallel_workers_per_gather` | 单个 Gather 节点最多并行 worker 数 | 默认 2，CPU 核数充裕时可提高，但要看 `max_worker_processes`/`max_parallel_workers` 总量是否够分配 |
| `parallel_setup_cost` / `parallel_tuple_cost` | 启动/传递并行 worker 的代价 | 调低会让优化器更倾向并行计划，小心小查询也被并行化反而变慢 |
| `min_parallel_table_scan_size` / `min_parallel_index_scan_size` | 触发并行扫描的最小对象大小 | 小表不会走并行，属预期行为 |

## 计划器行为开关（仅用于诊断对比，不建议线上长期关闭）

`enable_seqscan` / `enable_indexscan` / `enable_indexonlyscan` / `enable_bitmapscan` / `enable_nestloop` / `enable_hashjoin` / `enable_mergejoin` / `enable_material` / `enable_sort`

诊断用法：临时 `SET enable_seqscan = off;` 后重新 EXPLAIN，对比计划变化，验证"优化器是否只是选择了次优计划"还是"确实没有更优路径"。诊断完成后必须 `RESET` 或话束会话，不带回业务连接。

## JIT

| 参数 | 说明 |
|------|------|
| `jit` | 是否启用即时编译（PG11+/金仓默认开） |
| `jit_above_cost` / `jit_inline_above_cost` / `jit_optimize_above_cost` | 触发 JIT 各阶段的代价阈值 |

计划中出现较长 `JIT: Functions ... Timing: Generation ...` 且原始执行时间很短时，说明 JIT 编译开销占比过高，可考虑调高阈值或对短查询连接池关闭 JIT。

## 统计信息与采样

| 参数 | 说明 |
|------|------|
| `default_statistics_target` | 全局默认统计信息采样目标（默认 100） | 对高基数、分布不均的列可单独 `ALTER TABLE ... ALTER COLUMN ... SET STATISTICS N` 提高到 500~1000 |

## 会话安全（本 skill 强制设置）

| 参数 | 说明 |
|------|------|
| `statement_timeout` | 单条语句超时（毫秒），防止 EXPLAIN ANALYZE 长跑。脚本默认 30s，DML 建议更保守如 10s |
| `lock_timeout` | 拿不到锁就放弃（毫秒），避免锁等待链 |
| `idle_in_transaction_session_timeout` | 事务空闲超时，防止忘记提交/回滚导致长事务 |

## 金仓特有注意

- 全局配置文件是 `kingbase.conf`（`SHOW config_file;` 确认路径），不是 `postgresql.conf`；
- 调优前用 `SHOW database_mode;` 确认是 `pg` 兼容模式（本 skill 假设如此）；
- 需要查询历史语句统计时用 `sys_stat_statements`（public schema），`pg_stat_statements` 默认不存在。
