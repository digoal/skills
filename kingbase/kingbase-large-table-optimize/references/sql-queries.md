# SQL 查询参考（阶段 1 & 2）— KingbaseES 版

以下所有查询均为只读 `SELECT`，需在**每个目标数据库分别连接后执行**（KingbaseES 与 PostgreSQL 一样不支持跨库查询）。`<N>` 表示 TOP N，默认 20；`<MIN_GB>` 表示最小大小阈值，默认 10GB。

所有查询均在 PG 兼容模式下基于 `pg_*` 目录视图编写（V9R1C10 实测可用）。

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
  AND n.nspname <> ALL (ARRAY[
    'pg_catalog', 'information_schema', 'pg_toast',
    'sys', 'sys_catalog', 'sys_hm', 'sysmac', 'sysaudit',
    'src_restrict', 'sys_anon'                 -- 金仓内置系统 schema，可按实例调整
  ])
ORDER BY total_bytes DESC
LIMIT <N>;
-- 或补充条件 WHERE pg_total_relation_size(c.oid) > <MIN_GB> * 1024^3
```

若目标表是分区表，`partition_count` 反映子分区数；各子分区的统计需通过 `pg_partition_tree` 单独汇总（见下文「分区表统计汇总」）。

## 1.2 膨胀修正

**近似法**（`kbstattuple` 未安装时使用）：

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

**精确法**（已装 `kbstattuple` 时，金仓等价于 PG 的 `pgstattuple`）。注意 `kbstattuple()` 会做全表扫描，成本较高，只对候选大表调用：

```sql
-- 实测精确膨胀：返回 table_len, tuple_count, tuple_len, tuple_percent,
-- dead_tuple_count, dead_tuple_len, dead_tuple_percent, free_space, free_percent
SELECT * FROM kbstattuple('schema_name.table_name');
-- 超大表可用抽样近似版本（更快）：
SELECT * FROM kbstattuple_approx('schema_name.table_name'::regclass);
```

**口径提醒（实测）**：`kbstattuple` 是堆物理扫描实测值；`n_dead_tup` 是自上次 VACUUM/autovacuum 以来的累计计数器（vacuum 后会清零）。两者在同一时刻可能明显不一致（如大 UPDATE 后立即采集 vs autovacuum 已触发后采集）。评估「物理可回收空间」以 `kbstattuple` 为准（可回收 ≈ `dead_tuple_percent` + `free_percent` 占表体大小的比例）；`n_dead_tup` 用于判断膨胀趋势与 autovacuum 触发压力。报告中同时呈现并注明 `last_autovacuum`。

计算逻辑（无 `kbstattuple` 时的近似法）：

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

**精确法**（已装 `kbstattuple` 时，金仓 `kbstatindex` 直接给出 B-Tree 精确层高 `tree_level`，优于按大小估算）：

```sql
-- 对候选表的每个索引执行；返回 version, tree_level, index_size,
-- root_block_no, internal_pages, leaf_pages, empty_pages, deleted_pages,
-- avg_leaf_density, leaf_fragmentation
SELECT * FROM kbstatindex('schema_name.index_name');
```

**估算法**（未装 `kbstattuple` 时的退化方案，先用 2.3 索引列表查询拿到大小再估算）：

```sql
SELECT
  s.schemaname, s.relname, s.indexrelname,
  s.idx_scan, s.idx_tup_read, s.idx_tup_fetch,
  pg_relation_size(s.indexrelid) AS index_bytes,
  am.amname AS index_type,
  pg_get_indexdef(s.indexrelid) AS index_def,
  s.indexrelid::regclass::text AS index_full_name
FROM pg_stat_user_indexes s
JOIN pg_class ic ON ic.oid = s.indexrelid
JOIN pg_am am ON am.oid = ic.relam
WHERE s.schemaname = '<schema>' AND s.relname = '<table>'
ORDER BY index_bytes DESC;
```

B-Tree 层高估算公式（块大小取 `current_setting('block_size')`，默认 8192；200 为经验扇出系数，仅用于数量级判断）：

```
估算层高 ≈ CEIL( LOG( index_bytes / 8192, 200 ) )
```

若需与精确层高交叉验证（需要 `pageinspect` 扩展，诊断性只读操作，但 `CREATE EXTENSION` 属 DDL，须用户授权）：

```sql
SELECT level FROM bt_metap('schema_name.index_name');  -- level 即 B-Tree 层高
```

**注意**：默认只用 `kbstatindex`（已装时）或大小估算（未装时），标注「估算值，非精确 B-Tree 层高」；`tree_level > 3` 标记「索引偏深」。

**字段形状提醒**：采集脚本输出的 `exact_btree_level` 是嵌套对象（含 `tree_level` / `index_size` / `leaf_pages` / `avg_leaf_density` 等字段），读取层高时用 `exact_btree_level.tree_level`；当 `kbstattuple` 未安装时该字段为 `null`，只能使用 `estimated_btree_level`。

**分区父表提醒**：`kbstattuple` / `pg_stat_user_tables` 对声明式分区父表（relkind='p'）通常不适用（父表本身无数据、可能无统计行、`reltuples=-1`），父表候选只用于 `pg_partition_tree` 汇总各叶子分区后再做膨胀/负载分析。

## 分区表统计汇总（当候选表本身是分区父表时）

```sql
SELECT relid::regclass AS partition_name, level, isleaf
FROM pg_partition_tree('schema_name.parent_table');
```

对每个叶子分区分别执行 1.2 / 2.1 / 2.2 / 2.3 的查询后再汇总（求和 DML 计数、取最大值判断热点分区，如最近分区的写入并发情况）。

## 附：时段性负载分析（可选）

`pg_stat_user_tables` 的计数器是累积值；若需要「业务高峰期 vs 低峰期」的差异分析，可在两个时间点分别采集快照做差值。KingbaseES 的查询统计在 `sys_stat_statements` 视图（注意不是 `pg_stat_statements`），可用于补充 TOP SQL 视角：

```sql
SELECT
  calls, total_exec_time, mean_exec_time, rows,
  shared_blks_read, local_blks_read
FROM sys_stat_statements
WHERE query ILIKE '%<table>%'
ORDER BY total_exec_time DESC
LIMIT 10;
```

KES 自带的 `sys_kwr` 扩展（工作负载仓库，AWR 风格）可作为时段性负载分析的交叉验证手段（`CREATE EXTENSION sys_kwr;` 属 DDL，须用户授权）。
