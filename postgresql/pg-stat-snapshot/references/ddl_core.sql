-- ============================================================
-- pg-stat-snapshot / references / ddl_core.sql
-- 核心基础设施：快照元数据表 + 实例级历史表（pg_stat_statements, pg_stat_activity）
-- 在 postgres 库（或任意固定的"控制库"）中执行一次即可，全部使用 IF NOT EXISTS，可重复执行。
-- ============================================================

CREATE SCHEMA IF NOT EXISTS stat_snapshot;

-- ------------------------------------------------------------
-- 1. 快照元数据表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stat_snapshot.snapshots (
    snapshot_id        bigserial PRIMARY KEY,
    snapshot_time       timestamptz NOT NULL DEFAULT now(),
    snapshot_level      text NOT NULL CHECK (snapshot_level IN ('instance','database')),
    database_name       text,                 -- NULL 表示实例级快照
    source_reset_time   timestamptz,          -- 对应源视图上次 reset 的时间，用于差值一致性校验
    comment             text
);

CREATE INDEX IF NOT EXISTS idx_snapshots_time
    ON stat_snapshot.snapshots (snapshot_time);
CREATE INDEX IF NOT EXISTS idx_snapshots_db_time
    ON stat_snapshot.snapshots (database_name, snapshot_time);
CREATE INDEX IF NOT EXISTS idx_snapshots_level_time
    ON stat_snapshot.snapshots (snapshot_level, snapshot_time);

-- ------------------------------------------------------------
-- 2. pg_stat_statements 历史表（实例级，最重要，动态建表适配版本差异）
--    query 字段跟随 track_activity_query_size，这里统一用 text 避免二次截断。
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'stat_snapshot' AND table_name = 'stat_statements_history'
    ) THEN
        EXECUTE '
            CREATE TABLE stat_snapshot.stat_statements_history AS
            SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, s.*
            FROM pg_stat_statements s
            LIMIT 0
        ';
        EXECUTE 'ALTER TABLE stat_snapshot.stat_statements_history ALTER COLUMN snapshot_id DROP DEFAULT';
        -- query 字段容易因驱动/版本差异被限定长度，强制放宽为 text
        EXECUTE 'ALTER TABLE stat_snapshot.stat_statements_history ALTER COLUMN query TYPE text';
        EXECUTE 'CREATE INDEX idx_ssh_snapshot_id ON stat_snapshot.stat_statements_history (snapshot_id)';
        EXECUTE 'CREATE INDEX idx_ssh_queryid ON stat_snapshot.stat_statements_history (queryid)';
        EXECUTE 'CREATE INDEX idx_ssh_snapshot_time ON stat_snapshot.stat_statements_history (snapshot_time)';
    END IF;
END $$;

-- ------------------------------------------------------------
-- 3. pg_stat_activity 历史表（实例级，瞬时快照切片，不做差值，仅用于历史回溯）
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'stat_snapshot' AND table_name = 'stat_activity_history'
    ) THEN
        EXECUTE '
            CREATE TABLE stat_snapshot.stat_activity_history AS
            SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, a.*
            FROM pg_stat_activity a
            LIMIT 0
        ';
        EXECUTE 'ALTER TABLE stat_snapshot.stat_activity_history ALTER COLUMN snapshot_id DROP DEFAULT';
        EXECUTE 'ALTER TABLE stat_snapshot.stat_activity_history ALTER COLUMN query TYPE text';
        EXECUTE 'CREATE INDEX idx_sah_snapshot_id ON stat_snapshot.stat_activity_history (snapshot_id)';
        EXECUTE 'CREATE INDEX idx_sah_snapshot_time ON stat_snapshot.stat_activity_history (snapshot_time)';
        EXECUTE 'CREATE INDEX idx_sah_pid ON stat_snapshot.stat_activity_history (pid)';
    END IF;
END $$;

-- ------------------------------------------------------------
-- 4. 结构比对：检测源视图新增/移除字段（用于 Step 1.3 的存量实例升级检查）
--    使用方法：把 :view_name / :history_table 替换为实际值后执行
-- ------------------------------------------------------------
-- 示例：检测 pg_stat_statements 相对历史表新增的字段
-- SELECT a.attname
-- FROM pg_attribute a
-- JOIN pg_class c ON a.attrelid = c.oid
-- JOIN pg_namespace n ON c.relnamespace = n.oid
-- WHERE n.nspname = 'pg_catalog' AND c.relname = 'pg_stat_statements'
--   AND a.attnum > 0 AND NOT a.attisdropped
-- EXCEPT
-- SELECT column_name FROM information_schema.columns
-- WHERE table_schema = 'stat_snapshot' AND table_name = 'stat_statements_history';

-- ------------------------------------------------------------
-- 5. 通用差值计算函数
--    仅覆盖 pg_stat_statements 场景（最常用）；表/索引/IO 差值请直接使用
--    delta_templates.sql 中的模板 SQL，字段语义差异较大，不适合硬编码进单个函数。
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION stat_snapshot.compute_delta(
    snapshot_id_begin bigint,
    snapshot_id_end   bigint
)
RETURNS TABLE (
    queryid            bigint,
    query              text,
    delta_calls        bigint,
    delta_total_time   double precision,
    delta_rows         bigint,
    delta_mean_time    double precision
)
LANGUAGE plpgsql
AS $$
DECLARE
    reset_begin timestamptz;
    reset_end   timestamptz;
BEGIN
    SELECT source_reset_time INTO reset_begin FROM stat_snapshot.snapshots WHERE snapshot_id = snapshot_id_begin;
    SELECT source_reset_time INTO reset_end   FROM stat_snapshot.snapshots WHERE snapshot_id = snapshot_id_end;

    IF reset_begin IS DISTINCT FROM reset_end THEN
        RAISE EXCEPTION '快照区间内发生过统计重置（begin reset_time=% , end reset_time=%），差值无效', reset_begin, reset_end;
    END IF;

    RETURN QUERY
    SELECT
        e.queryid,
        e.query,
        (e.calls - b.calls)               AS delta_calls,
        (e.total_exec_time - b.total_exec_time) AS delta_total_time,
        (e.rows - b.rows)                 AS delta_rows,
        CASE WHEN (e.calls - b.calls) > 0
             THEN (e.total_exec_time - b.total_exec_time) / (e.calls - b.calls)
             ELSE 0
        END AS delta_mean_time
    FROM stat_snapshot.stat_statements_history e
    JOIN stat_snapshot.stat_statements_history b
      ON e.queryid = b.queryid AND e.dbid = b.dbid AND e.userid = b.userid
    WHERE e.snapshot_id = snapshot_id_end
      AND b.snapshot_id = snapshot_id_begin
      AND e.calls >= b.calls;  -- 过滤疑似驱逐重建/reset 导致的负增长条目
END;
$$;

COMMENT ON FUNCTION stat_snapshot.compute_delta(bigint, bigint) IS
    'pg_stat_statements 两个快照之间的差值计算，自动校验 reset 一致性并过滤负增长条目';
