-- ============================================================
-- pg-bloat-root-cause 参考查询集
-- 所有查询均为只读操作，仅访问 pg_catalog / information_schema / pg_stat_* 视图
-- ============================================================


-- ============================================================
-- [ENV] 阶段一：环境信息采集
-- ============================================================

-- [ENV-1] 版本及编译信息
SELECT version();

-- [ENV-2] 实例角色：主库(false) / 备库(true)
SELECT pg_is_in_recovery() AS is_standby;

-- [ENV-3] 数据库列表及大小
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS size_pretty,
    pg_database_size(datname) AS size_bytes
FROM pg_database
WHERE datistemplate = false
ORDER BY pg_database_size(datname) DESC;

-- [ENV-4] autovacuum 相关参数
SELECT name, setting, unit, context
FROM pg_settings
WHERE name IN (
    'autovacuum',
    'autovacuum_vacuum_scale_factor',
    'autovacuum_vacuum_threshold',
    'autovacuum_vacuum_cost_delay',
    'autovacuum_vacuum_cost_limit',
    'autovacuum_naptime',
    'autovacuum_max_workers',
    'vacuum_defer_cleanup_age',
    'idle_in_transaction_session_timeout',
    'hot_standby_feedback'
)
ORDER BY name;


-- ============================================================
-- [CAUSE-1] 长事务检测
-- ============================================================

-- 非 idle 状态且事务时长 > 5 分钟，或 idle in transaction 且时长 > 30 分钟
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    backend_start,
    xact_start,
    left(query, 200) AS query_snippet,
    round(extract(epoch FROM (now() - xact_start)) / 60.0, 1) AS duration_minutes
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
  AND (
        (state <> 'idle' AND now() - xact_start > interval '5 minutes')
     OR (state = 'idle in transaction' AND now() - xact_start > interval '30 minutes')
      )
ORDER BY xact_start ASC;


-- ============================================================
-- [CAUSE-2] 未结束的 2PC (prepared transaction) 检测
-- 需要能访问 pg_prepared_xacts（一般无特殊权限要求，但事务详情受限于角色）
-- ============================================================

SELECT
    transaction,
    gid,
    prepared,
    owner,
    database,
    round(extract(epoch FROM (now() - prepared)) / 60.0, 1) AS prepared_minutes
FROM pg_prepared_xacts
ORDER BY prepared ASC;

-- 严重程度判定（应用层逻辑）：prepared_minutes > 15 → Critical


-- ============================================================
-- [CAUSE-3] 长时间运行的查询检测
-- ============================================================

SELECT
    pid,
    usename,
    query_start,
    left(query, 200) AS query_snippet,
    round(extract(epoch FROM (now() - query_start)) / 60.0, 1) AS duration_minutes
FROM pg_stat_activity
WHERE state = 'active'
  AND query_start IS NOT NULL
  AND now() - query_start > interval '10 minutes'
ORDER BY query_start ASC;


-- ============================================================
-- [CAUSE-4] 复制槽延迟检测（主库上执行）
-- ============================================================

SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_current_wal_lsn() AS current_wal_lsn,
    round(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) / 1024.0 / 1024.0,
        2
    ) AS lag_mb
FROM pg_replication_slots
ORDER BY lag_mb DESC NULLS LAST;

-- 严重程度判定：active = false → Critical（不再被消费但持续保留资源）


-- ============================================================
-- [CAUSE-5] 备库反馈机制检测（在备库连接上执行）
-- ============================================================

-- 5a. 备库 hot_standby_feedback 当前值
SELECT name, setting FROM pg_settings WHERE name = 'hot_standby_feedback';

-- 5b. 备库长事务 / 长查询（运行时长 > 5 分钟）
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    query_start,
    left(query, 200) AS query_snippet,
    round(
        extract(epoch FROM (now() - COALESCE(xact_start, query_start))) / 60.0,
        1
    ) AS duration_minutes
FROM pg_stat_activity
WHERE COALESCE(xact_start, query_start) IS NOT NULL
  AND now() - COALESCE(xact_start, query_start) > interval '5 minutes'
ORDER BY duration_minutes DESC;

-- 因果判定（应用层逻辑）：
-- 若 5a 结果为 on 且 5b 存在长事务/长查询 → 判定为「备库反馈导致主库膨胀」


-- ============================================================
-- [CAUSE-6] 孤儿准备事务与失效逻辑复制槽补充检查
-- ============================================================

-- 6a. gid 中包含逻辑复制相关关键字的 2PC 事务（可能是复制初始化残留）
SELECT transaction, gid, prepared, owner, database
FROM pg_prepared_xacts
WHERE gid ILIKE '%logical%' OR gid ILIKE '%replication%' OR gid ILIKE '%slot%';

-- 6b. 未激活的逻辑复制槽
SELECT slot_name, slot_type, active, restart_lsn, confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical' AND active = false;


-- ============================================================
-- [BLOAT] 阶段三：实际膨胀数据采集（精确法，需 pgstattuple）
-- ============================================================

-- 检查 pgstattuple 是否已安装
SELECT extname FROM pg_extension WHERE extname = 'pgstattuple';

-- 若已安装，可用如下方式对单表进行精确膨胀评估（需逐库逐表调用，注意大表可能产生较高 IO）：
-- SELECT * FROM pgstattuple('schema.table_name');
-- 索引：SELECT * FROM pgstattuple('schema.index_name');

-- 每个数据库中候选膨胀表初筛（结合 pg_stat_user_tables 的死元组占比，优先对占比高的表再用 pgstattuple 精确核实）
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2
    ) AS dead_tuple_pct,
    last_autovacuum,
    last_autoanalyze,
    autovacuum_count,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY dead_tuple_pct DESC NULLS LAST
LIMIT 100;
