-- ============================================================
-- pg-stat-snapshot / references / ddl_optional.sql
-- 可选扩展视图：根据实例版本和实际存在情况按需建表。
-- 命名规则：stat_snapshot.<视图名去掉 pg_ 前缀>_history
-- 使用前先探测视图是否存在，避免在低版本实例上报错：
--   SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_views WHERE viewname = 'pg_stat_wal');
-- ============================================================

-- ------------------------------------------------------------
-- 1. pg_stat_wal（PG 14+，WAL 写入统计，实例级，只有一行，适合做时间序列而非差值 JOIN）
-- ------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_views WHERE viewname = 'pg_stat_wal')
       AND NOT EXISTS (
           SELECT 1 FROM information_schema.tables
           WHERE table_schema = 'stat_snapshot' AND table_name = 'stat_wal_history'
       ) THEN
        EXECUTE '
            CREATE TABLE stat_snapshot.stat_wal_history AS
            SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, w.*
            FROM pg_stat_wal w
            LIMIT 0
        ';
        EXECUTE 'ALTER TABLE stat_snapshot.stat_wal_history ALTER COLUMN snapshot_id DROP DEFAULT';
        EXECUTE 'CREATE INDEX idx_swh_snapshot_id ON stat_snapshot.stat_wal_history (snapshot_id)';
    END IF;
END $$;

-- ------------------------------------------------------------
-- 2. pg_stat_replication（主库复制状态，仅主库有数据，实例级）
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'stat_snapshot' AND table_name = 'stat_replication_history'
    ) THEN
        EXECUTE '
            CREATE TABLE stat_snapshot.stat_replication_history AS
            SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, r.*
            FROM pg_stat_replication r
            LIMIT 0
        ';
        EXECUTE 'ALTER TABLE stat_snapshot.stat_replication_history ALTER COLUMN snapshot_id DROP DEFAULT';
        EXECUTE 'CREATE INDEX idx_srh_snapshot_id ON stat_snapshot.stat_replication_history (snapshot_id)';
    END IF;
END $$;
-- 备库上该视图恒为空，采集 0 行属于正常现象，不算失败，报告中注明"当前非主库或无从库连接"。

-- ------------------------------------------------------------
-- 3. pg_stat_database（库级事务/IO 汇总，实例级视图但含各库一行，建议放在实例级历史表）
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'stat_snapshot' AND table_name = 'stat_database_history'
    ) THEN
        EXECUTE '
            CREATE TABLE stat_snapshot.stat_database_history AS
            SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, d.*
            FROM pg_stat_database d
            LIMIT 0
        ';
        EXECUTE 'ALTER TABLE stat_snapshot.stat_database_history ALTER COLUMN snapshot_id DROP DEFAULT';
        EXECUTE 'CREATE INDEX idx_sdh_snapshot_id ON stat_snapshot.stat_database_history (snapshot_id)';
        EXECUTE 'CREATE INDEX idx_sdh_datname ON stat_snapshot.stat_database_history (datname)';
    END IF;
END $$;

-- ------------------------------------------------------------
-- 4. pg_stat_bgwriter（后台写入与检查点统计，实例级，只有一行）
--    PG 17+ 该视图被拆分为 pg_stat_bgwriter + pg_stat_checkpointer，
--    采集前需探测 pg_stat_checkpointer 是否存在，存在则一并建表采集。
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'stat_snapshot' AND table_name = 'stat_bgwriter_history'
    ) THEN
        EXECUTE '
            CREATE TABLE stat_snapshot.stat_bgwriter_history AS
            SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, b.*
            FROM pg_stat_bgwriter b
            LIMIT 0
        ';
        EXECUTE 'ALTER TABLE stat_snapshot.stat_bgwriter_history ALTER COLUMN snapshot_id DROP DEFAULT';
        EXECUTE 'CREATE INDEX idx_sbh_snapshot_id ON stat_snapshot.stat_bgwriter_history (snapshot_id)';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_catalog.pg_views WHERE viewname = 'pg_stat_checkpointer')
       AND NOT EXISTS (
           SELECT 1 FROM information_schema.tables
           WHERE table_schema = 'stat_snapshot' AND table_name = 'stat_checkpointer_history'
       ) THEN
        EXECUTE '
            CREATE TABLE stat_snapshot.stat_checkpointer_history AS
            SELECT 0::bigint AS snapshot_id, now() AS snapshot_time, c.*
            FROM pg_stat_checkpointer c
            LIMIT 0
        ';
        EXECUTE 'ALTER TABLE stat_snapshot.stat_checkpointer_history ALTER COLUMN snapshot_id DROP DEFAULT';
        EXECUTE 'CREATE INDEX idx_sch_snapshot_id ON stat_snapshot.stat_checkpointer_history (snapshot_id)';
    END IF;
END $$;
