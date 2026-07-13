# SQL 诊断框架（Playbook）

对每条 TOP SQL，按以下 6 个方向逐一排查，**只输出实际命中的方向**，避免逐条罗列无关项凑字数。

## 1. 缺少合适的索引

判断信号：
- 需要执行计划辅助确认（如用户授权，可对该 SQL 跑 `EXPLAIN (ANALYZE, BUFFERS)`）。
- 若无法拿到执行计划，可基于 SQL 文本粗判：WHERE/JOIN 条件列是否为高选择性列且大概率无索引（如非主键、非常见索引列）。
- 输出建议时注明置信度："基于统计信息推测"或"已通过执行计划确认"。

典型建议：
```sql
CREATE INDEX CONCURRENTLY idx_<table>_<col> ON <table>(<col>);
```
大表建索引建议加 `CONCURRENTLY` 避免锁表，并提示在低峰期执行。

## 2. 索引失效

常见触发模式：
- 隐式类型转换：如 `WHERE varchar_col = 123`（数字与字符串比较）。
- 函数包裹索引列：如 `WHERE lower(name) = 'x'`，需要改为函数索引或改写查询。
- 前导通配符 LIKE：如 `LIKE '%abc%'` 无法使用 B-tree 索引，需考虑 `pg_trgm` + GIN/GiST 索引。

典型建议：
```sql
-- 函数索引示例
CREATE INDEX CONCURRENTLY idx_<table>_lower_name ON <table>(lower(name));
-- 模糊搜索示例
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX CONCURRENTLY idx_<table>_name_trgm ON <table> USING gin (name gin_trgm_ops);
```

## 3. JOIN 顺序或方式不佳

信号：多表 JOIN 且 `rows` 异常大、`mean_exec_time` 高；或 SQL 文本显示大表在前小表在后但缺少驱动条件。

建议方向：确保 JOIN 列均有索引；必要时通过 `EXPLAIN` 确认是否发生了 Nested Loop 在大数据量下的性能问题，建议改写为先过滤再 JOIN，或提示 `SET enable_nestloop = off` 仅作诊断用途（不建议生产长期设置）。

## 4. 子查询可改写为 JOIN 或 EXISTS

信号：SQL 文本包含 `IN (SELECT ...)` 或相关子查询（correlated subquery）导致的重复执行。

典型建议：
```sql
-- 改写前
SELECT * FROM orders WHERE customer_id IN (SELECT id FROM customers WHERE region = 'x');
-- 改写后
SELECT o.* FROM orders o JOIN customers c ON o.customer_id = c.id WHERE c.region = 'x';
```

## 5. 返回数据量过大，缺少 LIMIT / 分页

信号：`rows / calls` 在"单次返回行数异常 TOP"中排名靠前，且业务场景通常不需要一次性拉取大量数据（如列表查询无分页）。

典型建议：加 `LIMIT` + 游标分页（基于索引列的 keyset pagination），避免 `OFFSET` 在大偏移量下的性能问题。

## 6. 频繁的 DML 可合并批量操作

信号：出现在"执行频率 TOP"或"WAL 生成量 TOP"，且为单行 INSERT/UPDATE/DELETE 高频执行。

典型建议：
- 应用层合并为批量 `INSERT ... VALUES (...), (...), ...`
- 或使用 `COPY` 做批量导入
- 高频小事务的 UPDATE 可评估是否可以合并为单次批量 UPDATE（用临时表 + JOIN UPDATE）

## 建议输出的保守原则

- 不建议删除现有索引/约束，除非用户明确要求做索引瘦身分析。
- 不建议直接修改生产参数（如 `shared_buffers`）作为单条 SQL 的优化手段，除非该问题明显是全局配置引起（如缓存命中率全局偏低）。
- 所有 DDL 建议注明"建议先在测试环境验证，确认无锁表风险后再上生产，大表操作使用 CONCURRENTLY"。
