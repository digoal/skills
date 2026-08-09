---
name: kingbase-log-analyzer
description: "作为 KingbaseES（金仓）DBA 专家，输入金仓实例的日志目录路径与需要分析的时间段（绝对时间范围或相对时间如「最近3天」、「昨晚8点到今早8点」），对该时间段内的日志文件进行深度解析，识别错误/致命错误、慢查询、锁等待与死锁、checkpoint 与后台写入、autovacuum、临时文件、连接与认证异常、复制/WAL 问题、崩溃恢复以及金仓特有的审计/安全日志（sysaudit、sysmac、sys_hm），并输出图文并茂（含时间线图与统计表格）的 Markdown 分析报告。触发条件：用户提到「分析金仓日志」、「分析KingbaseES日志」、「分析KES日志」、「帮我看看金仓数据库日志」、「日志目录」、「sys_log」、「金仓log 目录」、「数据库日志诊断」、「这段时间金仓出了什么问题」、「帮我查一下慢查询」、「帮我看看有没有死锁」、「checkpoint是不是太频繁」、「autovacuum有没有问题」、「金仓这段时间为什么变慢」，或用户提供了一个日志目录路径 + 时间段并希望得到诊断报告。即使用户只说「帮我看看这个目录下的日志，最近有没有问题」，也应使用本 skill。"
tags: [KingbaseES, 金仓, sys_log, 日志分析, csvlog]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# KingbaseES 日志诊断专家

对 KingbaseES（金仓）实例在指定时间段内的日志文件进行系统性解析与根因分析，产出一份可直接用于故障复盘或健康巡检的 Markdown 报告。本 skill 以只读日志文件为主；可选地只读连接数据库来确认日志相关参数与时区假设，但不修改任何配置。

> **KingbaseES 适配要点**：金仓默认采用 **PG 兼容模式**，日志体系与 PostgreSQL 高度一致（`log_*` 系列参数、stderr/csvlog 输出、时间戳格式），但存在若干金仓特有差异（`sys_log` 目录、`sys_hba.conf`、日志文件名 `kingbase-*`、审计日志 `sysaudit`、安全策略日志 `sysmac`、健康监控 `sys_hm`、崩溃自动恢复消息等），已在 Step 2 / 分类维度 / Pitfalls 中逐条说明。金仓实测默认参数与常见日志消息模式见 `references/kb-log-format.md`。

## 前置要求

- Agent 具备读取目标日志目录的文件系统权限（无需 root，普通只读权限即可；若日志属于 kingbase 用户且当前用户无权限，需提示用户 `sudo -u kingbase` 或调整权限后重试）
- 基础命令行工具：`grep`、`awk`、`sed`、`zcat/zgrep`（处理压缩轮转日志）、`python3`（用于 csvlog 结构化解析，标准库即可，无需联网安装包）
- **可选**：`ksql` 或 `psql` 客户端（采集日志相关配置参数），或 `psycopg2`（等价 Python 版，见 `scripts/collect_log_settings.py`）
- 不需要网络访问（官方文档 URL 仅供核对术语，不构成依赖）

## 连接约定（仅当需要连库确认参数/时区时）

按优先级解析：

1. **用户明确提供的连接参数**（host/port/user/password/dbname，或连接串）；
2. **环境变量** `PGHOST` `PGPORT` `PGUSER` `PGPASSWORD`，库名变量**同时兼容** `PGDBNAME`（用户指定）与 `PGDATABASE`（PG 惯例）——即使 KingbaseES 手册把这些变量写作 `KINGBASEHOST`/`KINGBASE_HOST` 等，本 skill **一律沿用 PG 风格环境变量**；
3. **缺省值**：`PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGPASSWORD=123456 PGDATABASE=kingbase`（金仓默认库名是 `kingbase` 而非 `postgres`，注意 Pitfall）。

连接方式二选一，结果等价：
- **psql/ksql shell**：`scripts/collect_log_settings.sql`
- **Python SDK**：`scripts/collect_log_settings.py`（依赖 `psycopg2`，`pip install psycopg2-binary`）

## 工作流程

### Step 1: 捕获输入，缺失则询问

必需两个输入：
1. **日志目录路径**——金仓默认日志目录是 `<data_directory>/sys_log/`（相对路径，`SHOW log_directory` 可确认，如 `/home/kingbase/userdata/data/sys_log` 或本机挂载路径）；用户给的是绝对路径时直接使用
2. **分析时间段**——支持绝对区间（`2026-07-10 14:00` 到 `2026-07-10 18:00`）或相对表达（"最近3天"、"昨晚到今早"），Agent 需先用 `date` 换算成绝对时间区间，并在报告开头写明换算结果

若用户只给了目录没给时间段，默认使用该目录下**最新日志文件覆盖的最后 24 小时**，并在报告中明确注明"未指定时间段，默认分析最近 24 小时"。

