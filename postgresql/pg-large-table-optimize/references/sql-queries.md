# SQL 查询参考（阶段 1 & 2）

以下所有查询均为只读 `SELECT`，需在**每个目标数据库分别连接后**执行（PostgreSQL 不支持跨库查询）。`<N>` 表示 TOP N，默认 20；`<MIN_GB>` 表示最小大小阈值，默认 10GB。

## 1.1 大表初筛

```sql
SELECT
  n.nspname                                   AS schema_name,
  c.relname                                   AS table_name,
  pg_total_relation_size(c.oid)               AS total_bytes,
  pg_relation_size(c.oid)                     AS table_bytes,
  pg_indexes_size(c.oid)                      AS index_bytes,
  COALESCE(pg_total_relation_size(t.oid), 0)
    - COALESCE(pg_relation_size(t.oid), 0)    AS toast_bytes,
  c.reltuples::bigint                         AS est_rows,
  CASE WHEN p.partrelid IS NOT NULL THEN true ELSE false END AS is_partitioned,
  (SELECT count(*) FROM pg_inherits i WHERE i.inhparent = c.oid) AS partition_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_class t ON t.oid = c.reltoastrelid
LEFT JOIN pg_partitioned_table p ON p.partrelid = c.oid
WHERE c.relkind IN ('r', 'p')  -- 普通表 + 分区父表
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
ORDER BY total_bytes DESC
LIMIT <N>;
-- 或补充条件 WHERE pg_total_relation_size(c.oid) > <MIN_GB> * 1024^3
```

若目标表是分区表，`partition_count` 反映子分区数；子分区各自的统计需在 1.2/2.x 中通过 `pg_inherits` 单独汇总（见「Pitfalls」）。

## 1.2 膨胀修正

```sql
SELECT
  schemaname, relname,
  n_live_tup, n_dead_tup,
  CASE WHEN (n_live_tup + n_dead_tup) = 0 THEN 0
       ELSE round(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 2)
  END AS dead_tup_pct
FROM pg_stat_user_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema');
```

若 `pgstattuple` 扩展已安装，对候选大表可用更精确的实测值（注意 `pgstattuple` 会做一次全表扫描，成本较高，只对候选大表调用，不要对全库所有表调用）：

```sql
SELECT * FROM pgstattuple('schema_name.table_name');
-- 返回 table_len, tuple_count, dead_tuple_count, dead_tuple_percent, free_percent 等
```

计算逻辑（近似法，无 pgstattuple 时使用）：

- `估算膨胀大小 = 表本体大小(table_bytes) * dead_tup_pct/100 * 膨胀系数(默认1.0)`
- `修正后真实大小 = table_bytes - 估算膨胀大小`
- `dead_tup_pct > 20` → 标记「膨胀严重」

## 2.1 DML 活跃度

```sql
SELECT
  schemaname, relname,
  n_tup_ins, n_tup_upd, n_tup_del, n_tup_hot_upd,
  n_live_tup, n_dead_tup,
  last_vacuum, last_autovacuum, last_analyze, last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = '<schema>' AND relname = '<table>';
```

推导指标（分母为 0 时该指标标注「无数据」，不要报错）：

- 写入比率 = `n_tup_ins / (n_tup_ins + n_tup_upd + n_tup_del)`
- 更新比率 = `n_tup_upd / (n_tup_ins + n_tup_upd + n_tup_del)`
- HOT 更新效率 = `n_tup_hot_upd / n_tup_upd`（`n_tup_upd = 0` 时标「无更新记录」）
- DML 密度 = `(n_tup_ins + n_tup_upd + n_tup_del) / n_live_tup`（`n_live_tup = 0` 时标「无法计算」）

## 2.2 读取模式

```sql
SELECT
  schemaname, relname,
  seq_scan, seq_tup_read,
  idx_scan, idx_tup_fetch
FROM pg_stat_user_tables
WHERE schemaname = '<schema>' AND relname = '<table>';
```

推导指标：

- 索引使用率 = `idx_scan / (seq_scan + idx_scan)`
- 每次索引扫描平均行数 = `idx_tup_fetch / idx_scan`（`idx_scan = 0` 时标「无索引扫描记录」）
- 每次顺序扫描平均行数 = `seq_tup_read / seq_scan`（`seq_scan = 0` 时标「无顺序扫描记录」）

## 2.3 索引深度

```sql
SELECT
  s.schemaname, s.relname, s.indexrelname,
  s.idx_scan, s.idx_tup_read, s.idx_tup_fetch,
  pg_relation_size(s.indexrelid) AS index_bytes,
  am.amname AS index_type,
  pg_get_indexdef(s.indexrelid) AS index_def
FROM pg_stat_user_indexes s
JOIN pg_class ic ON ic.oid = s.indexrelid
JOIN pg_am am ON am.oid = ic.relam
WHERE s.schemaname = '<schema>' AND s.relname = '<table>'
ORDER BY index_bytes DESC;
```

B-Tree 层高估算（无需 `bt_metap`，用大小除以典型块数粗估，块大小取 `current_setting('block_size')`，默认 8192 字节；经验上单层 B-Tree 内部节点扇出约 100~300，可用如下简化公式做数量级估算）：

```
估算层高 ≈ CEIL( LOG( index_bytes / 8192, 200 ) )   -- 200 为经验扇出系数，仅用于数量级判断
```

若需要精确层高，可在候选索引上执行（需要 `pageinspect` 扩展，属于诊断性只读操作）：

```sql
CREATE EXTENSION IF NOT EXISTS pageinspect;  -- 需要用户确认是否允许安装扩展
SELECT level FROM bt_metap('schema_name.index_name');
```

**注意**：`CREATE EXTENSION` 属于 DDL，不在本技能默认执行范围内——只在用户明确同意后才建议执行，默认情况下仅用大小估算层高，标注「估算值，非精确 B-Tree 层高」。超过 3 层的标记为「索引偏深」。

## 分区表统计汇总（当候选表本身是分区父表时）

```sql
SELECT relid::regclass AS partition_name, level, isleaf
FROM pg_partition_tree('schema_name.parent_table');
```

对每个叶子分区分别执行 1.2/2.1/2.2/2.3 的查询后再汇总（求和 DML 计数、取最大值判断热点分区，如最近分区的写入并发情况）。
