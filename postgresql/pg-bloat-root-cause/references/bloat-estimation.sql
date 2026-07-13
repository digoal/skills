-- ============================================================
-- pg-bloat-root-cause: 基于统计信息的膨胀估算方法
-- 用途：当目标库无法安装/使用 pgstattuple 扩展时的降级方案
-- 说明：以下方法给出的是估算值，非精确值，报告中必须注明"估算"字样
-- ============================================================

-- 方法一：基于 n_dead_tup 与平均行宽的粗略估算（最简单，适合初筛）
SELECT
    n.nspname AS schemaname,
    c.relname,
    s.n_live_tup,
    s.n_dead_tup,
    round(100.0 * s.n_dead_tup / NULLIF(s.n_live_tup + s.n_dead_tup, 0), 2) AS dead_tuple_pct,
    pg_size_pretty(pg_relation_size(c.oid)) AS table_size,
    pg_size_pretty(
        (pg_relation_size(c.oid)::numeric
         * s.n_dead_tup / NULLIF(s.n_live_tup + s.n_dead_tup, 0))::bigint
    ) AS estimated_bloat_size,
    s.last_autovacuum,
    s.last_autoanalyze
FROM pg_stat_user_tables s
JOIN pg_class c ON c.oid = s.relid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE s.n_live_tup + s.n_dead_tup > 0
ORDER BY dead_tuple_pct DESC NULLS LAST
LIMIT 100;

-- 方法二：经典社区 bloat 估算查询思路（基于 pg_class.reltuples / relpages 与理论页大小对比）
-- 原理：理论最优页数 = ceil(reltuples * 平均行大小 / 每页可用空间)
--       实际页数 relpages 明显大于理论页数即为膨胀
-- 该方法对有大量变长字段 / TOAST 的表精度有限，仅作为 pgstattuple 不可用时的补充参考，
-- 建议将结果与方法一交叉验证后再下结论。

SELECT
    n.nspname AS schemaname,
    c.relname,
    c.reltuples::bigint AS estimated_row_count,
    c.relpages AS actual_pages,
    pg_size_pretty(c.relpages::bigint * 8192) AS actual_size,
    c.relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'i')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
ORDER BY c.relpages DESC
LIMIT 100;

-- 索引膨胀初筛：索引大小相对于表行数明显偏大时值得关注
SELECT
    n.nspname AS schemaname,
    t.relname AS table_name,
    i.relname AS index_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size,
    s.idx_scan,
    s.last_idx_scan
FROM pg_index x
JOIN pg_class i ON i.oid = x.indexrelid
JOIN pg_class t ON t.oid = x.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
LEFT JOIN pg_stat_user_indexes s ON s.indexrelid = i.oid
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
ORDER BY pg_relation_size(i.oid) DESC
LIMIT 100;

-- 使用建议：
-- 1. 先用方法一做全库初筛，按 dead_tuple_pct 排序；
-- 2. 对 dead_tuple_pct > 20% 或 estimated_bloat_size 排名前列的对象，
--    如已安装 pgstattuple，再用 pgstattuple('schema.relname') 精确核实；
-- 3. 索引膨胀通常伴随对应表的高频 UPDATE/DELETE，结合 [CAUSE-1]~[CAUSE-6]
--    的因果链一并判断，不要孤立地看索引大小。
