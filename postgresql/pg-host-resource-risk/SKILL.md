---
name: pg-host-resource-risk
description: "对 PostgreSQL 数据库所在服务器进行物理资源风险评估，涵盖磁盘剩余空间、OOM 风险（服务器整体及 PG 进程级内存分析并关联数据库内部视图）、IO 设备使用率及等待、网络带宽使用率四大维度。触发场景包括：磁盘要满了、磁盘空间不足、OOM、内存不够、内存泄漏、进程吃内存、IO 打满、IO 等待高、iostat 告警、网络带宽跑满、服务器资源评估、主机巡检、物理资源体检、容量风险排查等。即使用户只说'帮我看看数据库服务器还撑得住吗'或'这台机器是不是快扛不住了'，也应触发本技能。支持本地直接执行或通过 SSH 远程执行，自动判断执行环境。"
tags: [PostgreSQL, 运行时服务器潜在风险分析, 剩余空间预警, OOM预警, 内存预警, IOPS预警, IO等待预警, IO带宽预警, 网络带宽预警]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# PG 主机资源风险评估 (pg-host-resource-risk)

对 PostgreSQL 所在服务器做一次只读体检：磁盘、内存(OOM)、IO、网络四个维度，每个维度都要把 OS 层现象关联回数据库内部视图，定位到具体目录/进程/SQL/复制槽/应用，最终产出一份分级的中文风险报告。

## 前置要求

- 数据库连接：通过环境变量 `PGPASSWORD` 提供密码，禁止在命令行明文传递密码。其余连接参数（`PGHOST`/`PGPORT`/`PGUSER`/`PGDATABASE`）按需设置。
- OS 命令：`df`, `free`, `ps`, `cat /proc/meminfo` 为必需，均为系统自带。`iostat`/`sar`（sysstat 包）、`iftop`/`nload` 为可选增强，缺失时跳过对应分析并在报告中注明局限性。
- 如需远程执行：用户提供 SSH 连接信息（主机、端口、用户名、密码或密钥路径）。所有远程命令仅通过标准 `ssh` 调用只读命令，不落地密码到磁盘、不写 shell 历史。
- 所有 SQL 一律只读，会话开头执行 `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;`，严禁 INSERT/UPDATE/DELETE/DDL。
- 所有 OS 操作只读（df/free/ps/iostat/sar/cat/iftop 等），严禁 rm/kill/reboot/系统参数修改等破坏性操作。

## 工作流程

### Step 0：连接数据库并采集基础信息

执行 `references/sql_queries.sql` 中「Step0 基础信息」段：实例版本、启动时间、`data_directory`、内存相关参数（max_connections/shared_buffers/work_mem/maintenance_work_mem/effective_cache_size）、`inet_server_addr()`、当前活跃会话列表、`pg_tablespace` 中的自定义表空间路径。

### Step 1：判断执行环境（本地 or 远程）

运行 `scripts/env_detect.sh`：
1. 本地执行 `hostname -I` 与 `whoami`，比对本地 IP 与 Step 0 中 `inet_server_addr()` 是否匹配；
2. 检查本地是否存在正在运行的 `postgres` 主进程（`ps aux | grep '[p]ostgres'`）。

若两个条件均满足 → 判定为「本地模式」，后续所有 OS 命令直接本地执行。
否则 → 判定为「远程模式」，向用户输出：

> 检测到当前执行环境不是数据库服务器。请提供服务器的 SSH 连接信息（主机、端口、用户名、密码或密钥路径），以便进行物理资源扫描。

收到 SSH 信息后，后续所有 `scripts/*.sh` 均通过 `ssh <user>@<host> -p <port> 'bash -s' < script.sh` 的方式在远端执行，密码类连接信息只在当次会话内存中使用，不写入文件。

### Step 2：磁盘剩余空间预警

运行 `scripts/disk_check.sh`（传入 `$PGDATA`、WAL 目录、日志目录、`/tmp`、表空间路径列表、`/`）：
- 输出 `df -h` 全量挂载点及关注目录的剩余空间/使用率。
- 对判定为告警的目录，执行 `du -ah <dir> --max-depth=3 | sort -rh | head -20` 定位大文件。

分级标准（对每个关注目录独立判定）：
- 🔴 严重：剩余 < 5% 且绝对值 < 10GB
- 🟠 警告：剩余 < 10% 或绝对值 < 50GB
- 🟡 关注：剩余 < 20% 或绝对值 < 100GB
- 🟢 正常：以上均不满足

对告警目录做溯源：
- 数据目录/表空间目录下的大文件：按 OID 反查 `pg_database`/`pg_class`（见 `references/sql_queries.sql` Step2 段），定位到具体库或表。
- WAL 目录过大：查询 `pg_replication_slots` 找未消费的复制槽，或检查归档命令是否失败（`pg_stat_archiver`）。
- 日志目录过大：建议开启/检查日志轮转配置。
- `/tmp` 过大：结合 `pg_stat_activity` 检查是否有长时间运行的排序/临时文件查询。

增长预测：结合 `pg_stat_user_tables.n_tup_ins` 增量与当前数据文件大小做粗略线性外推，估算磁盘写满剩余天数（在报告中注明这是粗略估算，非精确预测）。

### Step 3：OOM 风险预警（服务器 + PG 进程级）

运行 `scripts/memory_check.sh`：
- `free -h`
- `cat /proc/meminfo | grep -E "MemTotal|MemAvailable|SwapTotal|SwapFree|Cached|Buffers"`
- `ps aux --sort=-%mem | grep postgres | head -30`