若目录不存在或无可读日志文件，直接告知用户，不要臆造分析结果。

### Step 2: 探测日志格式与时区

```bash
ls -la <log_dir> | head -50
# 判断格式：stderr 文本 / csvlog（.csv）
head -5 <log_dir>/kingbase-*.log 2>/dev/null
head -5 <log_dir>/kingbase-*.csv 2>/dev/null
```

- 金仓默认（PG 兼容模式）`log_destination = stderr`，`logging_collector = on`，`log_directory = sys_log`，`log_filename = kingbase-%Y-%m-%d_%H%M%S.log`，`log_line_prefix = %m [%p]`（即 `2026-08-09 09:00:45.981 UTC [92] LOG:  ...`）
- 若用户提供了连接信息，运行 `scripts/collect_log_settings.sql` 或 `.py` 采集 `log_destination`、`log_filename`、`log_line_prefix`、`log_timezone`、`log_min_duration_statement`、`log_checkpoints` 等参数，用实测值替代假设；无法连库时则以日志内时间戳自带时区/系统本地时区为准，并在报告"数据说明"中注明假设
- csvlog 每行是标准 CSV（含内嵌换行的字段，如 SQL 语句本身可能跨行），**禁止直接用 `grep`/`awk` 按行硬切，必须用 Python `csv` 模块解析**，否则会因内嵌逗号/换行导致字段错位。直接使用 `scripts/parse_csvlog.py`（自动读表头列名、支持 .csv/.csv.gz、时间段过滤、分类统计与脱敏）即可：`python3 scripts/parse_csvlog.py <日志目录> --since "..." --until "..."`；若实例尚未开启 csvlog，用 `scripts/enable_csvlog.sql`（psql/ksql）或 `scripts/enable_csvlog.py --enable`（Python）开启（需超级用户，`stderr,csvlog` 并存，reload 即生效，可随时回滚）
- 传统 stderr 文本格式中，一条日志事件可能横跨多行（`ERROR:` 主行 + 紧随其后的 `STATEMENT:`/`DETAIL:`/`CONTEXT:`/`HINT:` 续行，续行与主行**同时间戳同 PID**），解析时要把这些续行归并回它所属的事件，不能拆散统计

### Step 3: 筛选时间段内的日志文件

- 一个绝对时间段可能跨越多个日志文件（金仓按 `log_rotation_age`(默认1440分钟)/`log_rotation_size`(默认10MB) 轮转，含 `.gz` 压缩文件），按文件名时间戳或 `mtime` 排序后，选出**所有与目标区间有交集**的文件，而不是只挑一个最接近的文件
- 大文件（>200MB）优先用流式命令（`zgrep`/`grep` + 管道）过滤，禁止一次性读入内存后再处理
- 对每个候选文件，先用时间戳做粗筛（取文件内第一条和最后一条日志的时间戳，判断是否与区间有交集），再精确过滤落在区间内的行

### Step 4: 分类提取与统计

对区间内的日志事件，按以下维度提取并统计，每类都要给出**次数、代表性样例（脱敏后）、Top N 排序**：

| 维度 | 关键字/模式 | 需要统计的内容 |
|------|------------|----------------|
| 致命/错误 | `PANIC`、`FATAL`、`ERROR` | 按 SQLSTATE 或错误消息模板聚类去重，列 Top 10 出现频率最高的错误 |
| 崩溃/恢复（金仓常见） | `database system was interrupted`、`automatic recovery in progress`、`redo starts at`、`database system is ready to accept connections` | 崩溃次数、崩溃时刻、恢复耗时、redo 段数；区分"正常关闭"(`was shut down`) 与"异常中断"(`was interrupted`，可能被 kill/断电/主机重启) |
| 慢查询 | `duration: ... ms  statement:` / `duration: ... ms  plan:` | 耗时分布（P50/P95/最大值）、最慢 Top 10 语句（**对字面量做脱敏**，只保留 SQL 结构） |
| 锁与死锁 | `deadlock detected`、`process ... still waiting for` | 死锁次数、涉及的表/关系、锁等待最长时长 |
| 连接与认证 | `connection authorized`、`connection received`、`password authentication failed`、`too many connections`、`terminating connection` | 认证失败次数与来源 IP、连接数峰值时段、异常断连次数 |
| Checkpoint/后台写入 | `checkpoint starting`、`checkpoint complete` | 触发原因分布、平均耗时、写入 buffer 数、检查是否比 `checkpoint_timeout` 更频繁触发 |
| Autovacuum/Autoanalyze | `automatic vacuum of table`、`automatic analyze of table`、`to prevent wraparound` | 涉及表清单、耗时 Top、dead tuples 数量趋势，判断是否有表长期未被有效清理 |
| 临时文件 | `temporary file:` | 出现次数、总大小，提示可能 `work_mem` 不足 |
| 复制/WAL/归档 | `streaming replication`、`could not receive data from WAL stream`、`archive command failed`、`config the real archive_command string` | 复制中断次数、WAL 归档失败次数（`config the real archive_command string as soon as possible` 是金仓特有提示，表示 archive_command 尚未配置真实值） |
| 配置变更 | `ALTER SYSTEM`、`received SIGHUP, reloading configuration files`、`parameter ... changed to` | 谁在何时改了什么参数（如金仓日志中 `attention:superuser kingbase is modifying ... by ALTER SYSTEM SET statement`），判断是否与异常窗口相关 |
| 金仓特有：审计/安全 | `sysaudit`、`sysmac`、`sys_hm`、`security` | 审计策略告警、MAC 策略拒绝、健康监控告警（如开启时） |
| 其他告警 | `WARNING`、`could not`、`skipping` | 归类展示，避免遗漏未预期的问题类型 |

