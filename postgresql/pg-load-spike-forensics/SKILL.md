---
name: pg-load-spike-forensics
description: "扮演 PostgreSQL DBA 专家 + 操作系统专家 + 网络专家 + 存储专家，对给定的一段可疑时间窗口做数据库负载飙升的多维取证分析。触发条件：用户给出一个时间段并提到'负载飙升'、'CPU飙高'、'load average 很高'、'数据库卡顿'、'突然变慢'、'连接数暴涨'、'慢查询突增'、'IO打满'、'内存暴涨/OOM'、'那段时间发生了什么'、'帮我排查一下这段时间的数据库'、'复盘一次故障'、'故障根因分析'、'RCA'，或提供了 postgresql 日志/系统日志并希望定位问题根因。即使用户只说'昨晚2点到3点数据库很慢，帮我查查为什么'或'这段时间是不是数据库出问题了'，也应使用本 skill。本 skill 覆盖数据库日志、统计信息视图（pg_stat_*）、扩展插件（pg_stat_statements/pg_stat_kcache/pg_wait_sampling/auto_explain）、操作系统日志与指标（dmesg/journalctl/sar/vmstat）、存储（iostat/df/WAL增长）、网络（ss/netstat/tcp重传/复制延迟）六大维度，产出时间线、根因链条、影响面和规避建议。"
tags: [PostgreSQL, 负载问题, 问题溯源, 性能分析, 异常分析, 抖动分析]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# PostgreSQL 负载飙升多维取证分析

给定一个时间窗口，综合数据库日志、统计视图、扩展插件、操作系统、存储、网络六大维度的证据，重建负载飙升的时间线，溯源根本原因，评估影响面，并给出可落地的规避建议。输出一份可直接用于故障复盘（RCA）的 Markdown 报告。

## 核心原则

1. **先假设"确有其事"，再用证据证伪或证实** — 不要预设结论，时间窗口内也可能是正常业务高峰。每一条结论必须有至少一个维度的原始证据支撑，标注证据来源（文件+行号/视图+采集时间）。
2. **时间对齐是第一优先级** — 数据库日志、OS 日志、监控采集点的时区/时钟可能不一致，必须先确认 `timezone`、`log_timezone`、服务器 `timedatectl` 输出，将所有证据换算到同一时区后再建时间线。
3. **区分"症状"与"病因"** — CPU 飙高、连接数暴涨往往是下游症状；锁等待、IO 饱和、autovacuum 风暴、计划变化、连接风暴（thundering herd）才是常见病因。工作流程按"由外到内、由表及里"收窄。
4. **只读取证，不做变更** — 本 skill 只执行只读诊断命令（SELECT、日志 grep、sar/vmstat/iostat 读取），不修改数据库参数、不重启服务、不 kill 进程。如需干预，在报告"规避建议"中给出方案供人工审批执行。
5. **证据链闭环** — 最终报告必须能回答：什么时候开始 → 最先出现异常的维度是什么 → 传导路径是什么 → 影响了哪些库/表/应用 → 什么时候恢复/是否仍在持续 → 下次如何提前发现或避免。

## 前置要求

- **数据库访问**：具备 `pg_monitor` 角色或 superuser 权限的只读账号，用于查询 `pg_stat_*` 视图；若时间窗口已过去，这些视图多为累计值/当前快照，需结合日志与监控历史数据（Prometheus/Zabbix/云厂商监控）做时间切片，不能仅凭"现在查到的视图"倒推历史某一时刻。
- **日志访问权限**：读取 PostgreSQL 日志目录（`SHOW log_directory`、`SHOW data_directory`）以及操作系统日志（`/var/log/messages`、`journalctl`、`dmesg`）。若数据库部署在容器/K8s 中，改用 `kubectl logs`、`crictl logs` 或容器日志采集平台。
- **已装/建议安装的扩展**（不存在则在报告中注明"该维度证据缺失"，不要臆造）：
  - `pg_stat_statements`（SQL 级性能画像，几乎必备）
  - `pg_stat_kcache`（结合 OS 级 CPU/IO 消耗到 SQL 粒度）
  - `pg_wait_sampling`（等待事件采样历史，PG 原生 `pg_stat_activity.wait_event` 只是快照，没有历史采样能力很难回溯）
  - `auto_explain`（若开启，日志中会有慢 SQL 的执行计划，是排查计划突变的关键证据）
