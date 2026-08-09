---
name: kingbase-load-spike-forensics
description: "扮演 KingbaseES（金仓）DBA 专家 + 操作系统专家 + 网络专家 + 存储专家，对给定的一段可疑时间窗口做数据库负载飙升的多维取证分析。KingbaseES 默认采用 PG 兼容模式，因此 pg_stat_activity / pg_stat_database / pg_stat_bgwriter / pg_locks / pg_stat_replication / pg_stat_user_tables 等系统视图与 PostgreSQL 12 高度一致，可直接复用；同时金仓在 sys_catalog 下提供一套独立的 sys_stat_* 动态性能视图（sys_stat_sql / sys_stat_sqltime / sys_stat_sqlio / sys_stat_sqlwait / sys_stat_sqlcount / sys_stat_wait / sys_stat_waitaccum / sys_stat_wal_buffer / sys_stat_dbtime / sys_stat_dmlcount / sys_stat_instevent / sys_stat_instlock / sys_stat_instio / sys_stat_msgaccum）和 AWR 风格的 sys_stat_metric_history / sys_stat_sysmetric / sys_stat_sysmetric_history / sys_stat_sysmetric_summary 自动快照仓库（依赖 sys_kwr 扩展开启），可作为本次窗口取证的核心证据来源。触发条件：用户给出一个时间段并提到'负载飙升'、'CPU飙高'、'load average 很高'、'数据库卡顿'、'突然变慢'、'连接数暴涨'、'慢查询突增'、'IO打满'、'内存暴涨/OOM'、'那段时间发生了什么'、'帮我排查一下这段时间的金仓'、'金仓复盘一次故障'、'故障根因分析'、'金仓 RCA'，或提供了金仓日志/系统日志/连接串并希望定位问题根因。即使用户只说'昨晚2点到3点金仓数据库很慢，帮我查查为什么'或'金仓这段时间是不是出问题了'，也应使用本 skill。本 skill 覆盖金仓数据库日志、统计信息视图、扩展插件（sys_stat_statements / sys_stat_sql 聚合视图 / auto_explain）、操作系统日志与指标（dmesg/journalctl/sar/vmstat）、存储（iostat/df/WAL 增长）、网络（ss/netstat/tcp 重传/复制延迟）六大维度，产出时间线、根因链条、影响面和规避建议。"
tags: [KingbaseES, 金仓, 负载问题, 问题溯源, 性能分析, 异常分析, 抖动分析]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# KingbaseES 负载飙升多维取证分析

给定一个时间窗口，综合金仓数据库日志、统计视图、动态性能视图、操作系统、存储、网络六大维度的证据，重建负载飙升的时间线，溯源根本原因，评估影响面，并给出可落地的规避建议。输出一份可直接用于故障复盘（RCA）的 Markdown 报告。

> **KingbaseES 适配要点**：金仓默认采用 **PG 兼容模式**，`pg_stat_activity` / `pg_stat_database` / `pg_stat_bgwriter` / `pg_locks` / `pg_stat_replication` / `pg_stat_wal_receiver` / `pg_stat_progress_vacuum` / `pg_stat_user_tables` / `pg_stat_user_indexes` 与 PostgreSQL 12 高度一致，可直接复用；同时金仓在 `sys_catalog` 下提供了一套**远超 PG 默认能力**的动态性能视图（见下文 Step 2 的 KB-extra 部分），可在不依赖外部监控系统的情况下回溯历史负载分布。

## 核心原则

1. **先假设"确有其事"，再用证据证伪或证实** — 不要预设结论，时间窗口内也可能是正常业务高峰。每一条结论必须有至少一个维度的原始证据支撑，标注证据来源（文件+行号/视图+采集时间）。
2. **时间对齐是第一优先级** — 数据库日志、OS 日志、监控采集点的时区/时钟可能不一致，必须先确认 `SHOW timezone`、`SHOW log_timezone`、服务器 `timedatectl` 输出，将所有证据换算到同一时区后再建时间线。
3. **区分"症状"与"病因"** — CPU 飙高、连接数暴涨往往是下游症状；锁等待、IO 饱和、autovacuum 风暴、计划变化、连接风暴（thundering herd）才是常见病因。工作流程按"由外到内、由表及里"收窄。
4. **只读取证，不做变更** — 本 skill 只执行只读诊断命令（SELECT、日志 grep、sar/vmstat/iostat 读取），不修改数据库参数、不重启服务、不 kill 进程。如需干预，在报告"规避建议"中给出方案供人工审批执行。
5. **证据链闭环** — 最终报告必须能回答：什么时候开始 → 最先出现异常的维度是什么 → 传导路径是什么 → 影响了哪些库/表/应用 → 什么时候恢复/是否仍在持续 → 下次如何提前发现或避免。
6. **KB 特有的"免费午餐"**：金仓默认运行的 `KshMain` 后台进程是金仓快照助手（Kingbase Snapshot Helper，等价 Oracle MMON），它会按固定 interval 把累计型动态性能视图里的数据写入 `sys_catalog.sys_stat_metric_history` / `sys_stat_sysmetric_history`（AWR 仓库）。**该仓库就是金仓版的"过去某个时间点慢在哪"的金标准证据**，远比事后查 `pg_stat_*` 快照更可靠。如果该仓库为空，意味着 `sys_kwr` 扩展未启用或 interval 间隔尚未触发，应在规避建议里要求开启。

