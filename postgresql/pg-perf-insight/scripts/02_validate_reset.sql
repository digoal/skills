-- 02_validate_reset.sql
-- 目的：验证 snap_begin / snap_end 的 source_reset_time 是否一致
-- 前置：已从 01_find_snapshot_pair.sql 得到 SNAP_BEGIN_ID 和 SNAP_END_ID
-- 占位符：{schema}；执行前请把 :snap_begin_id / :snap_end_id 替换为实际快照ID
-- （或用 psql -v snap_begin_id=... -v snap_end_id=... 传参）

-- 一致性校验
SELECT
  b.snapshot_id   AS begin_snapshot_id,
  b.snapshot_time AS begin_snapshot_time,
  b.source_reset_time AS begin_reset_time,
  e.snapshot_id   AS end_snapshot_id,
  e.snapshot_time AS end_snapshot_time,
  e.source_reset_time AS end_reset_time,
  (b.source_reset_time = e.source_reset_time) AS is_valid_pair
FROM {schema}.snapshots b, {schema}.snapshots e
WHERE b.snapshot_id = :snap_begin_id
  AND e.snapshot_id = :snap_end_id;

-- 若 is_valid_pair = false，执行下面的查询定位 reset 发生的精确时间点，
-- 从而给用户推荐可用的替代分析窗口。
SELECT
  snapshot_id,
  snapshot_time,
  source_reset_time,
  LAG(source_reset_time) OVER (ORDER BY snapshot_time) AS prev_reset_time,
  (source_reset_time <> LAG(source_reset_time) OVER (ORDER BY snapshot_time)) AS reset_happened
FROM {schema}.snapshots
WHERE snapshot_time BETWEEN
  (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_begin_id)
  AND
  (SELECT snapshot_time FROM {schema}.snapshots WHERE snapshot_id = :snap_end_id)
ORDER BY snapshot_time;
-- reset_happened = true 的那一行的 snapshot_time 即为 reset 发生的时间点，
-- 建议将分析窗口调整为该时间点之前或之后。