整体内存分级：
- 🔴 严重：MemAvailable < 5% 总内存 或 Swap 使用率 > 80%
- 🟠 警告：MemAvailable < 10% 或 Swap 使用率 > 50%
- 🟡 关注：MemAvailable < 20%
- 🟢 正常

对 RSS > 500MB 或 %MEM > 10% 的 PG 进程，用其 PID 执行 `references/sql_queries.sql` Step3 段的 `pg_stat_activity` 关联查询，并按进程类型分支：
- **普通后端**：若 `pg_stat_statements` 可用，按 `queryid` 关联历史资源消耗，判断是否涉及大排序/大哈希（可能占满 work_mem），或长事务持锁导致内存堆积。
- **autovacuum worker**：查询 `pg_stat_progress_vacuum` 找正在处理的表，核对 `maintenance_work_mem` 是否设置过高。
- **WAL sender**：查询 `pg_stat_replication` 的复制延迟，判断是否因 WAL 积压导致内存升高。
- 统计高内存进程的 `application_name` 分布，判断是否某个应用连接数异常。

综合评估：列出内存消耗构成表 —— `shared_buffers`（固定）+ 连接基础开销（约 5-10MB/连接 × `max_connections`）+ 活跃查询 work_mem 理论上限 + 并发 autovacuum 的 `maintenance_work_mem` 上限，与物理内存对比，判断是否存在理论超卖。给出 `work_mem`/`max_connections`/`shared_buffers` 调整建议，或引入连接池（pgbouncer）的建议。

### Step 4：IO 设备使用率与等待预警

运行 `scripts/io_check.sh`（若 `iostat`/`sar` 不存在则报告工具缺失并跳过本项细节）：
- `iostat -x 1 3` 或 `sar -d 1 3`，采集 `%util, await, r/s, w/s, rkB/s, wkB/s, avgqu-sz`。

分级：
- 🔴 严重：%util > 95% 且 await > 50ms
- 🟠 警告：%util > 80% 或 await > 20ms（HDD）/ 5ms（SSD，需先判断磁盘类型 `cat /sys/block/<dev>/queue/rotational`）
- 🟡 关注：%util > 60%
- 🟢 正常

数据库内部关联（见 `references/sql_queries.sql` Step4 段）：
- `pg_stat_bgwriter` 中 `buffers_backend` 与 `buffers_checkpoint` 比例，判断 IO 主要来自后端查询还是检查点。
- `pg_stat_statements` 按 `shared_blks_read` 降序 TOP 10，找出磁盘读最多的 SQL，并计算缓存命中率。
- `pg_statio_user_tables`/`pg_statio_user_indexes` 找 `heap_blks_read` 最高的表/索引。
- 若 `checkpoints_req` 远大于 `checkpoints_timed`，提示 `max_wal_size` 可能偏小，建议增大。

输出 IO 消耗来源归总表（检查点/后端直读/VACUUM/WAL 写），各给根因和优化建议。

### Step 5：网络带宽使用率预警

运行 `scripts/network_check.sh`：
- 优先 `sar -n DEV 1 3`；否则读取两次 `/proc/net/dev` 采样计算速率；`ethtool <iface>` 或 `/sys/class/net/<iface>/speed` 获取网卡额定带宽。
- 可选：`iftop -t -s 3` 或 `nload -t 3` 做交叉验证。

分级（按 rx+tx 占额定带宽比例）：
- 🔴 严重：> 90%　🟠 警告：> 70%　🟡 关注：> 50%　🟢 正常

数据库内部关联（见 `references/sql_queries.sql` Step5 段）：
- 复制流量：`pg_stat_replication` 的 `write_lag`/`flush_lag`，及两次采样 `pg_current_wal_lsn()` 算出的 WAL 生成速率，估算复制占用带宽。
- 大结果集查询：`pg_stat_activity` 中 `state='active'` 且疑似返回大量行的会话，或 `pg_stat_statements` 中 `rows` 极大的查询。
- 连接风暴：短时间内新建连接数是否异常激增（尤其外部来源）。
- 非 PG 流量：`ss -tup` 排查是否有非 PG 端口的大流量，提示混合部署风险。

### Step 6：生成综合报告

按 `references/report_template.md` 的结构输出最终中文报告，要点：
- 顶部摘要：主机信息 + CPU/内存/磁盘/带宽规格 + 各级风险计数。
- 按 🔴/🟠/🟡/🟢 四个严重度分组列出所有维度的发现，每项包含：风险名称、当前值 vs 阈值、根因定位（精确到目录/进程/SQL/复制槽/应用）、可执行修复建议。
- 资源趋势预测：磁盘满剩余天数、内存安全余量、IO 高峰余量、网络带宽余量。
- 参数调整建议汇总（`shared_buffers`/`work_mem`/`max_connections`/`max_wal_size` 等）。
- 后续监控建议：OS 层与 PG 层各自该盯哪些指标、阈值多少。
- 若当前非业务高峰期执行，必须在报告顶部明确提示"当前非高峰，实际峰值可能更高"。

## 注意事项

- 全程只读：OS 命令严禁 `rm`/`kill`/`reboot`/参数热改；SQL 严禁写操作。
- 密码只走 `PGPASSWORD` 环境变量或当次会话内存中的 SSH 凭据，不写入任何文件、不打印到日志。
- 工具缺失（`iostat`/`sar`/`iftop`）时，提示用户 `yum/dnf/apt install sysstat` 或跳过对应分析，并在报告中注明该维度结论的局限性。
- 不硬编码 IP、路径、用户名，全部从实际环境探测获得。
- 判断是否处于业务高峰期时，若无法确定，默认按"非高峰期"提示风险可能被低估。