若某一类在该时间段内完全没有记录，在报告中明确写"未发现"，不要跳过不提，也不要编造。

### Step 5: 关联分析（时间维度交叉）

把上述所有关键事件按时间排序，构建一条时间线，重点检查以下关联模式（有则指出，没有就不要牵强附会）：

- 慢查询集中爆发的时间段是否与 checkpoint、autovacuum 的执行窗口重叠
- 连接错误/认证失败暴增是否伴随 `too many connections` 或应用侧重连风暴
- 死锁频发是否集中在特定表或特定时段（如批量任务窗口）
- 临时文件暴增是否与某类慢查询的语句结构一致（提示同一 SQL 反复触发外部排序/哈希）
- **金仓特有**：崩溃恢复（`was interrupted`）后是否紧接认证失败风暴/连接堆积（应用侧重连）；`ALTER SYSTEM` 或 `pg_reload_conf` 之后是否出现计划/行为变化

对每一条关联结论，给出**支持证据**（引用具体时间点和事件计数），并明确这是"相关性观察"而非确诊，附上"如何进一步验证"的建议（如开启 `auto_explain`、检查具体表的统计信息等）。

### Step 6: 生成并保存报告

用 Markdown 输出，保存到当前项目 `markdown/` 目录（不存在则创建），文件名格式：`kingbase-log-analysis_{开始时间}_{结束时间}.md`（时间用 `YYYYMMDD-HHMM`）。报告需包含时间线图（Mermaid `timeline` 或简单的 ASCII 时间轴均可）和统计表格，让 DBA 一眼看出这段时间数据库经历了什么。

## 输出格式

