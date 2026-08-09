-- ============================================================
-- kingbase-bloat-root-cause 参考查询集
-- 所有查询均为只读操作，仅访问 pg_catalog / information_schema /
-- pg_stat_* 视图；如确需 sys_recovery / sys_squeeze 的只读视图，
-- 也仅 SELECT，不调用任何会改写表/锁表的函数。
-- KingbaseES 默认采用 PG 12 兼容模式，与 PostgreSQL 共享相同的
-- pg_stat_activity / pg_prepared_xacts / pg_replication_slots / pg_stat_user_tables
-- 等视图。
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

-- [ENV-5] KingbaseES 特有：在线压缩前置 GUC（sys_squeeze 需要）
SELECT name, setting, unit
FROM pg_settings
WHERE name IN (
    'wal_level',                        -- sys_squeeze 需要 logical
    'max_replication_slots',            -- sys_squeeze 需要 ≥1
    'shared_preload_libraries',         -- 确认 sys_squeeze / sys_recovery / sys_repack 是否预加载
    'sys_kwr.enable'                    -- 与本诊断无关，但列出以备交叉参考
)
ORDER BY name;

-- [ENV-6] 可用于诊断的 KingbaseES 扩展是否安装
SELECT extname, extversion
FROM pg_extension
WHERE extname IN (
    'sys_squeeze',    -- 在线压缩（占用 logical slot）
    'sys_recovery',   -- 死元组详情读取
    'sys_spacequota', -- 表空间配额（侧面反映磁盘增长）
    'sys_repack',     -- 命令行在线重写（作为扩展时不常见）
    'pgstattuple'     -- 标准 PG 精确膨胀扩展，KingbaseES 默认无
)
ORDER BY extname;


-- ============================================================
-- [CAUSE-1] 长事务检测
-- ============================================================

-- 非 idle 状态且事务时长 > 5 分钟，或 idle in transaction 且时长 > 30 分钟
-- 注意：KingbaseES 的 round() 没有 (double, integer) 重载，需显式 cast 为 numeric
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    backend_start,
    xact_start,
    left(query, 200) AS query_snippet,
    round((extract(epoch FROM (now() - xact_start)) / 60.0)::numeric, 1) AS duration_minutes
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
    round((extract(epoch FROM (now() - prepared)) / 60.0)::numeric, 1) AS prepared_minutes
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
    round((extract(epoch FROM (now() - query_start)) / 60.0)::numeric, 1) AS duration_minutes
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
        (pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) / 1024.0 / 1024.0)::numeric,
        2
    ) AS lag_mb
FROM pg_replication_slots
ORDER BY lag_mb DESC NULLS LAST;

-- 严重程度判定：active = false → Critical（不再被消费但持续保留资源）
-- 注意：KingbaseES 的 sys_squeeze 启用后会在此处出现一个
-- slot_type='logical' 的 squeeze 自身槽位，slot_name 通常包含 "squeeze" 字样，
-- 不要误判为"残留孤儿 logical 槽"，参见 [CAUSE-6]


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
        (extract(epoch FROM (now() - COALESCE(xact_start, query_start))) / 60.0)::numeric,
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
WHERE gid ILIKE '%logical%'
   OR gid ILIKE '%replication%'
   OR gid ILIKE '%slot%'
   OR gid ILIKE '%squeeze%';

-- 6b. 未激活的逻辑复制槽
-- ⚠️ KingbaseES 特有注意：如果已经安装 sys_squeeze 扩展，
-- 该列表会出现一个 slot_type=logical、slot_name 含 squeeze 字样的活动槽位，
-- 不要把 sys_squeeze 自身的工作槽误判为残留；
-- 可结合 SELECT extname FROM pg_extension WHERE extname='sys_squeeze';
-- 来区分"扩展已安装的工作槽" vs "真正的残留孤儿 logical 槽"。
SELECT
    s.slot_name,
    s.slot_type,
    s.active,
    s.restart_lsn,
    s.confirmed_flush_lsn,
    (s.slot_name ILIKE '%squeeze%') AS is_sys_squeeze_slot
FROM pg_replication_slots s
WHERE s.slot_type = 'logical'
  AND (
        s.active = false
     OR s.slot_name ILIKE '%squeeze%'
  )
ORDER BY is_sys_squeeze_slot, s.slot_name;


-- ============================================================
-- [BLOAT] 阶段三：实际膨胀数据采集（基于统计信息估算，KingbaseES 默认方案）
-- ============================================================

-- 检查 KingbaseES 特有扩展是否已安装，决定是否启用精确读法
SELECT
    EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgstattuple')   AS has_pgstattuple,
    EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'sys_recovery')  AS has_sys_recovery,
    EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'sys_squeeze')   AS has_sys_squeeze;

-- 每个数据库中候选膨胀表初筛（结合 pg_stat_user_tables 的死元组占比）
-- 若已安装 sys_recovery，下面的 query_snippet 列可改为
--   (SELECT count(*) FROM sys_recovery(c.oid, false)) 精确读取死元组
-- （sys_recovery 不属于只读 SELECT 副作用，但执行时会对表做 MVCC 扫描，
--  大表请谨慎，可仅对初筛 top 10 名单独调用）。
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        (100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0))::numeric, 2
    ) AS dead_tuple_pct,
    last_autovacuum,
    last_autoanalyze,
    autovacuum_count,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY dead_tuple_pct DESC NULLS LAST
LIMIT 100;