-- 01_find_snapshot_pair.sql
-- 目的：找出覆盖用户指定分析时间段 [{start_time}, {end_time}] 的最佳快照对
-- 占位符：{schema} {start_time} {end_time}

-- 快照范围总览（用于"找不到快照对"时的提示）
SELECT
  MIN(snapshot_time) AS earliest_snapshot,
  MAX(snapshot_time) AS latest_snapshot,
  COUNT(*)           AS total_snapshots
FROM {schema}.snapshots;

-- snap_begin：<= start_time 中最大的一条
SELECT snapshot_id, snapshot_time, source_reset_time
FROM {schema}.snapshots
WHERE snapshot_time <= '{start_time}'::timestamptz
ORDER BY snapshot_time DESC
LIMIT 1;

-- snap_end：>= end_time 中最小的一条
SELECT snapshot_id, snapshot_time, source_reset_time
FROM {schema}.snapshots
WHERE snapshot_time >= '{end_time}'::timestamptz
ORDER BY snapshot_time ASC
LIMIT 1;

-- 若上面两条查询任一为空，按 SKILL.md 中的固定话术告知用户，并使用
-- earliest_snapshot / latest_snapshot 填充提示内容，然后终止分析。
