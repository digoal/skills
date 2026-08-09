# 根因判断模式 & AWS Performance Insights 概念映射

## 根因判断模式（用于 Step 6）

| 观测模式 | 疑似根因 | 建议核实方式 |
|---|---|---|
| WHERE 有过滤条件，但 `delta_shared_blks_read` 很高、缓存命中率低 | 索引缺失 | 对目标表执行 `EXPLAIN (ANALYZE, BUFFERS)` 确认是否 Seq Scan |
| WHERE 条件中字段被函数包裹（如 `WHERE date_trunc('day', col) = ...`）或存在隐式类型转换 | 索引失效 | 检查列类型与常量类型是否一致，考虑函数索引或改写谓词 |
| `delta_rows` 很大但 `delta_calls` 不高 | 分析型大查询，非高频问题 | 确认是否为报表/批处理任务，评估是否需要专用只读实例分流 |
| `delta_calls` 很高但单次 `avg_latency_ms` 很低 | 高频小查询（ORM N+1 / 缓存未命中的点查） | 检查应用层是否可批量查询（IN 替代循环单查）或引入缓存 |
| 高频 UPDATE/DELETE 且 `pg_stat_activity_snapshot` 中 `wait_event_type='Lock'` 出现频次高 | 锁竞争 | 检查事务是否过长、是否可拆分批次、是否有共同热点行 |
| `delta_total_parse_time`/`delta_total_plan_time` 明显高于 `delta_total_exec_time` 的合理比例（金仓特色） | 硬解析/重规划开销大 | 检查应用是否未复用 prepared statement、`parses` 是否明显高于 `calls` |
| `parses` 增量明显高于 `calls` 增量（Parse-to-Exec > 1.2）（金仓特色） | 连接池未复用 prepared statement | 检查应用是否走 PreparedStatement 缓存 |
| AAS 接近/超过 vCPU 数，且 Top SQL 以低 IO 为主 | CPU 瓶颈 | 检查是否有复杂计算（排序、聚合、JSON处理）可优化 |
| `shared_blks_read` 占比高、缓存命中率持续偏低 | IO/内存瓶颈 | 评估 `shared_buffers` 是否偏小，或工作集是否远超内存 |
| 活跃连接数接近 `max_connections` | 连接数瓶颈 | 评估是否需要连接池或调大 `max_connections` |

以上均为**推断**，非确定性结论，报告中应使用"疑似"、"推断为"等措辞，并给出可供用户自行核实的具体方法（如 EXPLAIN）。

## AWS Performance Insights 概念映射

| AWS PI 概念 | 本报告对应内容 |
|---|---|
| Database Load (AAS) | 平均活跃会话数 |
| Top SQL | 按总耗时排序的 TOP SQL |
| Top Waits | 等待事件分布 |
| By Database | 按数据库负载拆解 |
| By User/Application | 按用户/应用负载拆解 |
| Counter Metrics | 调用次数、IO 读、解析规划耗时等 |
| 性能洞察建议 | 关键发现与根因分析 + 优化优先级 |

## KingbaseES 与 PostgreSQL 差异备忘

| 维度 | PostgreSQL | KingbaseES (KES V9R1C10) |
|---|---|---|
| Top SQL 取数视图 | `pg_stat_statements` | `sys_stat_statements`（或 `sys_catalog.sys_stat_statements`） |
| 快照表对应名 | `{schema}.pg_stat_statements_snapshot` | `{schema}.sys_stat_statements_snapshot` |
| WAL 生成量字段 | `wal_bytes`（PG13+） | **无**，WAL 维度跳过 |
| 解析/规划耗时 | 无（PG13 只有 plan 部分字段） | 有 `parses/plans/total_parse_time/total_plan_time`（金仓特色） |
| 统计 reset 视图 | `pg_stat_statements_info`（PG13+） | **无**，依赖快照表 `source_reset_time` 校验 |
| 跨库视图 | 无 | `sys_stat_statements_all`（含 `parent_queryid`） |
| 实例启动时间 | `pg_postmaster_start_time()` | 同 |
| 客户端 | psql | ksql（语法兼容）/ psql 均可 |
