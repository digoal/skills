---
name: pg-perf-insight
description: "基于 pg-stat-snapshot 采集的历史快照，为指定时间段生成 AWS Performance Insights 风格的 PostgreSQL 深度性能诊断报告。触发场景：用户给出实例连接信息（host/port/user/密码）+ 快照 schema + 分析时间段，并要求'性能诊断'、'性能分析报告'、'AAS 分析'、'Top SQL 分析'、'等待事件分析'、'数据库负载分析'、'为什么这段时间数据库很慢'、'定位性能瓶颈'、'类似 AWS PI 的报告'。即使用户只说'帮我分析一下昨晚 2-3 点数据库为什么慢'并提供了连接信息，也应触发本技能。"
tags: [PostgreSQL, 性能洞察, performance insight, 快照分析]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# pg-perf-insight：PostgreSQL 性能诊断报告生成器

给定实例连接信息、快照 schema、分析时间段，从历史快照中定位最佳快照对，计算差值指标，产出一份 AWS Performance Insights 风格的中文深度性能报告（AAS、Top SQL、等待事件推断、按库/用户拆解、根因分析、优化优先级）。

本技能**依赖**已通过 `pg-stat-snapshot` 技能（或同构的快照采集机制）持续采集的历史快照数据，自身不采集快照、不修改任何数据。

## 前置要求

- 已安装 `psql` 客户端（`which psql` 确认）。
- 目标实例已存在快照 schema（默认 `stat_snapshot`），且包含至少两条覆盖分析时间段的快照记录。
- 连接凭据只能通过环境变量 `PGPASSWORD` 传递，**禁止**在命令行参数、日志或报告中明文出现密码。
- 首次执行前用 `\d {schema}.*` 确认实际表结构；下文 SQL 假设的表名/字段名如与实际不符，需据实调整（见"表结构假设"一节）。

## 输入参数（向用户确认或从对话中提取）

| 参数 | 说明 | 默认值 |
|---|---|---|
| host / port / user / dbname | 连接信息 | 无，必需 |
| PGPASSWORD | 密码，仅通过环境变量传入 | 无，必需 |
| schema | 快照所在 schema | `stat_snapshot` |
| start_time / end_time | 用户指定的分析时间段 | 无，必需 |
| vcpu 数量 | 用于计算 CPU 利用率，若未提供则从 `pg_settings_snapshot` 中查 `guc` 或提示用户提供 | 自动探测/询问 |

## 表结构假设（与 pg-stat-snapshot 对齐）

- `{schema}.snapshots(snapshot_id, snapshot_time, source_reset_time)`
- `{schema}.pg_stat_statements_snapshot(snapshot_id, dbid, userid, queryid, query, calls, total_exec_time, rows, shared_blks_hit, shared_blks_read, blk_read_time, blk_write_time, wal_bytes)`
- `{schema}.pg_stat_activity_snapshot(snapshot_id, pid, usename, application_name, datname, state, wait_event_type, wait_event, query_start)`
- `{schema}.pg_stat_database_snapshot(snapshot_id, datid, datname, xact_commit, xact_rollback, blks_read, blks_hit)`
- `{schema}.pg_settings_snapshot(snapshot_id, name, setting)`

若实际列缺失（如 `wal_bytes` 在 PG13 以下不存在，`blk_read_time` 依赖 `track_io_timing=on`），对应分析项在报告中标注「当前版本/配置不支持该指标，跳过」，不要臆造数值。

## 工作流程

### Step 1：只读会话建立

所有查询必须在只读事务中执行，使用 `scripts/run_analysis.sh` 统一封装：

```bash
PGPASSWORD="$PW" psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DBNAME" -v ON_ERROR_STOP=1 <<'SQL'
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
-- 具体查询
SQL
```

不使用超级用户专属操作，不执行任何 INSERT/UPDATE/DELETE/DDL。

### Step 2：定位最佳快照对

执行 `scripts/01_find_snapshot_pair.sql`（需替换 `{schema}`、`{start_time}`、`{end_time}`），得到：

- `snap_begin`：`snapshot_time <= start_time` 中最大的一条
- `snap_end`：`snapshot_time >= end_time` 中最小的一条

若查不到满足条件的快照对，按此格式告知用户并终止：

> 指定时间段内没有足够的快照数据。快照范围是 [最早快照时间] 到 [最晚快照时间]，请调整分析时间段。

找到后，向用户报告实际使用的窗口 `[snap_begin.snapshot_time, snap_end.snapshot_time]`。

### Step 3：快照有效性验证

执行 `scripts/02_validate_reset.sql`，比对两条快照的 `source_reset_time`：

- **不一致** → 说明窗口内发生过 `pg_stat_statements_reset()` 或实例重启，累计计数器差值无效。用如下格式提示，并终止分析，不得继续计算差值：

  > 快照 #X（时间 A）和快照 #Y（时间 B）的统计计数器重置时间不同（分别为 T1 和 T2），说明在分析窗口内发生过统计重置，累计计数器差值无效。

  再执行该脚本中的第二段查询，定位 reset 发生的精确时间点，给出可用的备选时间段建议。

- **一致** → 继续 Step 4。

### Step 4：窗口长度检查

计算 `window_seconds = snap_end.snapshot_time - snap_begin.snapshot_time`：