```markdown
# KingbaseES 日志分析报告

## 数据说明
- 实例日志目录：...
- 分析时间段：... 至 ...（如为默认/推算得出的时间段需注明）
- 涉及日志文件：文件名列表
- 日志格式：stderr / csvlog
- 时区假设：...（连库采集到的 log_timezone 或推断值）

## 健康度摘要
一句话结论 + 3-5 条关键发现（按严重程度排序）

## 关键发现 Top 5
1. ...（含证据：次数、时间点）

## 时间线
（Mermaid timeline 或时间轴表格，标出致命错误/崩溃恢复/死锁/连接风暴等关键节点）

## 分类明细
### 错误与致命错误
表格：错误类型 | 次数 | 首次出现 | 最近一次 | 代表样例（脱敏）

### 崩溃与恢复
表格：崩溃时刻 | 恢复耗时 | redo 段数 | 是否正常关闭

### 慢查询
表格：语句结构（脱敏） | 出现次数 | 平均耗时 | 最大耗时

### 锁与死锁
...

### Checkpoint / 后台写入
...

### Autovacuum / Autoanalyze
...

### 临时文件
...

### 连接与认证
...

### 复制 / WAL / 归档
...

### 配置变更
...

### 审计 / 安全日志（金仓特有）
...

## 关联分析与根因假设
每条假设附证据与验证建议

## 优化建议
按优先级（P0/P1/P2）列出可执行的参数调整或运维动作，每条建议说明"解决什么问题"

## 附录：原始日志片段引用
关键事件的原始行（脱敏后），供人工复核
```

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|------|----------|
| 日志轮转导致时间段横跨多个文件，只看最新文件会漏掉信息 | 先按文件时间范围筛选出所有相交文件再处理 |
| csvlog 内嵌逗号/换行用 grep/awk 按行切割会导致字段错位 | 必须用 Python csv 模块或专用解析器读取 |
| stderr 文本格式的多行日志（ERROR + STATEMENT/DETAIL）被当成独立行统计，导致重复计数 | 解析时先做"事件归并"（同时间戳同 PID 的续行拼回主事件）后再统计 |
| 慢查询语句里可能包含手机号、身份证、密码等敏感字面量 | 报告中一律用占位符替换字面量（如 `$1`、`'***'`），只保留 SQL 结构 |
| 大文件一次性读入内存导致 OOM 或极慢 | 用 `grep`/`zgrep` 流式过滤后再精细处理，避免一次性 `read()` 整个文件 |
| 时间戳时区与系统本地时区不一致，导致筛选区间偏移 | 优先确认 `log_timezone`（金仓实测常见 UTC），找不到时明确注明假设的时区，不要默默假定 UTC |
| **金仓特有**：`log_min_duration_statement = -1`（默认**不记慢 SQL**）、`log_checkpoints = off`、`log_autovacuum_min_duration = -1` | 慢查询/checkpoint/autovacuum 类目日志缺失时，提示用户检查相关参数是否开启，而不是直接判定"无问题"（这是金仓默认比 PG 更保守的一处） |
| **金仓特有**：客户端默认连 `postgres` 库报 `FATAL: database "postgres" does not exist` | 金仓默认库名是 `kingbase`（或安装时指定的库），报告应点明这是客户端习惯性问题而非数据库故障 |
| **金仓特有**：认证失败消息里出现 `Connection matched sys_hba.conf line 63` | 金仓的 host 认证配置文件叫 `sys_hba.conf`（不是 `pg_hba.conf`），引用时注意名称 |
| **金仓特有**：`2pc are not enabled` / `the prepared transaction ... does not exist` | 金仓默认未开启 2PC（`max_prepared_transactions` 相关），涉及 PREPARE TRANSACTION 的运维/SQL 需要先确认参数 |
| **金仓特有**：`sys_stat_statements` 同名对象在不同 schema（`public` 扩展视图 vs `sys_catalog` 内部对象）列结构可能不同 | 查询前用 `\dn`/`information_schema.columns` 确认目标对象，报 `column ... does not exist` 时先检查 search_path |
| **金仓特有**：`ALTER SYSTEM` 触发 `attention:superuser kingbase is modifying ...` 日志 | 这是金仓对超级用户改参数的审计提示，属正常行为，但应纳入"配置变更"维度关联到异常窗口 |
| **金仓特有**：`config the real archive_command string as soon as possible to archive WAL files` | 金仓提示 archive_command 尚未配置真实值（可能默认占位），报告应提醒确认归档配置 |
| 把相关性当因果，给出过度确定的根因结论 | 所有关联分析必须标注为"观察到的相关性"，并给出证据和进一步验证方法 |

## 注意事项

- 本 skill 仅读取日志文件；如需连库（只读）确认参数，只执行 SELECT/SHOW，不执行任何 SQL 写操作、不修改任何配置或系统文件
- 日志中的字面量数据（用户输入、SQL 参数）在报告中一律脱敏，不得原样透出
- 若日志目录权限不足，提示用户调整权限或使用有权限的账户重试，不要尝试提权
- 若关键日志类别（如慢查询、checkpoint）因参数未开启而缺失数据，必须在报告中明确说明"数据不可得"，不得凭经验编造结论
- 报告中的所有优化建议需说明适用前提（如"若确认瓶颈在 IO，可考虑..."），不做无条件的参数修改建议
- 连接信息解析：用户提供 > 环境变量（PG 风格，即使金仓手册写作 KINGBASE*；库名兼容 `PGDBNAME`/`PGDATABASE`）> 缺省值 `127.0.0.1:5432/kingbase/kingbase/123456`

## 脚本与参考

- `scripts/collect_log_settings.sql` — psql/ksql 版：只读采集日志相关配置（格式、轮转、内容开关、时区）
- `scripts/collect_log_settings.py` — Python SDK（psycopg2）版：与 .sql 等价
- `scripts/parse_csvlog.py` — csvlog 结构化日志解析器（Python 标准库 csv/gzip，只读）：动态读表头、支持 .csv/.csv.gz、`--since/--until/--json`，按 skill Step 4 维度分类统计并脱敏
- `scripts/enable_csvlog.sql` — psql/ksql 版：开启 csvlog（`stderr,csvlog` 并存 + reload，需超级用户，含回滚方法）
- `scripts/enable_csvlog.py` — Python SDK 版：`--check`（只读查看，默认）/ `--enable` / `--revert`
- `references/kb-log-format.md` — 金仓日志格式细节、实测默认参数、特有消息模式、csvlog 字段说明、官方文档链接
- 官方文档：[错误报告和日志（运行时配置-日志）](https://docs.kingbase.com.cn/cn/KES-V9R1C10/administration/Config_Mgmt/runtime-config-logging)（说明：docs.kingbase.com.cn 为 JS 渲染站点，`curl` 只能拿到导航壳，正文需用浏览器渲染或直接以本 skill 的实测/经验内容为准）
