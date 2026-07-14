# pg-sql-audit 逐条审查项详解

本文件是 SKILL.md 的详细展开版本，供审查过程中按需查阅。每个维度都给出：检查点、判断标准、典型修正写法。

## 维度 1：执行计划与索引分析

**检查点**
- 是否出现 `Seq Scan`（尤其是大表 n_live_tup 较大时）
- Join 顺序是否合理（是否先过滤小表再 Join 大表）
- 是否出现 `Sort` 且 `Sort Method: external merge`（说明 work_mem 不足，磁盘排序）
- 是否出现 `Rows Removed by Filter` 数值远大于最终返回行数（索引选择性差或索引失效）

**索引失效常见原因与修正**

| 失效写法 | 原因 | 修正写法 |
|---|---|---|
| `WHERE col::text = 'x'` | 隐式类型转换导致索引失效 | 保持列原始类型比较，或对参数做转换而非列 |
| `WHERE lower(col) = 'x'` 但索引建在 `col` 上 | 函数包裹列 | 建函数索引 `CREATE INDEX ON t (lower(col))`，或索引改为表达式索引 |
| `WHERE col + 1 = 100` | 列参与运算 | 改写为 `col = 99`，避免列侧运算 |
| `WHERE col LIKE '%abc'` | 前缀通配符无法用 btree | 考虑 `pg_trgm` + GIN/GIST，或调整业务查询方式 |

**索引建议分级**
- 高频 SQL（OLTP、每秒/每分钟级调用）：必须给出具体 `CREATE INDEX CONCURRENTLY` 建议
- 低频/一次性报表/批处理：仅提示"存在全表扫描，若非高频调用可暂不加索引"，避免过度索引增加写放大

## 维度 2：DDL 安全与锁风险评估

**表重写判定（会触发 ACCESS EXCLUSIVE 锁 + 全表重写）**
- `ALTER TABLE ... ALTER COLUMN TYPE`（多数类型转换，除非二进制兼容如 varchar 长度放宽）
- `ALTER TABLE ... ADD COLUMN ... DEFAULT <非常量表达式>`（PG 11 之前会重写；PG 11+ 常量默认值不重写，但函数/易变默认值仍会重写）
- `ALTER TABLE ... ADD CONSTRAINT ... CHECK (...)` 在未加 `NOT VALID` 时会全表扫描校验

**超时保护模板**
```sql
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '5min';
-- 具体 DDL 语句
ALTER TABLE ...;
COMMIT;
```
若未设置，必须在报告中标记 🔴 并给出以上模板。

**并发友好写法**
- 建索引：`CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_xxx ON tbl (col);`（不可在事务块内执行，需单独会话）
- 加约束：先 `ADD CONSTRAINT ... NOT VALID`，再择机 `VALIDATE CONSTRAINT`（VALIDATE 只加 SHARE UPDATE EXCLUSIVE 锁，不阻塞读写）
- 大表分批：`DELETE/UPDATE` 使用主键范围循环 + 每批间 `pg_sleep`，避免长事务

**依赖影响排查**
- 视图/物化视图依赖：`pg_depend` + `pg_rewrite` 联查
- 外键级联：`ALTER TABLE` 修改被引用列可能导致外键失效或级联锁
- 触发器：DDL 变更列可能导致触发器函数中引用的字段报错

## 维度 3：开发者规范与最佳实践

**规范检查清单**
- [ ] 禁止 `SELECT *`，必须显式列出所需列
- [ ] `INSERT` 必须显式列出列名，不依赖列顺序
- [ ] 命名统一 snake_case，不使用保留字（如 `user`、`order`、`group` 作表名/列名）
- [ ] 数据类型匹配业务语义（如金额用 `numeric` 而非 `float8`）

**批量操作分批模板**
```sql
-- 按主键范围循环删除，每批 5000 行，避免长事务和大量死元组
DO $$
DECLARE
  batch_size INT := 5000;
  affected INT;
BEGIN
  LOOP
    DELETE FROM tbl WHERE id IN (
      SELECT id FROM tbl WHERE <条件> LIMIT batch_size
    );
    GET DIAGNOSTICS affected = ROW_COUNT;
    EXIT WHEN affected = 0;
    COMMIT;
    PERFORM pg_sleep(0.1);
  END LOOP;
END $$;
```