## 前置要求

- **数据库访问**：具备 `sys_monitor`（PG 兼容角色，等价 `pg_monitor`）或 superuser 权限的只读账号，用于查询 `pg_stat_*` 与 `sys_catalog.sys_stat_*` 视图；若时间窗口已过去，PG 视图多为累计值/当前快照，需结合日志与 AWR 历史仓库做时间切片。
- **日志访问权限**：读取 KingbaseES 日志目录（`SHOW log_directory` / `SHOW data_directory`，默认相对 `data_directory` 的 `sys_log/` 子目录）以及操作系统日志（`/var/log/messages`、`journalctl`、`dmesg`）。若金仓部署在容器/K8s 中，改用 `kubectl logs`、`crictl logs` 或容器日志采集平台。
- **金仓默认行为**：
  - `log_destination = stderr`、`logging_collector = on`、`log_filename = kingbase-%Y-%m-%d_%H%M%S.log` —— 按小时切分日志文件（可在 `postgresql.conf` 调整）；
  - `log_min_duration_statement = -1` —— 默认**不记录慢 SQL**，必须显式打开才能在日志里看到慢查询（这是金仓默认比 PG 更保守的一处）；
  - `sys_stat_statements` 扩展默认开启（`v1.11`），等价 `pg_stat_statements`，可直接查询；
  - **KWR 自动快照**默认未开启或 interval 较长，需 DBA 显式配置 `sys_kwr` 扩展。
- **已装/建议安装的扩展**（不存在则在报告中注明"该维度证据缺失"，不要臆造）：
  - `sys_stat_statements`（SQL 级性能画像，几乎必备，等价 `pg_stat_statements`）
  - **KB 强烈推荐**：`sys_stat_sql` / `sys_stat_sqltime` / `sys_stat_sqlio` / `sys_stat_sqlwait` —— 金仓独有的 SQL 聚合视图，把 `pg_stat_statements` + `pg_stat_kcache` + 等待事件三类信息合在一张表里，是金仓取证的核心证据，比 PG 默认视图强大得多。
  - `sys_kwr` + `sys_ksh` —— 金仓 AWR / ASH 等价物，开启后 `sys_stat_metric_history` 等会自动按 interval 落库。
  - `auto_explain`（若开启，日志中会有慢 SQL 的执行计划，是排查计划突变的关键证据）
- **操作系统工具**：`sar`（sysstat 包）、`iostat`、`vmstat`、`ss`、`netstat`、`journalctl`、`dmesg`。KingbaseES 同样常部署在麒麟/CentOS/UOS 等操作系统上，请用对应的包管理工具安装。
- **前提确认**：向用户确认或从上下文中提取——目标时间窗口（含时区）、数据库版本 `SELECT version();`、部署形态（单机/主从/RWC/云托管，云托管上很多 OS 层命令不可执行，需改用云监控 API 或控制台指标）、是否有历史监控系统可查（Prometheus/Grafana/云监控）。

## 连接约定

按优先级解析：

1. 用户明确提供的连接参数（host/port/user/password/dbname）；
2. 环境变量 `PGHOST` `PGPORT` `PGUSER` `PGPASSWORD` `PGDATABASE`（即使 KingbaseES 手册把这些变量写作 `KINGBASE_*`，本 skill **继续沿用 PG 风格**）；
3. 缺省值：`PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGPASSWORD=123456 PGDATABASE=kingbase`。

## 工作流程

### Step 0：锚定时间窗口与环境画像

