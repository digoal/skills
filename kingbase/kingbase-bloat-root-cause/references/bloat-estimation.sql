-- ============================================================
-- kingbase-bloat-root-cause: 基于统计信息的膨胀估算方法
-- 用途：KingbaseES 默认无 pgstattuple 扩展，使用统计信息做粗略估算
-- 说明：以下方法给出的是估算值，非精确值，报告中必须注明"估算"字样
-- ============================================================

-- 方法一：基于 n_dead_tup 与平均行宽的粗略估算（最简单，适合初筛）
SELECT
    n.nspname AS schemaname,
    c.relname,
    s.n_live_tup,
    s.n_dead_tup,
    round((100.0 * s.n_dead_tup / NULLIF(s.n_live_tup + s.n_dead_tup, 0))::numeric, 2) AS dead_tuple_pct,
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
-- 该方法对有大量变长字段 / TOAST 的表精度有限，仅作为精确方法不可用时的补充参考，
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
  AND n.nspname NOT LIKE 'sys_%'   -- 排除 KingbaseES 系统 schema
ORDER BY c.relpages DESC
LIMIT 100;

-- 方法三（KingbaseES 特有）：sys_recovery 精确读取死元组详情
-- 仅当 sys_recovery 扩展已安装时可用：
--   CREATE EXTENSION sys_recovery;
-- 该扩展基于 MVCC 可见性扫描，对大表会消耗较多 IO，建议只对初筛 top 10 调用。
-- 函数签名：sys_recovery(regclass, recoveryrow bool DEFAULT true) → 记录集
-- 调用示例（务必限定单表 + LIMIT）：
--   SELECT count(*) AS dead_tuple_count
--   FROM sys_recovery('schema.table_name'::regclass, false);

-- 索引膨胀初筛：索引大小相对于表行数明显偏大时值得关注
-- 注意：KingbaseES 的 pg_stat_user_indexes 没有 last_idx_scan 字段
--（该字段在 PG13+ 已移除，KingbaseES 沿用 PG12 早期视图结构）
SELECT
    n.nspname AS schemaname,
    t.relname AS table_name,
    i.relname AS index_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch
FROM pg_index x
JOIN pg_class i ON i.oid = x.indexrelid
JOIN pg_class t ON t.oid = x.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
LEFT JOIN pg_stat_user_indexes s ON s.indexrelid = i.oid
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
  AND n.nspname NOT LIKE 'sys_%'   -- 排除 KingbaseES 系统 schema
ORDER BY pg_relation_size(i.oid) DESC
LIMIT 100;

-- 使用建议：
-- 1. 先用方法一做全库初筛，按 dead_tuple_pct 排序；
-- 2. 对 dead_tuple_pct > 20% 或 estimated_bloat_size 排名前列的对象，
--    如已安装 sys_recovery，再用 sys_recovery('schema.relname', false) 精确读取死元组；
--    压缩完成后可通过对比 pg_relation_size 前后变化得到精确回收量。
-- 3. 索引膨胀通常伴随对应表的高频 UPDATE/DELETE，结合 [CAUSE-1]~[CAUSE-6]
--    的因果链一并判断，不要孤立地看索引大小。
-- 4. 如需物理回收空间：
--    a. 业务低峰期首选 KingbaseES 的 sys_repack 命令行（无需 logical 槽位）
--       sys_repack -h <host> -p <port> -U <user> -d <db> --table schema.table
--    b. 或先启用 sys_squeeze（需要 wal_level=logical + max_replication_slots≥1 + 重启）
--       SELECT squeeze.squeeze_table('schema', 'table');