- **操作系统工具**：`sar`（sysstat 包，提供历史 CPU/内存/IO/网络数据，是回溯"过去某个时间点"系统状态的核心工具，若未安装或未采集历史数据，需在报告中明确指出该维度只能靠 dmesg/journalctl 等事件型日志补充）、`iostat`、`vmstat`、`ss`、`netstat`、`journalctl`、`dmesg`。
- **前提确认**：向用户确认或从上下文中提取——目标时间窗口（含时区）、数据库版本 `SELECT version();`、部署形态（单机/主从/多活/云托管，云托管上很多 OS 层命令不可执行，需改用云监控 API 或控制台指标）、是否有历史监控系统可查（Prometheus/Grafana/云监控），若有应优先用其做"面"上的定位，本 skill 的手工排查用于"点"上补充证据链。

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
   ```
3. ```bash
   timedatectl
   uname -a
   cat /etc/os-release
   nproc
   free -h
   df -h
   ```
4. 若为主从/多活架构，同时对主库和相关从库分别执行 Step1~Step6，因为负载飙升可能源自任意一侧（例如从库大查询拖慢复制、或主库故障切换引发从库瞬时负载）。

### Step 1：数据库日志维度

1. 定位窗口内的日志文件（PostgreSQL 默认按天/按小时切分），用时间戳 grep 精确圈定窗口：
   ```bash
   awk -v start="2026-07-11 02:00:00" -v end="2026-07-11 03:00:00" \
     '$0 >= start && $0 <= end' /var/log/postgresql/postgresql-*.log
   ```
2. 重点关注以下信号（按优先级排序，出现即记入证据表）：
   - `FATAL` / `PANIC` / `could not fork new process` —— 资源耗尽或连接数打满
   - `checkpoint starting` / `checkpoint complete` 且 `... sync=... total=...` 时间显著变长，或出现 `checkpoints are occurring too frequently` —— 检查点风暴，通常与 IO 饱和或 `max_wal_size` 设置过小相关
   - `automatic vacuum of table ...` 且耗时/dead tuple 数远超平常，或 `autovacuum: ... to prevent wraparound` —— autovacuum 风暴或事务 ID 回卷紧急清理，会抢占大量 IO 并可能长期持有锁
   - `duration: ... ms statement:` 超过 `log_min_duration_statement` 的慢查询集中爆发
   - `process ... still waiting for ... lock` / `deadlock detected` —— 锁等待/死锁
   - `temporary file: ... size ...` 集中出现且体积大 —— `work_mem` 不足导致排序/哈希落盘，会放大 IO
   - `unexpected EOF on client connection` / `could not receive data from client` —— 客户端异常断开，常是网络或应用侧问题的反向信号
   - `out of memory` / `terminating connection because of crash of another server process` —— OOM 或进程异常终止
3. 如果开启了 `auto_explain`，提取窗口内被记录的执行计划，比对同一 SQL 在正常时段的计划（若有 `pg_stat_statements` 历史快照或 `pg_stat_plans` 之类扩展）判断是否发生了计划回归（plan regression）。
4. 将每条证据记录为 `[时间戳] [日志级别] [摘要] [原文片段]`，供后续与其他维度时间线对齐。

### Step 2：数据库统计信息视图维度

> 注意：`pg_stat_*` 多为累计计数器或当前时刻快照，若窗口已过去且无历史采样（无 `pg_wait_sampling`、无外部监控落库），只能做"事后现状 vs. 日志/监控历史"的交叉验证，不能直接把"现在查到的值"当作"窗口内的值"。以下查询在故障发生时或刚发生后执行价值最大；事后复盘时优先用 Step1 日志与外部监控历史，视图查询用于验证当前是否仍有残留异常（如未清理的锁、膨胀未回收）。

1. 连接与会话状态：
   ```sql
   SELECT state, wait_event_type, wait_event, count(*)
   FROM pg_stat_activity GROUP BY 1,2,3 ORDER BY count(*) DESC;

   SELECT pid, usename, datname, state, wait_event_type, wait_event,
          now() - query_start AS running_for, left(query,120) AS query
   FROM pg_stat_activity
   WHERE state <> 'idle'
   ORDER BY running_for DESC;
   ```
   若窗口内 `state = 'active'` 且大量堆积、`wait_event_type = 'Lock'` 集中，指向锁竞争；`wait_event_type = 'IO'`（如 `DataFileRead`）集中指向存储瓶颈；`wait_event_type = 'Client'` 集中通常是应用侧慢/网络慢导致连接被占用而非数据库本身慢。
2. 锁等待链（判断阻塞根源）：
   ```sql
   SELECT blocked_locks.pid AS blocked_pid,
          blocking_locks.pid AS blocking_pid,
          blocked_activity.query AS blocked_query,
          blocking_activity.query AS blocking_query
   FROM pg_catalog.pg_locks blocked_locks
   JOIN pg_catalog.pg_locks blocking_locks
     ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
    AND blocking_locks.pid != blocked_locks.pid
   JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
   JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
   WHERE NOT blocked_locks.granted;
   ```
3. 数据库级吞吐与缓存命中：
   ```sql
   SELECT datname, numbackends, xact_commit, xact_rollback,
          blks_read, blks_hit,
          round(blks_hit::numeric / nullif(blks_hit+blks_read,0), 4) AS hit_ratio,
          tup_returned, tup_fetched, temp_files, temp_bytes,
          deadlocks, conflicts
   FROM pg_stat_database;
   ```
   `hit_ratio` 骤降、`temp_files/temp_bytes` 骤增、`deadlocks` 非零都是窗口内异常的强信号（需结合外部监控确认是否为窗口内的增量，而非历史累计）。
4. 后台写进程/检查点：
   ```sql
   SELECT * FROM pg_stat_bgwriter;   -- PG < 17，PG 17+ 拆分为 pg_stat_checkpointer
   SELECT * FROM pg_stat_checkpointer; -- PG 17+
   ```
   `checkpoints_req` 相对 `checkpoints_timed` 占比高，说明是被动触发（WAL 写入过快），提示存在写放大或 `max_wal_size` 偏小。
5. 复制状态（主从/多活场景）：
   ```sql
   SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn,
          write_lag, flush_lag, replay_lag
   FROM pg_stat_replication;

   SELECT * FROM pg_stat_wal_receiver;  -- 从库侧
   ```
   `replay_lag` 突增指向从库 IO/CPU 跟不上，或主库产生了大事务/大量 WAL。
6. 表膨胀与 vacuum 状态：
   ```sql
   SELECT relname, n_dead_tup, n_live_tup, last_autovacuum, last_autoanalyze
   FROM pg_stat_user_tables
   ORDER BY n_dead_tup DESC LIMIT 20;

   SELECT * FROM pg_stat_progress_vacuum;
   ```

### Step 3：扩展/插件维度

1. `pg_stat_statements`（累计值，需要"窗口前后两次快照做差"或结合已有历史快照表才能精确定位窗口内的增量；若无历史快照，只能给出"当前累计 Top N"作为参考证据，并在报告中注明局限性）：
   ```sql
   SELECT query, calls, total_exec_time, mean_exec_time, rows,
          shared_blks_hit, shared_blks_read, temp_blks_written
   FROM pg_stat_statements
   ORDER BY total_exec_time DESC LIMIT 20;
   ```
2. `pg_stat_kcache`（若安装）：结合 `pg_stat_statements` 关联 SQL 粒度的真实 CPU 时间和物理 IO，判断是"CPU 密集型"还是"IO 密集型"的慢 SQL。
3. `pg_wait_sampling`（若安装，是回溯历史等待事件分布的关键，弥补 `pg_stat_activity` 只有快照没有历史的缺陷）：
   ```sql
   SELECT event_type, event, count(*)
   FROM pg_wait_sampling_history
   WHERE ts BETWEEN '2026-07-11 02:00:00' AND '2026-07-11 03:00:00'
   GROUP BY 1,2 ORDER BY count(*) DESC;
   ```
4. 若以上扩展均未安装，在报告中明确列为"证据缺口"，并在规避建议中建议后续安装以增强可观测性，而不是跳过这一节不提。

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
   journalctl --since "2026-07-11 02:00:00" --until "2026-07-11 03:00:00" -p warning
   grep -iE "oom|segfault|kernel" /var/log/messages
   ```
   OOM Killer 击杀了 `postgres` 进程是导致数据库瞬时不可用/连接风暴的经典根因，必须优先排除。