1. 确认时间窗口起止时间及时区，统一换算为数据库服务器本地时间和 UTC 两套时间戳，后续所有证据都同时标注两套时间避免时区错位。
2. 采集环境画像：
   ```sql
   SELECT version();
   SHOW server_version;
   SHOW data_directory;
   SHOW log_directory;
   SHOW log_filename;
   SHOW timezone;
   SHOW log_timezone;
   SHOW shared_buffers;
   SHOW max_connections;
   SHOW checkpoint_timeout;
   SHOW max_wal_size;
   SHOW autovacuum;
   SHOW track_io_timing;
   -- KB-specific
   SHOW sysaudit.log;     -- 金仓审计日志开关
   SHOW sysmac.log;       -- 金仓 MAC 策略日志开关
   -- 扩展版本
   SELECT extname, extversion FROM pg_extension
     WHERE extname IN ('sys_stat_statements','sys_kwr','sys_ksh','sysaudit','sysmac','sys_hm');
   -- KB 特有的 track_* 开关（控制 sys_stat_sql / sys_stat_instevent 等 KB-extra 视图）
   SELECT name, setting FROM pg_settings
     WHERE name IN ('track_sql','track_instance','track_real_stats','track_wait_timing');
   ```
   > **关键**：金仓在 PG 兼容 `track_*` 之上又增加了一组 `track_sql` / `track_instance` / `track_real_stats` 控制 KB-extra 视图（`sys_stat_sql` 等）的采集。如果这些 GUC 保持默认 `off`，即使 `sys_stat_statements` 有数据，`sys_stat_sql` / `sys_stat_wait` / `sys_stat_sqlwait` 等仍会返回 0 行——这不是脚本问题，需要在规避建议里要求打开。
3. ```bash
   timedatectl
   uname -a
   cat /etc/os-release
   nproc
   free -h
   df -h
   ```
4. 若为主从/RWC（读写分离集群）架构，同时对主库和相关从库分别执行 Step1~Step6，因为负载飙升可能源自任意一侧。
5. 检查金仓独有后台进程是否正常（`ps -ef | grep kingbase` 应能看到 `WalWriter`、`BgWriter`、`Checkpointer`、`AutoVacuum`、`LogicalLauncher` 以及金仓独有的 `KshMain` —— 即快照助手）：
   ```sql
   SELECT pid, application_name, wait_event_type, wait_event, state
   FROM pg_stat_activity WHERE backend_type LIKE '%worker%' OR backend_type LIKE '%launcher%' OR backend_type LIKE '%Main%';
   ```

### Step 1：数据库日志维度

1. 定位窗口内的日志文件（金仓默认按小时切分，命名形如 `kingbase-2026-08-09_020000.log`）：
   ```bash
   # 找出窗口内的日志文件（pg_ctl-style 目录）
   ls -1 ${DATA_DIR}/sys_log/ | awk -v start="2026-08-09 02:00" -v end="2026-08-09 03:00" '
     { fn=$0; gsub(/.*kingbase-|\.log/, "", fn); if (fn >= start && fn <= end) print $0 }'
   ```
   或直接对所有日志按时间戳 grep：
   ```bash
   awk -v start="2026-08-09 02:00:00" -v end="2026-08-09 03:00:00" \
     '$0 >= start && $0 <= end' ${DATA_DIR}/sys_log/kingbase-*.log
   ```
2. 重点关注以下信号（与 PG 基本一致，注意金仓独有的 `sys_*` 相关日志前缀）：
   - `FATAL` / `PANIC` / `could not fork new process` —— 资源耗尽或连接数打满
   - `checkpoint starting` / `checkpoint complete` 且 `... sync=... total=...` 时间显著变长，或出现 `checkpoints are occurring too frequently` —— 检查点风暴
   - `automatic vacuum of table ...` 且耗时/dead tuple 数远超平常，或 `autovacuum: ... to prevent wraparound` —— autovacuum 风暴或事务 ID 回卷紧急清理
   - `duration: ... ms statement:` 超过 `log_min_duration_statement` 的慢查询集中爆发
   - `process ... still waiting for ... lock` / `deadlock detected` —— 锁等待/死锁
   - `temporary file: ... size ...` 集中出现且体积大 —— `work_mem` 不足
   - `unexpected EOF on client connection` / `could not receive data from client` —— 客户端异常断开
   - `out of memory` / `terminating connection because of crash of another server process` —— OOM 或进程异常终止
   - **KB 特有**：`sys_hm` 健康监控告警日志、`sysaudit` 审计日志被截断告警、`KshMain` 写入 AWR 仓库失败的 ERROR 日志
3. 如果开启了 `auto_explain`，提取窗口内被记录的执行计划，比对同一 SQL 在正常时段的计划判断是否发生了计划回归（plan regression）。
4. 将每条证据记录为 `[时间戳] [日志级别] [摘要] [原文片段]`，供后续与其他维度时间线对齐。

### Step 2：数据库统计信息视图维度

> **KingbaseES 适配说明**：金仓有两套并行的统计视图——PG 兼容的 `pg_stat_*` 与金仓独有的 `sys_catalog.sys_stat_*`（后者更强大）。本 step 同时使用两套视图，互相验证；AWR 历史仓库（依赖 `sys_kwr` 扩展）则是窗口已过后的**核心证据来源**，比事后再去查累计视图可靠得多。

#### Step 2.1 PG 兼容视图（与 PG 12 等价）

