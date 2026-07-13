-- ============================================================
-- pg-stat-snapshot / references / ddl_perdb.sql
-- 库级历史表：需要连接到每一个非模板数据库分别执行一次（IF NOT EXISTS，可重复执行）。
-- 遍历库列表：SELECT datname FROM pg_database WHERE datistemplate = false;
-- ============================================================

CREATE SCHEMA IF NOT EXISTS stat_snapshot;

-- ------------------------------------------------------------
-- 1. pg_stat_user_tables 历史表（表级 DML/扫描活跃度，膨胀估算依赖此表）
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'stat_snapshot' AND table_name = 'stat_user_tables_history'
    ) THEN
        EXECUTE '
            CREATE TABLE stat_snapshot.stat_user_tables_history AS
            SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, t.*
            FROM pg_stat_user_tables t
            LIMIT 0
        ';
        EXECUTE 'ALTER TABLE stat_snapshot.stat_user_tables_history ALTER COLUMN snapshot_id DROP DEFAULT';
        EXECUTE 'CREATE INDEX idx_suth_snapshot_id ON stat_snapshot.stat_user_tables_history (snapshot_id)';
        EXECUTE 'CREATE INDEX idx_suth_relid ON stat_snapshot.stat_user_tables_history (relid)';
    END IF;
END $$;

-- ------------------------------------------------------------
-- 2. pg_stat_user_indexes 历史表（索引使用频率/扫描量差值分析）
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'stat_snapshot' AND table_name = 'stat_user_indexes_history'
    ) THEN
        EXECUTE '
            CREATE TABLE stat_snapshot.stat_user_indexes_history AS
            SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, i.*
            FROM pg_stat_user_indexes i
            LIMIT 0
        ';
        EXECUTE 'ALTER TABLE stat_snapshot.stat_user_indexes_history ALTER COLUMN snapshot_id DROP DEFAULT';
        EXECUTE 'CREATE INDEX idx_suih_snapshot_id ON stat_snapshot.stat_user_indexes_history (snapshot_id)';
        EXECUTE 'CREATE INDEX idx_suih_indexrelid ON stat_snapshot.stat_user_indexes_history (indexrelid)';
    END IF;
END $$;

-- ------------------------------------------------------------
-- 3. pg_statio_user_tables / pg_statio_user_indexes 历史表（IO 命中率分析）
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'stat_snapshot' AND table_name = 'statio_user_tables_history'
    ) THEN
        EXECUTE '
            CREATE TABLE stat_snapshot.statio_user_tables_history AS
            SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, t.*
            FROM pg_statio_user_tables t
            LIMIT 0
        ';
        EXECUTE 'ALTER TABLE stat_snapshot.statio_user_tables_history ALTER COLUMN snapshot_id DROP DEFAULT';
        EXECUTE 'CREATE INDEX idx_siuth_snapshot_id ON stat_snapshot.statio_user_tables_history (snapshot_id)';
        EXECUTE 'CREATE INDEX idx_siuth_relid ON stat_snapshot.statio_user_tables_history (relid)';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'stat_snapshot' AND table_name = 'statio_user_indexes_history'
    ) THEN
        EXECUTE '
            CREATE TABLE stat_snapshot.statio_user_indexes_history AS
            SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, i.*
            FROM pg_statio_user_indexes i
            LIMIT 0
        ';
        EXECUTE 'ALTER TABLE stat_snapshot.statio_user_indexes_history ALTER COLUMN snapshot_id DROP DEFAULT';
        EXECUTE 'CREATE INDEX idx_siuih_snapshot_id ON stat_snapshot.statio_user_indexes_history (snapshot_id)';
        EXECUTE 'CREATE INDEX idx_siuih_indexrelid ON stat_snapshot.statio_user_indexes_history (indexrelid)';
    END IF;
END $$;

-- 采集库级视图时，对应的 snapshots 元数据行示例：
-- INSERT INTO stat_snapshot.snapshots (snapshot_level, database_name, source_reset_time)
-- VALUES ('database', current_database(),
--         (SELECT stats_reset FROM pg_stat_database WHERE datname = current_database()))
-- RETURNING snapshot_id;
