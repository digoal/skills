-- ============================================================
-- pg-stat-snapshot / references / cleanup.sql
-- 历史数据清理：按时间保留 / 按快照数量保留，二选一或组合使用。
-- ============================================================

-- ------------------------------------------------------------
-- 1. 按时间清理：删除 retention_days 天之前的所有快照数据
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE stat_snapshot.cleanup_snapshots(retention_days integer DEFAULT 7)
LANGUAGE plpgsql AS $$
DECLARE
    cutoff_time timestamptz := now() - (retention_days || ' days')::interval;
    rec         record;
    del_count   bigint;
BEGIN
    FOR rec IN
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'stat_snapshot'
          AND table_name LIKE '%_history'
    LOOP
        EXECUTE format(
            'DELETE FROM stat_snapshot.%I WHERE snapshot_time < $1',
            rec.table_name
        ) USING cutoff_time;
        GET DIAGNOSTICS del_count = ROW_COUNT;
        RAISE NOTICE '表 % 删除 % 行（截止时间 %）', rec.table_name, del_count, cutoff_time;
    END LOOP;

    DELETE FROM stat_snapshot.snapshots WHERE snapshot_time < cutoff_time;
    GET DIAGNOSTICS del_count = ROW_COUNT;
    RAISE NOTICE '快照清理完成，删除元数据 % 条，截止时间 %', del_count, cutoff_time;

    COMMIT;
END;
$$;

-- ------------------------------------------------------------
-- 2. 按快照数量保留：保留最近 retain_count 个快照，删除更早的
--    以"第 retain_count 个最新快照的 snapshot_time"为界，按时间批量删除，
--    避免按 snapshot_id 硬删导致跨库/跨 level 的快照被误删。
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE stat_snapshot.cleanup_by_count(retain_count integer DEFAULT 100)
LANGUAGE plpgsql AS $$
DECLARE
    cutoff_time timestamptz;
    rec         record;
    del_count   bigint;
BEGIN
    SELECT snapshot_time INTO cutoff_time
    FROM (
        SELECT snapshot_time
        FROM stat_snapshot.snapshots
        ORDER BY snapshot_time DESC
        OFFSET retain_count LIMIT 1
    ) t;

    IF cutoff_time IS NULL THEN
        RAISE NOTICE '当前快照总数未超过 %，无需清理', retain_count;
        RETURN;
    END IF;

    FOR rec IN
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'stat_snapshot'
          AND table_name LIKE '%_history'
    LOOP
        EXECUTE format(
            'DELETE FROM stat_snapshot.%I WHERE snapshot_time < $1',
            rec.table_name
        ) USING cutoff_time;
        GET DIAGNOSTICS del_count = ROW_COUNT;
        RAISE NOTICE '表 % 删除 % 行（截止时间 %）', rec.table_name, del_count, cutoff_time;
    END LOOP;

    DELETE FROM stat_snapshot.snapshots WHERE snapshot_time < cutoff_time;
    GET DIAGNOSTICS del_count = ROW_COUNT;
    RAISE NOTICE '按数量清理完成，保留最近 % 个快照，删除元数据 % 条', retain_count, del_count;

    COMMIT;
END;
$$;

-- ------------------------------------------------------------
-- 3. pg_cron 定时任务示例（若实例已安装 pg_cron 扩展）
-- ------------------------------------------------------------
-- 每天凌晨 3 点清理 7 天前的数据
-- SELECT cron.schedule('pg-stat-snapshot-cleanup-time', '0 3 * * *',
--     $$CALL stat_snapshot.cleanup_snapshots(7)$$);

-- 或者每天凌晨 3 点按数量保留最近 200 个快照
-- SELECT cron.schedule('pg-stat-snapshot-cleanup-count', '0 3 * * *',
--     $$CALL stat_snapshot.cleanup_by_count(200)$$);

-- ------------------------------------------------------------
-- 4. 操作系统 crontab 方式示例（无 pg_cron 时的替代方案）
--    需提前配置 .pgpass 或环境变量 PGPASSWORD 免密，避免在 crontab 中明文写密码。
-- ------------------------------------------------------------
-- 0 3 * * * PGPASSWORD="$(cat /etc/pg-stat-snapshot.pgpass)" psql "host=<HOST> port=<PORT> user=<USER> dbname=postgres" -c "CALL stat_snapshot.cleanup_snapshots(7);" >> /var/log/pg-stat-snapshot-cleanup.log 2>&1