```sql
-- 会话状态与等待事件分布
SELECT state, wait_event_type, wait_event, count(*)
FROM pg_stat_activity GROUP BY 1,2,3 ORDER BY count(*) DESC;

SELECT pid, usename, datname, state, wait_event_type, wait_event,
       now() - query_start AS running_for, left(query,120) AS query
FROM pg_stat_activity WHERE state <> 'idle' ORDER BY running_for DESC;

-- 阻塞锁链
SELECT blocked_locks.pid AS blocked_pid, blocking_locks.pid AS blocking_pid,
       blocked_activity.query AS blocked_query, blocking_activity.query AS blocking_query
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_locks blocking_locks
  ON blocking_locks.locktype = blocked_locks.locktype
 AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
 AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
 AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;

-- 数据库级吞吐与缓存命中
SELECT datname, numbackends, xact_commit, xact_rollback,
       blks_read, blks_hit,
       round(blks_hit::numeric / nullif(blks_hit+blks_read,0), 4) AS hit_ratio,
       tup_returned, tup_fetched, temp_files, temp_bytes,
       deadlocks, conflicts
FROM pg_stat_database;

-- 后台写/检查点
SELECT * FROM pg_stat_bgwriter;

-- 复制状态（主库）
SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn,
       write_lag, flush_lag, replay_lag
FROM pg_stat_replication;

-- 表膨胀 / autovacuum 状态 Top 20
SELECT relname, n_dead_tup, n_live_tup, last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables ORDER BY n_dead_tup DESC LIMIT 20;

-- 正在进行的 vacuum 进度
SELECT * FROM pg_stat_progress_vacuum;
```

#### Step 2.2 KB-extra：sys_catalog.sys_stat_* 动态性能视图（金仓独有，比 PG 更强大）

```sql
-- ① 当前时刻的 SQL 全维度画像（db_time / db_cpu / db_wait / wait_event 排名 / parse/plan/exec 拆分 / IO 大小 / WAL 大小 / 缓存命中率）
--    单表等价于 pg_stat_statements + pg_stat_kcache + 等待事件 + WAL 统计的并集
SELECT
  s.datname, s.username, s.queryid,
  left(s.query, 120) AS query,
  s.calls,
  round(s.db_time::numeric/1000, 1)              AS db_time_ms,
  round(s.db_cpu::numeric/1000, 1)               AS db_cpu_ms,
  round(s.db_wait::numeric/1000, 1)              AS db_wait_ms,
  s.total_db_time_pct, s.cpu_time_pct, s.wait_time_pct,
  s.wait_event_1, s.wait_calls_1, round(s.wait_time_1::numeric/1000,1) AS wait_time_1_ms,
  s.wait_event_2,
  round(s.parse_time::numeric/1000, 1)           AS parse_time_ms,
  round(s.plan_time::numeric/1000, 1)            AS plan_time_ms,
  round(s.exec_time::numeric/1000, 1)            AS exec_time_ms,
  s.wal_size, s.shared_blks_read_size, s.shared_blks_write_size,
  s.temp_blks_read_size, s.temp_blks_write_size,
  s.shared_blks_hit
FROM sys_catalog.sys_stat_sql s
ORDER BY s.db_time DESC
LIMIT 20;

-- ② 等待事件全局分布（等价 Oracle V$SYSTEM_WAIT / V$SYSTEM_EVENT）
SELECT event_type, wait_event, calls, total_time,
       round(avg_time::numeric, 2) AS avg_time,
       round(dbtime_pct::numeric, 2) AS dbtime_pct
FROM sys_catalog.sys_stat_wait
ORDER BY total_time DESC
LIMIT 20;

-- ③ SQL × 等待事件交叉矩阵（找出"哪条 SQL 大量等待哪种事件"）
SELECT s.username, s.queryid, left(s.query,80) AS query,
       w.wait_event_type, w.wait_event, w.calls, round(w.times::numeric/1000,1) AS times_ms
FROM sys_catalog.sys_stat_sqlwait w
JOIN sys_catalog.sys_stat_sql s USING (userid, datid, queryid)
WHERE w.calls > 0
ORDER BY w.calls DESC LIMIT 30;

-- ④ WAL buffer 实时写入状态（用于确认窗口内 WAL 是否堆积）
SELECT name, bytes, utilization_rate, write_rate,
       written_to_lsn, written_to_lsn - copied_to_lsn AS unwritten_lsn
FROM sys_catalog.sys_stat_wal_buffer;

-- ⑤ 数据库总 DB time（验证负载整体水位）
SELECT sum(db_time) AS total_db_time_us, sum(db_cpu) AS total_db_cpu_us,
       sum(db_wait) AS total_db_wait_us
FROM sys_catalog.sys_stat_sql;

-- ⑥ DML/调用次数汇总（看到底是 OLTP 高频小事务还是大查询在拖）
SELECT datid::regclass::text AS datname, sql_type, background, sum(calls) AS calls, sum(times) AS times
FROM sys_catalog.sys_stat_sqlcount
GROUP BY 1,2,3
ORDER BY calls DESC LIMIT 20;
```