**事务边界**
- 多步变更必须显式 `BEGIN...COMMIT`，避免中间态对外可见
- 警惕忘记 `COMMIT`/`ROLLBACK` 导致 `idle in transaction`，建议设置 `idle_in_transaction_session_timeout`

## 维度 4：回退机制与可恢复性

**DDL 回滚对照表**

| 变更操作 | 回滚语句 | 风险提示 |
|---|---|---|
| `ADD COLUMN` | `DROP COLUMN` | 数据丢失，且需重新执行同样耗时的操作才能恢复列 |
| `DROP COLUMN` | 无法直接回滚 | 必须提前 `CREATE TABLE bak AS SELECT` 备份 |
| `ALTER COLUMN TYPE` | 改回原类型 | 若已发生精度丢失（如 numeric→int）无法逆向恢复 |
| `CREATE INDEX` | `DROP INDEX CONCURRENTLY` | 风险低 |
| `DROP INDEX` | 重新 `CREATE INDEX` | 重建期间查询性能下降 |
| `RENAME` | 改回原名 | 需确认应用代码是否已同步使用新名 |

**DML 快照备份模板**
```sql
CREATE TABLE tbl_bak_20xx0101 AS
SELECT * FROM tbl WHERE <本次变更涉及的条件>;
```

## 维度 5：SQL 注入风险审查

**审查提示话术（必须原样提示用户确认）**

> 若应用层采用字符串拼接方式构造此 SQL，存在注入风险。请确保应用程序使用参数化查询（PreparedStatement）或存储过程变量绑定。需确认：应用端是否使用了 prepared statement？或是否在存储过程中通过 format、EXECUTE ... USING 等方式避免了注入？

**函数/存储过程中动态 SQL 检查点**
- `EXECUTE` 语句是否直接字符串拼接变量 → 🔴 高危
- 是否使用了 `quote_ident()` / `quote_literal()` 包裹标识符/字面量
- 是否使用了 `format('%I', ident)` / `format('%L', literal)` 安全格式化
- 是否通过 `EXECUTE ... USING` 传参而非拼接

**不安全示例 vs 安全示例**
```sql
-- 不安全：直接拼接
EXECUTE 'SELECT * FROM ' || tbl_name || ' WHERE id = ' || user_input;

-- 安全：标识符用 quote_ident/format %I，值用 USING 绑定
EXECUTE format('SELECT * FROM %I WHERE id = $1', tbl_name) USING user_input;
```

## 维度 6：触发器安全性审查

**检查点**
- 触发时机 `BEFORE`/`AFTER`/`INSTEAD OF` 是否符合业务预期
- 触发函数内是否有复杂查询（多表 Join、聚合）可能拖慢每行操作
- 是否修改了其他表（级联触发风险，需确认目标表触发器是否会反向触发回本表，形成递归）
- 是否有异常处理（`EXCEPTION` 块），未捕获异常会导致整个事务回滚
- 行级触发器 `FOR EACH ROW` 在批量 INSERT/UPDATE 场景下的开销评估（N 行 = N 次触发器调用）

**汇总表更新型触发器的性能放大提示**
若触发器逻辑是"每次插入都 UPDATE 汇总表"，批量导入 10 万行时会产生 10 万次汇总表更新，建议改为：
- 批量场景下临时禁用触发器（`ALTER TABLE ... DISABLE TRIGGER`），导入后统一重算汇总表
- 或将触发器改为语句级触发器（`FOR EACH STATEMENT`）+ transition table 批量处理

## 维度 7：高级环境关联风险评估

**统计信息过时判定**
- `last_analyze`/`last_autoanalyze` 距今超过 7 天且表有明显 DML 活动 → 建议先 `ANALYZE tbl;`

**长事务冲突排查语句**
```sql
SELECT pid, usename, state, xact_start, now()-xact_start AS age, left(query,120)
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start ASC;
```
若发现 DDL 目标表存在超过预期锁等待时间的长事务，警告"当前执行会阻塞在获取锁阶段，建议先处理长事务或选择低峰期"。

**复制延迟评估**
- 大批量 UPDATE/DELETE/DDL 会产生大量 WAL，评估对物理流复制延迟、逻辑复制槽堆积的影响
- 建议：大操作放在低峰期，分批执行，必要时监控 `pg_stat_replication` 的 `replay_lag`

**资源消耗评估**
- 结合 `work_mem`、`shared_buffers` 判断大排序/哈希 Join 是否会溢出到磁盘（对照执行计划中的 `Sort Method` / `Hash Batches`）