3. CPU 层面区分 `%user`（数据库/应用计算）、`%system`（内核态，常与频繁系统调用/锁/调度相关）、`%iowait`（等待磁盘）——三者中哪个飙升直接决定后续应聚焦存储还是聚焦 SQL 计算。
4. 若数据库运行在容器/K8s 中，额外检查 cgroup 限流：
   ```bash
   kubectl top pod <pg-pod> --containers
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
   `%util` 接近 100% 且 `await` 显著高于平常基线，指向磁盘 IO 饱和；结合 Step1 的 checkpoint/autovacuum 日志判断是数据库自身写放大导致，还是同宿主机其他租户/进程抢占了 IO（云盘场景下检查是否触发了云盘 IOPS/带宽限流，通常在云监控里能看到限流指标）。
2. 空间层面：
   ```bash
   df -h
   du -sh <data_directory>/pg_wal/
   ```
   `pg_wal` 目录异常膨胀（对应 Step2 中检查点被动触发占比高）可能进一步导致磁盘写满，写满后数据库会 PANIC 停止写入，是最严重的级联故障路径之一，需重点排查窗口内 `df` 剩余空间是否触底。
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
3. 若为云环境，还需检查安全组/NAT网关/负载均衡层是否有当时的限流或异常日志，这一层的问题从数据库自身指标里通常看不出来，容易被误判为"数据库问题"。

### Step 7：时间线整合与根因链条推导

1. 把 Step1~Step6 收集到的所有带时间戳的证据，按时间顺序合并成一条统一时间线（建议用表格：`时间 | 维度 | 现象 | 证据来源`）。
2. 找到**最早出现异常的维度**作为疑似起点，沿"操作系统/存储/网络（外部环境）→ 数据库内部资源竞争（锁/IO/内存）→ SQL 执行层（慢查询/计划回归）→ 连接层堆积（应用侧感知的'卡顿'）"这条常见传导路径做正向验证，同时做反向验证（排除"表面上最先出现异常"实际只是被更早的隐藏原因触发的下游表现，例如 autovacuum 在窗口开始前几十分钟就已启动，只是在窗口内才因为 IO 竞争加剧才表现为可观测的变慢）。
3. 常见根因链条模式（可作为假设清单去逐一验证或证伪，不要直接套用而不核实证据）：
   - `大表 autovacuum / 防回卷强制清理` → 长时间占用 IO 与 CPU → 检查点被拖慢/被动触发增多 → 其他查询 IO 等待上升 → 连接堆积 → 应用感知变慢
   - `慢 SQL 计划回归`（如统计信息过期、`ANALYZE` 未及时执行、参数嗅探导致 Bad Plan）→ 单条查询消耗骤增 → 数据库整体资源被少数会话占满 → 其他会话排队
   - `锁等待链`：某个长事务（如未提交的 `BEGIN`、大批量 DDL/DML）持有锁 → 后续同表访问全部排队 → `pg_stat_activity` 中 `wait_event_type=Lock` 堆积 → 连接数被动堆高
   - `外部环境`：云盘 IOPS 限流 / 容器 CPU throttle / 同宿主机噪声邻居 / 网络抖动 → 数据库表现为"莫名其妙变慢"，但数据库内部指标（锁、计划）本身并无异常，此时必须优先看 Step4/5/6 而非在 SQL 层面死磕
   - `OOM Killer 误杀 postgres 子进程` → 触发数据库 crash-recovery → 短时间内所有连接被断开重连 → 表现为"瞬时飙升 + 瞬时抖动恢复"的脉冲形态，区别于持续性飙升
4. 每一条根因链条必须标注置信度（高/中/低）和支撑证据数量，证据不足时诚实标注"存在多个可能根因，无法唯一定位，建议增强以下可观测性后再复盘"，不要为了给出确定结论而过度诠释。

### Step 8：影响面评估

1. 影响的对象：哪些数据库/schema/表/应用连接池受到影响，是否波及从库/只读实例，是否触发了应用侧超时/重试/熔断。
2. 影响的时长：飙升开始到恢复正常的完整区间，是否有反复抖动（多个波峰）而非单一峰值。
3. 影响的严重程度：是否有请求失败/超时对外可见，是否有数据不一致风险（如从库延迟导致读到旧数据）、是否逼近资源硬限（磁盘写满、连接数打满、OOM）。

### Step 9：规避建议

针对已定位的根因，给出**具体、可执行、有优先级**的规避建议，区分：
- **立即可做（参数/运维层面）**：如调整 `autovacuum_vacuum_cost_limit`、`max_wal_size`、`work_mem`，增加慢查询告警阈值，给大表单独配置 autovacuum 参数，增加连接池排队上限而非直连风暴。
- **需要验证再上线（SQL/索引层面）**：如为回归的执行计划补充索引、更新统计信息频率、SQL 改写。
- **架构/容量层面**：如磁盘 IOPS 扩容、连接池分层、读写分离承接部分从库压力、容器资源 request/limit 重新评估。
- **可观测性增强**：若发现证据缺口（如未装 `pg_wait_sampling`、未采集 `sar` 历史、无慢查询计划记录），明确建议补齐，说明"补齐后下次能在多快时间内定位到什么级别的问题"。

## 输出格式

产出一份 Markdown 报告，结构如下：

```markdown
# 数据库负载飙升取证报告 [起止时间]