> **重要**：这些 sys_stat_* 视图本质都是累计计数器，复盘型取证仍然需要"两次快照做差"或者**优先用 Step 2.3 的 AWR 历史仓库**。如果窗口内 sys_stat_* 视图的 `stats_reset` 早于窗口起点，则累计值可直接代表窗口内总发生量。

#### Step 2.3 KB-extra：AWR 风格历史仓库（sys_stat_metric_history / sys_stat_sysmetric_history）——窗口回溯的金标准

```sql
-- ① 窗口内的"系统级"指标时序（CPU/QPS/TPS 等）
SELECT begin_time, end_time, metric_name, metric_unit,
       metric_value, rel_value, abs_value
FROM sys_catalog.sys_stat_sysmetric_history
WHERE end_time   >= '2026-08-09 02:00:00+08'
  AND begin_time <= '2026-08-09 03:00:00+08'
ORDER BY begin_time, metric_name;

-- ② 窗口内的指标名（meta 字典）
SELECT group_id, group_name, metric_id, metric_name, metric_unit
FROM sys_catalog.sys_stat_metric_name
ORDER BY group_id, metric_id;

-- ③ 窗口内更细粒度的指标（如 buffer hit / wait count 等）
SELECT begin_time, metric_name, metric_unit, metric_value
FROM sys_catalog.sys_stat_metric_history
WHERE end_time   >= '2026-08-09 02:00:00+08'
  AND begin_time <= '2026-08-09 03:00:00+08'
ORDER BY begin_time, metric_name;
```

> 如果查询返回 0 行，说明 `sys_kwr` 扩展未开启或 interval 间隔尚未触发——此时必须**回到 Step 1 日志**与外部监控历史数据做时间切片，并在规避建议中要求开启 KWR。

### Step 3：扩展/插件维度

1. **`sys_stat_statements`**（金仓默认开启，位于 `public` schema，是 `pg_stat_statements` 的 PG 兼容同义视图，可直接用 `SELECT * FROM sys_stat_statements` 或 `SELECT * FROM pg_stat_statements` —— 二者实为同一视图）：
   ```sql
   SELECT left(query, 120) AS query, calls, total_exec_time, mean_exec_time, rows,
          shared_blks_hit, shared_blks_read, temp_blks_written
   FROM sys_stat_statements ORDER BY total_exec_time DESC LIMIT 20;
   ```
   金仓中**更推荐**直接查 `sys_catalog.sys_stat_sql`（Step 2.2 ①），因为它还带 CPU/Wait/IO size 等拆分，是 `sys_stat_statements` 的超集。
2. **KB 推荐 `sys_stat_sql` + `sys_stat_sqlwait`**：分别给出 SQL 总耗时画像与 SQL × 等待事件矩阵，比 PG 单独的 `pg_stat_statements` + `pg_stat_kcache` 强大。
3. **KB 推荐 `sys_kwr` + `sys_stat_sysmetric_history`**：若已开启，能给出窗口内时序，是回溯型证据的第一来源，弥补 `pg_stat_activity` 只有快照没有历史的缺陷。
4. 若以上扩展均未安装/未开启，在报告中明确列为"证据缺口"，并在规避建议中建议后续安装以增强可观测性，而不是跳过这一节不提。

### Step 4：操作系统维度

1. 历史指标（依赖 sysstat 是否采集了 sar 历史数据，通常保存在 `/var/log/sa/`）：
   ```bash
   sar -u -s 02:00:00 -e 03:00:00     # CPU：user/system/iowait
   sar -q -s 02:00:00 -e 03:00:00     # load average、runqueue
   sar -r -s 02:00:00 -e 03:00:00     # 内存、swap
   sar -B -s 02:00:00 -e 03:00:00     # 换页/swap 活动
   ```
2. 事件型日志（不依赖历史采集，任何时候都能查历史，是 OS 维度最可靠的证据）：
   ```bash
   dmesg -T | grep -iE "oom|out of memory|killed process"
   journalctl --since "2026-08-09 02:00:00" --until "2026-08-09 03:00:00" -p warning
   grep -iE "oom|segfault|kernel" /var/log/messages
   ```
   OOM Killer 击杀了 `kingbase` 进程是导致数据库瞬时不可用/连接风暴的经典根因，必须优先排除。
