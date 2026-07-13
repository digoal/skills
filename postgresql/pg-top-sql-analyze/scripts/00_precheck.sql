-- ============================================================
-- pg-top-sql-analyze / Step 0: 前置条件检查
-- 用法：psql -h <host> -p <port> -U <user> -d <dbname> -f 00_precheck.sql
-- ============================================================

-- 1. 检查 pg_stat_statements 扩展是否已安装
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'pg_stat_statements';
-- 若无返回行 -> 扩展未安装，需终止并提示安装步骤

-- 2. 检查 track 参数设置
SHOW pg_stat_statements.track;
-- 期望值：all；若为 top 或 none，非 SELECT 语句可能采集不到，需警告

-- 3. 检查 PostgreSQL 主版本号（决定是否有 total_plan_time 字段）
SHOW server_version_num;
-- >= 130000 才有 total_plan_time / mean_plan_time 等字段

-- 4. 检查 pg_stat_statements.max（采样容量，容量太小会导致高频新查询挤出老查询）
SHOW pg_stat_statements.max;

-- 5. 检查当前用户是否具备 reset 权限（仅重置模式需要，供参考，不代表一定失败）
SELECT rolsuper OR rolreplication AS likely_can_reset
FROM pg_roles
WHERE rolname = current_user;