- `< 60s`：提示"分析窗口过短，统计样本可能不足，建议扩大时间范围"。
- `> 24h`：提示"分析窗口较长，汇总数据可能掩盖瞬时尖峰，建议缩短至 1-6 小时"。
- 两种情况均**继续**分析，只是在报告开头附加提示，不中断流程。

### Step 5：核心差值计算

依次执行 `scripts/03_aas_overview.sql`、`scripts/04_top_sql_multi_dim.sql`、`scripts/05_wait_event_inference.sql`、`scripts/06_by_database.sql`、`scripts/07_by_user_app.sql`，全部基于 `snap_begin.snapshot_id` 与 `snap_end.snapshot_id` 在 SQL 内部做差值（`snap_end.x - snap_begin.x`），**不要**把两份原始快照拉到外部再用程序语言相减。

关键指标口径：

- `AAS = SUM(delta_total_exec_time) / window_seconds / 1000`
- CPU 占比：`delta_total_exec_time` 占比作为 CPU 消耗近似
- 缓存命中率：`delta_shared_blks_hit / NULLIF(delta_shared_blks_hit + delta_shared_blks_read, 0)`
- 每个维度（总耗时/调用频率/平均延迟/IO/WAL/行数）各取 TOP 10

### Step 6：瓶颈根因诊断（推理，非 SQL）

对每个维度 TOP 3 的 SQL，结合以下模式判断根因（参考 `references/root_cause_patterns.md`）：

- WHERE 有过滤条件但 `shared_blks_read` 很高 → 疑似索引缺失
- WHERE 条件含函数包裹字段/隐式类型转换 → 疑似索引失效
- `rows` 很大但 `calls` 不高 → 分析型大查询
- `calls` 很高但单次延迟很低 → 高频小查询（ORM N+1 / 缓存未命中）
- 高频 UPDATE/DELETE + `pg_stat_activity_snapshot` 中 `wait_event_type='Lock'` 频次高 → 锁竞争

资源瓶颈判断：

- CPU 瓶颈：AAS 接近或超过 vCPU 数，且 Top SQL 以低 IO/低 WAL 为主
- IO 瓶颈：`shared_blks_read` 占比高、缓存命中率低
- 内存瓶颈：缓存命中率持续偏低
- 连接数瓶颈：`pg_stat_activity_snapshot` 中活跃连接数接近 `max_connections`
- WAL 瓶颈：`delta_wal_bytes` 异常高

异常检测：执行 `scripts/08_anomaly_detection.sql`，检测相邻快照间 AAS 突增、同一 `queryid` 平均延迟翻倍、`snap_end` 中新增的 `queryid`。

### Step 7：生成报告

使用 `references/report_template.md` 的结构生成完整中文报告，章节顺序：性能总览仪表盘 → 按维度 Top SQL（4 张表）→ 等待事件分布 → 按数据库拆解 → 按用户/应用拆解 → 关键发现与根因分析 → 负载趋势与异常检测 → 优化优先级 Top 5 → 后续监控建议。

## 执行约束

- 所有分析仅对 `{schema}` 下的历史快照表做只读查询，不访问生产表，不执行任何写操作。
- 差值计算必须在 SQL 内完成。
- PG 版本不支持的指标（如 `wal_bytes`）在报告中明确标注"跳过"，禁止编造数值。
- 若 `pg_stat_activity_snapshot` 只采集了非空闲连接，报告中需注明"活跃连接数可能偏低，仅统计非空闲连接"。
- SQL 文本截取前 200 字符展示，但完整 `queryid` 必须保留供用户自行查询。
- 报告使用中文输出。
- 密码只通过 `PGPASSWORD` 环境变量传递，禁止回显、禁止写入报告或日志文件。

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|---|---|
| 快照对 reset_time 不一致却硬算差值 | Step 3 必须先验证，不一致立即终止并给出替代窗口建议 |
| `wal_bytes` 在 PG13 以下不存在导致报错 | 先查 `server_version_num`，`< 130000` 时跳过该维度并标注 |
| `blk_read_time` 全为 0 | 检查 `track_io_timing`，关闭时说明该指标不可用，改用 `shared_blks_read` 做 IO 压力近似 |
| 快照窗口内数据库重启，`pg_stat_statements` 计数器清零但被误判为"低负载" | 依赖 Step 3 的 reset 校验而非单纯看数值大小 |
| 多库实例遗漏跨库聚合 | Step 5 的 by_database 脚本按 `datname` 分组，不要只看当前连接的库 |
| 密码明文出现在 shell 历史或报告中 | 一律通过 `PGPASSWORD` 环境变量注入，禁止 `-W` 交互式外的任何明文传递方式 |

## 注意事项

- 本技能不采集快照、不做任何 DDL/DML，纯只读分析。
- 若目标库为多机（主备/只读实例），确认连接的是采集快照的那台实例，避免跨实例对比。
- 报告中的"建议"仅供参考，涉及生产变更（建索引、改写 SQL）前需在业务低峰期验证并保留回滚方案（如 `DROP INDEX CONCURRENTLY` 撤销新建索引）。
- 分析窗口跨越大促/业务高峰与平峰时，聚合指标会被平均掉，应提示用户按更细粒度窗口复查。