3. CPU 层面区分 `%user`（数据库/应用计算）、`%system`（内核态，常与频繁系统调用/锁/调度相关）、`%iowait`（等待磁盘）——三者中哪个飙升直接决定后续应聚焦存储还是聚焦 SQL 计算。
4. 若数据库运行在容器/K8s 中，额外检查 cgroup 限流：
   ```bash
   kubectl top pod <kb-pod> --containers
   cat /sys/fs/cgroup/cpu/cpu.stat | grep throttled   # cgroup v1
   cat /sys/fs/cgroup/cpu.stat                        # cgroup v2
   ```
   `throttled_time` 骤增说明容器 CPU limit 设置过小导致被限流，表现为"数据库变慢"但根因在编排层而非数据库本身。

### Step 5：存储维度

1. 历史 IO 指标：
   ```bash
   sar -d -p -s 02:00:00 -e 03:00:00   # 各磁盘 tps、await、%util
   iostat -x 1 10                       # 若无历史数据，至少确认当前基线做对比
   ```
   `%util` 接近 100% 且 `await` 显著高于平常基线，指向磁盘 IO 饱和；结合 Step1 的 checkpoint/autovacuum 日志判断是数据库自身写放大导致，还是同宿主机其他租户/进程抢占了 IO。
2. 空间层面：
   ```bash
   df -h
   du -sh ${DATA_DIR}/ # WAL 目录就在 data_directory 下
   ```
   `pg_wal`（KB 中实际目录名可能为 `wal` 或类似，参照 `SHOW data_directory`）目录异常膨胀（对应 Step2 中检查点被动触发占比高）可能进一步导致磁盘写满，写满后数据库会 PANIC 停止写入，是最严重的级联故障路径之一。
3. 文件系统层面：检查是否存在文件系统只读挂载（fs remount read-only，通常伴随 dmesg 中的文件系统错误日志）、inode 耗尽（`df -i`）等非直觉的存储类故障。

### Step 6：网络维度

1. 连接数与连接状态：
   ```bash
   ss -s
   ss -tan state established '( dport = :5432 or sport = :5432 )' | wc -l
   ```
   结合 Step2 的 `pg_stat_activity` 会话数，判断连接数暴涨是应用侧连接池配置问题（如异常重连风暴）还是数据库慢导致连接被应用侧重试性堆积（连接风暴通常是"结果"而非"原因"，注意不要倒因为果）。
2. 网络质量：
   ```bash
   sar -n DEV -s 02:00:00 -e 03:00:00      # 网卡吞吐
   sar -n ETCP -s 02:00:00 -e 03:00:00     # TCP 重传等异常统计
   ```
   重传率异常升高、网卡吞吐骤降/骤升都可能是跨机房复制延迟、客户端连接超时重试的根因之一。
3. 若为云环境，还需检查安全组/NAT 网关/负载均衡层是否有当时的限流或异常日志，这一层的问题从数据库自身指标里通常看不出来，容易被误判为"数据库问题"。

### Step 7：时间线整合与根因链条推导

1. 把 Step1~Step6 收集到的所有带时间戳的证据，按时间顺序合并成一条统一时间线（建议用表格：`时间 | 维度 | 现象 | 证据来源`）。
2. 找到**最早出现异常的维度**作为疑似起点，沿"操作系统/存储/网络（外部环境）→ 数据库内部资源竞争（锁/IO/内存）→ SQL 执行层（慢查询/计划回归）→ 连接层堆积（应用侧感知的'卡顿'）"这条常见传导路径做正向验证，同时做反向验证（排除"表面上最先出现异常"实际只是被更早的隐藏原因触发的下游表现）。
3. **KB 特有根因**（与 Oracle/PG 类似，但触发链路略有不同）：
   - `KshMain` 自身异常（`sys_stat_*` / AWR 仓库写入失败）→ 后续性能证据缺口，DBA 无法回溯历史
   - `LogicalLauncherMain`（逻辑复制 launcher）异常 → 逻辑复制堆积，主库 WAL 增长触发检查点风暴（KB 比 PG 默认多这一类后台进程）
   - `sysaudit` 开启后审计日志被频繁写入 → 间接 IO 放大（KB 特有）
   - `sysmac` 强制访问控制策略匹配耗时 → 某些表的查询被策略引擎串行化（KB 特有）
   - RWC 读写分离集群备库回放跟不上 → 主库 replay_lag 突增
4. 常见根因链条模式（可作为假设清单去逐一验证或证伪，不要直接套用而不核实证据）：
   - `大表 autovacuum / 防回卷强制清理` → 长时间占用 IO 与 CPU → 检查点被拖慢/被动触发增多 → 其他查询 IO 等待上升 → 连接堆积 → 应用感知变慢
   - `慢 SQL 计划回归`（如统计信息过期、`ANALYZE` 未及时执行、参数嗅探导致 Bad Plan）→ 单条查询消耗骤增 → 数据库整体资源被少数会话占满 → 其他会话排队
   - `锁等待链`：某个长事务（如未提交的 `BEGIN`、大批量 DDL/DML）持有锁 → 后续同表访问全部排队 → `pg_stat_activity` 中 `wait_event_type=Lock` 堆积 → 连接数被动堆高
   - `外部环境`：云盘 IOPS 限流 / 容器 CPU throttle / 同宿主机噪声邻居 / 网络抖动 → 数据库表现为"莫名其妙变慢"，但数据库内部指标（锁、计划）本身并无异常
   - `OOM Killer 误杀 kingbase 子进程` → 触发数据库 crash-recovery → 短时间内所有连接被断开重连