## 摘要
一段话概括：飙升区间、核心根因（若已定位）、置信度、影响范围。

## 时间线
| 时间 | 维度 | 现象 | 证据来源 |
|---|---|---|---|

## 各维度详细表现
### 数据库日志
### 数据库统计视图
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
| 把 `pg_stat_*` 累计视图当作"窗口内"的值直接下结论 | 结论时间错位，可能把历史遗留问题误判为本次窗口根因 | 必须结合日志/监控历史做时间切片，无历史快照时明确标注"当前快照，仅供参考" |
| 数据库日志时区与操作系统日志时区不一致 | 时间线对不齐，根因链条推导方向错误 | Step0 强制确认 `log_timezone` 与 `timedatectl`，统一换算 |
| 只看到"连接数暴涨"就下结论是数据库慢 | 倒因为果，连接堆积往往是下游症状而非根因 | 沿 Step7 的传导路径反向验证是否有更早的锁/IO/计划异常作为真正起点 |
| 云托管数据库无法执行 OS 层命令 | Step4/5 证据缺失 | 改用云厂商监控 API/控制台指标（CPU/IOPS/网络/OOM 事件），并在报告中注明数据来源为云监控而非本机采集 |
| `pg_stat_statements` 未清空过、跨越了多次故障 | 增量归因困难，Top N 可能是历史累计而非本次窗口 | 若数据库支持，用两次快照做差；否则降级为"参考性证据"并说明局限 |
| 把"表面最先出现异常的维度"当作根因 | 遗漏更早的隐藏触发因素（如 autovacuum 早于窗口开始） | Step7 要求同时做正向和反向验证，扩大排查的起始时间边界（往前多看 30-60 分钟） |
| 使用了破坏性/写操作命令做诊断 | 违反只读取证原则，可能进一步影响生产 | 严格限定在 SELECT 查询、日志 grep、只读系统命令范围内，任何需要执行的干预都写入"规避建议"交由人工审批执行 |

## 注意事项

- 本 skill 全程只读，不执行任何修改数据库参数、重启服务、`kill` 进程、`VACUUM FULL`、`DROP`/`TRUNCATE` 等操作；如确需干预，仅在报告"规避建议"中提出方案，由人工评估后执行。
- 需要 `pg_monitor` 角色或等效只读权限访问统计视图，需要文件系统读权限访问数据库与操作系统日志；不要求也不应尝试获取超出诊断范围的权限（如 `~/.ssh`、云账号密钥）。
- 云托管实例（RDS/PolarDB 等）通常无法执行 Step4/5 中的本机 OS 命令，需替换为对应云厂商的监控指标查询方式，并在报告中如实说明数据来源。
- 若时间窗口内的原始日志已被滚动清理（超出 `log_rotation_size`/保留天数），如实告知用户该维度证据已不可获取，不要编造或用其他时段数据冒充。
- 输出报告使用中文，术语（如 `wait_event`、`checkpoint`）保留英文原名以保证与官方文档一致，便于用户后续查证。
