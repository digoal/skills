-- pg-runtime-risk / references/manual_checks.sql
-- 本文件中的查询/命令分为两类：
--   (A) 只读辅助查询 —— 可直接执行，用于补充第七部分单点故障分析
--       以及第六部分连接数耗尽的按角色排查
--   (B) 破坏性操作模板 —— 仅作为"建议命令"呈现给用户，
--       Agent 不得自动执行，必须等待用户明确二次确认后才可运行

-- =========================================================
-- (A) 只读辅助查询
-- =========================================================

-- A1. 同步备库数量与状态（用于判断"同步备库缺失"风险）
SELECT count(*) FILTER (WHERE sync_state = 'sync') AS sync_standby_count,
       count(*) AS total_standby_count
FROM pg_stat_replication;

-- A2. synchronous_standby_names 配置内容（为空表示未配置任何同步备库）
SELECT setting FROM pg_settings WHERE name = 'synchronous_standby_names';

-- A3. synchronous_commit 取值（off/local 时即使有同步备库也不保证同步）
SELECT setting FROM pg_settings WHERE name = 'synchronous_commit';

-- A4. 检测 serial/smallserial 语义的序列（对应列 data_type 为 integer/smallint）
--     与 02_sequence_risk.csv 中的 data_type 字段结合使用，
--     若剩余调用次数已进入警告及以上，建议改为 bigserial。
SELECT n.nspname, c.relname AS seq_name, format_type(s.seqtypid, null) AS data_type
FROM pg_sequence s
JOIN pg_class c ON s.seqrelid = c.oid
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE format_type(s.seqtypid, null) IN ('integer','smallint');

-- =========================================================
-- (B) 破坏性操作模板 —— 严禁自动执行，仅供用户手动确认后使用
-- =========================================================

-- B1. 清理未激活的复制槽（会立即释放该槽保留的 WAL，若消费者尚未消费完毕会导致数据丢失）
-- SELECT pg_drop_replication_slot('要删除的槽名');

-- B2. 清理疑似孤立的大对象（执行前必须先通过 08_lo_reference_columns.csv
--     人工核对该 OID 是否仍被某张表的 oid/lo 列引用，或被应用层文件路径引用）
-- SELECT lo_unlink(loid) FROM pg_largeobject_metadata WHERE loid NOT IN (/* 人工确认的在用 OID 列表 */);

-- B3. 手动触发 vacuum freeze（当数据库年龄已进入警告/严重区间，
--     且 autovacuum 未能及时处理时使用；会产生较大 IO，建议在业务低峰期执行）
-- VACUUM (FREEZE, VERBOSE, ANALYZE) <table_name>;

-- B4. 调整 autovacuum_freeze_max_age，使 freeze 更均匀分摊（示例：从默认调低到 10 亿）
-- ALTER SYSTEM SET autovacuum_freeze_max_age = 1000000000;
-- SELECT pg_reload_conf();

-- B5. 终止长时间 idle in transaction 的连接（释放连接数、解除对 autovacuum 推进的阻塞）
--     执行前必须与用户确认具体 pid（来自 06_long_idle_in_transaction.csv），
--     且需告知：该连接若持有未提交事务，终止后事务会回滚，业务侧可能感知为连接异常断开。
-- SELECT pg_terminate_backend(<pid>);