5. 每一条根因链条必须标注置信度（高/中/低）和支撑证据数量，证据不足时诚实标注"存在多个可能根因，无法唯一定位，建议增强以下可观测性后再复盘"。

### Step 8：影响面评估

1. 影响的对象：哪些数据库/schema/表/应用连接池受到影响，是否波及从库/只读实例/RWC 备库，是否触发了应用侧超时/重试/熔断。
2. 影响的时长：飙升开始到恢复正常的完整区间，是否有反复抖动（多个波峰）而非单一峰值。
3. 影响的严重程度：是否有请求失败/超时对外可见，是否有数据不一致风险（如从库延迟导致读到旧数据）、是否逼近资源硬限（磁盘写满、连接数打满、OOM）。

### Step 9：规避建议

针对已定位的根因，给出**具体、可执行、有优先级**的规避建议，区分：
- **立即可做（参数/运维层面）**：如调整 `autovacuum_vacuum_cost_limit`、`max_wal_size`、`work_mem`，增加慢查询告警阈值，给大表单独配置 autovacuum 参数，增加连接池排队上限而非直连风暴。
- **KB 特有立即可做**：
  - **开启 `log_min_duration_statement`**（默认 -1，等于关闭慢查询日志）以便后续能回溯慢 SQL；
  - **开启 `auto_explain` + `log_min_duration_statement`**，把慢 SQL 的执行计划落盘；
  - **开启 `sys_kwr` 扩展**，把累计型 `sys_stat_*` 视图按 interval 自动落库；
  - **关闭不必要的 `sysaudit` 详尽审计**，避免审计日志写入放大 IO；
  - **审视 `sysmac` 策略**，避免行级策略匹配成为热路径瓶颈。
- **需要验证再上线（SQL/索引层面）**：如为回归的执行计划补充索引、更新统计信息频率、SQL 改写。
- **架构/容量层面**：如磁盘 IOPS 扩容、连接池分层、读写分离承接部分从库压力、容器资源 request/limit 重新评估。
- **可观测性增强**：若发现证据缺口（如未装 `sys_kwr`、未采集 `sar` 历史、无慢查询计划记录），明确建议补齐。

## 输出格式

产出一份 Markdown 报告，结构如下：

```markdown
# KingbaseES 负载飙升取证报告 [起止时间]

## 摘要
一段话概括：飙升区间、核心根因（若已定位）、置信度、影响范围。

## 时间线
| 时间 | 维度 | 现象 | 证据来源 |
|---|---|---|---|

## 各维度详细表现
### 数据库日志
### 数据库统计视图（含 KB-extra sys_stat_* 与 AWR 历史仓库）
### 扩展/插件
### 操作系统
### 存储
### 网络

（每节：关键发现 + 原始证据摘录 + 是否异常的判断依据）

## 根因链条
（假设 → 验证过程 → 结论，标注置信度；若多个可能根因并存需分别说明）

## 影响面
（对象 / 时长 / 严重程度）

## 规避建议
（立即可做 / 需验证再上线 / 架构层面 / 可观测性增强，按优先级排列）

## 证据缺口与局限性
（哪些维度因缺少工具/历史数据无法完全还原，如实说明）
```

## Pitfalls & Solutions

