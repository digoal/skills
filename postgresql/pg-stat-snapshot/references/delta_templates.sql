-- ============================================================
-- pg-stat-snapshot / references / delta_templates.sql
-- 可直接替换 <begin_id> / <end_id> 后执行的差值分析模板。
-- 使用前必须先做一致性校验（见 SKILL.md Step 4）：
--   SELECT s1.source_reset_time = s2.source_reset_time
--   FROM stat_snapshot.snapshots s1, stat_snapshot.snapshots s2
--   WHERE s1.snapshot_id = <begin_id> AND s2.snapshot_id = <end_id>;
-- ============================================================

-- ------------------------------------------------------------
-- 1. TOP SQL 分析（pg_stat_statements 差值，按耗时排序）
-- ------------------------------------------------------------
SELECT
    e.queryid,
    e.query,
    e.calls - b.calls                              AS delta_calls,
    e.total_exec_time - b.total_exec_time            AS delta_total_time,
    e.rows - b.rows                                  AS delta_rows,
    CASE WHEN (e.calls - b.calls) > 0
         THEN (e.total_exec_time - b.total_exec_time) / (e.calls - b.calls)
         ELSE 0 END                                  AS delta_mean_time,
    e.shared_blks_hit - b.shared_blks_hit             AS delta_shared_blks_hit,
    e.shared_blks_read - b.shared_blks_read           AS delta_shared_blks_read
FROM stat_snapshot.stat_statements_history e
JOIN stat_snapshot.stat_statements_history b
  ON e.queryid = b.queryid AND e.dbid = b.dbid AND e.userid = b.userid
WHERE e.snapshot_id = <end_id>
  AND b.snapshot_id = <begin_id>
  AND e.calls >= b.calls   -- 过滤 reset/驱逐重建导致的负增长
ORDER BY delta_total_time DESC
LIMIT 20;

-- ------------------------------------------------------------
-- 2. 表级 DML 增量分析（pg_stat_user_tables 差值）
-- ------------------------------------------------------------
SELECT
    e.schemaname, e.relname,
    e.seq_scan - b.seq_scan               AS delta_seq_scan,
    e.seq_tup_read - b.seq_tup_read        AS delta_seq_tup_read,
    e.idx_scan - b.idx_scan                AS delta_idx_scan,
    e.n_tup_ins - b.n_tup_ins              AS delta_ins,
    e.n_tup_upd - b.n_tup_upd              AS delta_upd,
    e.n_tup_del - b.n_tup_del              AS delta_del,
    e.n_tup_hot_upd - b.n_tup_hot_upd      AS delta_hot_upd,
    e.n_dead_tup                           AS current_dead_tup,   -- 快照字段，取 end 值
    e.n_live_tup                           AS current_live_tup,
    e.last_autovacuum, e.last_autoanalyze  -- 快照字段，取 end 值即可
FROM stat_snapshot.stat_user_tables_history e
JOIN stat_snapshot.stat_user_tables_history b
  ON e.relid = b.relid
WHERE e.snapshot_id = <end_id>
  AND b.snapshot_id = <begin_id>
ORDER BY delta_ins + delta_upd + delta_del DESC
LIMIT 20;

-- ------------------------------------------------------------
-- 3. 索引使用增量分析（pg_stat_user_indexes 差值），用于找低效/零使用索引
-- ------------------------------------------------------------
SELECT
    e.schemaname, e.relname, e.indexrelname,
    e.idx_scan - b.idx_scan                AS delta_idx_scan,
    e.idx_tup_read - b.idx_tup_read        AS delta_idx_tup_read,
    e.idx_tup_fetch - b.idx_tup_fetch      AS delta_idx_tup_fetch
FROM stat_snapshot.stat_user_indexes_history e
JOIN stat_snapshot.stat_user_indexes_history b
  ON e.indexrelid = b.indexrelid
WHERE e.snapshot_id = <end_id>
  AND b.snapshot_id = <begin_id>
ORDER BY delta_idx_scan ASC   -- 升序：区间内几乎没被用到的索引排最前
LIMIT 20;

-- ------------------------------------------------------------
-- 4. IO 命中率增量分析（pg_statio_user_tables 差值），命中率是比率字段，
--    必须基于差值重新计算，不能对两个快照的命中率直接相减。
-- ------------------------------------------------------------
SELECT
    e.schemaname, e.relname,
    e.heap_blks_hit - b.heap_blks_hit      AS delta_heap_blks_hit,
    e.heap_blks_read - b.heap_blks_read    AS delta_heap_blks_read,
    CASE WHEN (e.heap_blks_hit - b.heap_blks_hit) + (e.heap_blks_read - b.heap_blks_read) > 0
         THEN round(
             100.0 * (e.heap_blks_hit - b.heap_blks_hit)
             / NULLIF((e.heap_blks_hit - b.heap_blks_hit) + (e.heap_blks_read - b.heap_blks_read), 0)
         , 2)
         ELSE NULL END                     AS delta_hit_ratio_pct
FROM stat_snapshot.statio_user_tables_history e
JOIN stat_snapshot.statio_user_tables_history b
  ON e.relid = b.relid
WHERE e.snapshot_id = <end_id>
  AND b.snapshot_id = <begin_id>
ORDER BY delta_heap_blks_read DESC
LIMIT 20;

-- ------------------------------------------------------------
-- 5. WAL 写入增量分析（pg_stat_wal 差值，PG14+，实例级只有一行，直接相减即可）
-- ------------------------------------------------------------
SELECT
    e.wal_records - b.wal_records          AS delta_wal_records,
    e.wal_bytes - b.wal_bytes              AS delta_wal_bytes,
    e.wal_fpi - b.wal_fpi                  AS delta_wal_fpi
FROM stat_snapshot.stat_wal_history e, stat_snapshot.stat_wal_history b
WHERE e.snapshot_id = <end_id>
  AND b.snapshot_id = <begin_id>;

-- ------------------------------------------------------------
-- 6. 直接调用通用差值函数（仅覆盖 pg_stat_statements 场景，见 ddl_core.sql）
-- ------------------------------------------------------------
-- SELECT * FROM stat_snapshot.compute_delta(<begin_id>, <end_id>) ORDER BY delta_total_time DESC LIMIT 20;
