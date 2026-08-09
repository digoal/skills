-- ============================================================
-- kingbase-top-sql-analyze / Step 0: 前置条件检查
-- 适用：KingbaseES（金仓）V9R1C10，PG 兼容模式
-- 用法：psql "host=<host> port=<port> user=<user> dbname=<db>" -f 00_precheck.sql
-- 也可用 ksql（金仓自带客户端）执行，语法与 psql 兼容。
-- ============================================================

-- 1. 检查 sys_stat_statements 扩展是否已安装（注意：不是 pg_stat_statements）
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'sys_stat_statements';
-- 若无返回行 -> 扩展未安装，需终止并提示安装步骤

-- 2. 检查 track 参数设置（金仓默认 top，非顶层语句可能采集不到）
SHOW sys_stat_statements.track;
-- 期望值：all；若为 top 或 none，函数/存储过程内部语句可能采集不到，需警告

-- 3. 检查 track_parse / track_plan / track_utility（金仓特有，决定解析/规划/工具语句是否统计）
SHOW sys_stat_statements.track_parse;
SHOW sys_stat_statements.track_plan;
SHOW sys_stat_statements.track_utility;

-- 4. 检查 KingbaseES 版本（仅用于报告标注；字段可用性请以第 6 步探测为准，
--    不要按 server_version_num 判断字段：R1C10 为 120001，但 sys_stat_statements 采用 PG14+ 字段集）
SHOW server_version_num;

-- 5. 检查 sys_stat_statements.max（采样容量，容量太小会导致高频新查询挤出老查询）
SHOW sys_stat_statements.max;

-- 6. 动态探测 sys_stat_statements 可用列（决定哪些分析维度可用）
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'sys_stat_statements'
ORDER BY ordinal_position;

-- 7. 检查 track_io_timing（blk_read_time / blk_write_time 是否为 0）
SHOW track_io_timing;

-- 8. 检查当前用户是否具备 reset 权限（仅重置模式需要，供参考，不代表一定成功）
SELECT rolsuper OR rolreplication AS likely_can_reset
FROM pg_roles
WHERE rolname = current_user;