| 坑点 | 后果 | 解决方案 |
|---|---|---|
| 把 `pg_stat_*` / `sys_stat_*` 累计视图当作"窗口内"的值直接下结论 | 结论时间错位，可能把历史遗留问题误判为本次窗口根因 | 必须结合日志/AWR 历史仓库做时间切片，无历史快照时明确标注"当前快照，仅供参考" |
| 数据库日志时区与操作系统日志时区不一致 | 时间线对不齐，根因链条推导方向错误 | Step0 强制确认 `log_timezone` 与 `timedatectl`，统一换算 |
| 只看到"连接数暴涨"就下结论是数据库慢 | 倒因为果，连接堆积往往是下游症状而非根因 | 沿 Step7 的传导路径反向验证是否有更早的锁/IO/计划异常作为真正起点 |
| 云托管数据库无法执行 OS 层命令 | Step4/5 证据缺失 | 改用云厂商监控 API/控制台指标（CPU/IOPS/网络/OOM 事件），并在报告中注明数据来源为云监控而非本机采集 |
| `sys_stat_statements` 未清空过、跨越了多次故障 | 增量归因困难，Top N 可能是历史累计而非本次窗口 | **优先**用 `sys_kwr`/`sys_stat_sysmetric_history` 取窗口内时序快照；若数据库支持，对 `sys_stat_statements` 用两次快照做差；否则降级为"参考性证据"并说明局限 |
| 把"表面最先出现异常的维度"当作根因 | 遗漏更早的隐藏触发因素（如 autovacuum 早于窗口开始） | Step7 要求同时做正向和反向验证，扩大排查的起始时间边界（往前多看 30-60 分钟） |
| 使用了破坏性/写操作命令做诊断 | 违反只读取证原则，可能进一步影响生产 | 严格限定在 SELECT 查询、日志 grep、只读系统命令范围内，任何需要执行的干预都写入"规避建议"交由人工审批执行 |
| **KB 特有**：未开启 `log_min_duration_statement` | 金仓默认**不记慢 SQL**，导致 Step 1 日志维度证据严重缺失 | Step 0 必须检查该参数并立即在"规避建议"里要求打开 |
| **KB 特有**：未开启 `sys_kwr` 扩展 | AWR 历史仓库为空，无法用 sys_stat_sysmetric_history 做时序回溯 | Step 0 必须检查 `sys_stat_metric_history` 行数；为空时降级为"日志 + 当前累计视图"路径 |
| **KB 特有**：忽略 `KshMain`/`LogicalLauncherMain` 等金仓独有后台进程异常 | 这些进程本身异常也能引起主库性能抖动 | Step 0 必须 `pg_stat_activity WHERE backend_type LIKE '%worker%'` 一并核对 |
| **KB 特有**：误用 `regdatabase` 类型转换 | PG 有 `regdatabase` 伪类型，金仓可能没有 | `sys_stat_sql` 中查 `datid::oid::text` 或 `datname::text`，不要依赖 `::regdatabase` |

## 注意事项

- 本 skill 全程只读，不执行任何修改数据库参数、重启服务、`kill` 进程、`VACUUM FULL`、`DROP`/`TRUNCATE` 等操作；如确需干预，仅在报告"规避建议"中提出方案，由人工评估后执行。
- 需要 `sys_monitor` 角色（PG 兼容，等价 `pg_monitor`）或等效只读权限访问统计视图与 AWR 仓库，需要文件系统读权限访问数据库与操作系统日志；不要求也不应尝试获取超出诊断范围的权限。
- 云托管实例（RDS/华为云 GaussDB 等）通常无法执行 Step4/5 中的本机 OS 命令，需替换为对应云厂商的监控指标查询方式，并在报告中如实说明数据来源。
- 若时间窗口内的原始日志已被滚动清理（超出 `log_rotation_size` / 保留天数），如实告知用户该维度证据已不可获取，不要编造或用其他时段数据冒充。
- 输出报告使用中文，术语（如 `wait_event`、`checkpoint`、`sys_stat_sql`、`sys_kwr`）保留英文原名以保证与官方文档一致。
- 自动化只读取证脚本见 `scripts/collect_kb_stats.sql`（psql）、`scripts/collect_kb_stats.py`（psycopg2）、`scripts/collect_os_metrics.sh`；红旗信号速查见 `references/dimension-checklist.md`；KB 特有的视图映射、`sys_kwr` 启用方式、KingbaseES 默认日志切分规则等见 `references/edge_cases.md`。
- 参考官方文档入口：[性能调优工具概述](https://docs.kingbase.com.cn/cn/KES-V9R1C10/perf/db-optimization/%E6%80%A7%E8%83%BD%E8%B0%83%E4%BC%98%E5%B7%A5%E5%85%B7/%E6%80%A7%E8%83%BD%E8%B0%83%E4%BC%98%E5%B7%A5%E5%85%B7%E6%A6%82%E8%BF%B0) / [动态性能视图](https://docs.kingbase.com.cn/cn/KES-V9R1C10/perf/db-optimization/%E6%80%A7%E8%83%BD%E8%B0%83%E4%BC%98%E5%B7%A5%E5%85%B7/%E5%8A%A8%E6%80%81%E6%80%A7%E8%83%BD%E8%A7%86%E5%9B%BE) / [KSH 报告](https://docs.kingbase.com.cn/cn/KES-V9R1C10/perf/db-optimization/%E6%80%A7%E8%83%BD%E8%B0%83%E4%BC%98%E5%B7%A5%E5%85%B7/KSH%E6%8A%A5%E5%91%8A) / [KWR 报告](https://docs.kingbase.com.cn/cn/KES-V9R1C10/perf/db-optimization/%E6%80%A7%E8%83%BD%E8%B0%83%E4%BC%98%E5%B7%A5%E5%85%B7/KWR%E6%8A%A5%E5%91%8A)。