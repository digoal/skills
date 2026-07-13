---
name: pg-log-analyzer
description: "作为 PostgreSQL DBA 专家，输入 PostgreSQL 实例的日志目录路径与需要分析的时间段（绝对时间范围或相对时间如「最近3天」、「昨晚8点到今早8点」），对该时间段内的日志文件进行深度解析，识别错误/致命错误、慢查询、锁等待与死锁、checkpoint 与后台写入、autovacuum、临时文件、连接与认证异常、复制/WAL 问题，并输出图文并茂（含时间线图与统计表格）的 Markdown 分析报告。触发条件：用户提到「分析PG日志」、「分析PostgreSQL日志」、「帮我看看数据库日志」、「日志目录」、「pg_log」、「log 目录」、「数据库日志诊断」、「这段时间数据库出了什么问题」、「帮我查一下慢查询」、「帮我看看有没有死锁」、「checkpoint是不是太频繁」、「autovacuum有没有问题」、「数据库这段时间为什么变慢」，或用户提供了一个日志目录路径 + 时间段并希望得到诊断报告。即使用户只说「帮我看看这个目录下的日志，最近有没有问题」，也应使用本 skill。"
tags: [PostgreSQL, csvlog, 日志分析]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# PostgreSQL 日志诊断专家

对 PostgreSQL 实例在指定时间段内的日志文件进行系统性解析与根因分析，产出一份可直接用于故障复盘或健康巡检的 Markdown 报告。本 skill 只读日志文件，不连接数据库、不修改任何配置。

## 前置要求

- Agent 具备读取目标日志目录的文件系统权限（无需 root，普通只读权限即可；若日志属于 postgres 用户且当前用户无权限，需提示用户 `sudo -u postgres` 或调整权限后重试）
- 基础命令行工具：`grep`、`awk`、`sed`、`zcat/zgrep`（处理压缩轮转日志）、`python3`（用于 csvlog/jsonlog 结构化解析，标准库即可，无需联网安装包）
- 不需要网络访问

## 工作流程

### Step 1: 捕获输入，缺失则询问

必需两个输入：
1. **日志目录路径**（如 `/var/lib/pgsql/data/log`、`/var/log/postgresql`）
2. **分析时间段**——支持绝对区间（`2026-07-10 14:00` 到 `2026-07-10 18:00`）或相对表达（"最近3天"、"昨晚到今早"），Agent 需先用 `date` 换算成绝对时间区间，并在报告开头写明换算结果

若用户只给了目录没给时间段，默认使用该目录下**最新日志文件覆盖的最后 24 小时**，并在报告中明确注明"未指定时间段，默认分析最近 24 小时"。

若目录不存在或无可读日志文件，直接告知用户，不要臆造分析结果。

### Step 2: 探测日志格式与时区

```bash
ls -la <log_dir> | head -50
# 判断格式：stderr 文本 / csvlog（.csv）/ jsonlog（.json）
head -5 <log_dir>/postgresql-*.log 2>/dev/null
head -5 <log_dir>/postgresql-*.csv 2>/dev/null
head -5 <log_dir>/postgresql-*.json 2>/dev/null
```

- 若能找到 `postgresql.conf` 或日志中包含 `log_line_prefix` 线索，确认时间戳格式与 `log_timezone`；找不到则以日志内时间戳自带的时区/或系统本地时区为准，并在报告"数据说明"中注明假设
- csvlog 每行是标准 CSV（含内嵌换行的字段，如 SQL 语句本身可能跨行），**禁止直接用 `grep`/`awk` 按行硬切，必须用 Python `csv` 模块解析**，否则会因内嵌逗号/换行导致字段错位
- jsonlog 每行是一个 JSON 对象，用 `python3 -c "import json"` 逐行解析，不要用正则啃 JSON
- 传统 stderr 文本格式中，一条日志事件可能横跨多行（`ERROR:` 主行 + 紧随其后的 `STATEMENT:`/`DETAIL:`/`CONTEXT:`/`HINT:` 续行），续行以空白字符缩进或紧跟在时间戳行之后但本身不带新时间戳，解析时要把这些续行归并回它所属的事件，不能拆散统计

### Step 3: 筛选时间段内的日志文件

- 一个绝对时间段可能跨越多个日志文件（含轮转、含 `.gz` 压缩文件），按文件名时间戳或 `mtime` 排序后，选出**所有与目标区间有交集**的文件，而不是只挑一个最接近的文件
- 大文件（>200MB）优先用流式命令（`zgrep`/`grep` + 管道）过滤，禁止一次性读入内存后再处理
- 对每个候选文件，先用时间戳做粗筛（取文件内第一条和最后一条日志的时间戳，判断是否与区间有交集），再精确过滤落在区间内的行

### Step 4: 分类提取与统计

对区间内的日志事件，按以下维度提取并统计，每类都要给出**次数、代表性样例（脱敏后）、Top N 排序**：

| 维度 | 关键字/模式 | 需要统计的内容 |
|------|------------|----------------|
| 致命/错误 | `PANIC`、`FATAL`、`ERROR` | 按 SQLSTATE 或错误消息模板聚类去重，列 Top 10 出现频率最高的错误 |
| 慢查询 | `duration: ... ms  statement:` / `duration: ... ms  plan:` | 耗时分布（P50/P95/最大值）、最慢 Top 10 语句（**对字面量做脱敏**，只保留 SQL 结构） |
| 锁与死锁 | `deadlock detected`、`process ... still waiting for` | 死锁次数、涉及的表/关系、锁等待最长时长 |
| 连接与认证 | `connection authorized`、`connection received`、`password authentication failed`、`too many connections`、`terminating connection` | 认证失败次数与来源 IP、连接数峰值时段、异常断连次数 |
| Checkpoint/后台写入 | `checkpoint starting`、`checkpoint complete` | 触发原因分布（time/xlog/force）、平均耗时、写入 buffer 数、检查是否比 `checkpoint_timeout` 更频繁触发（提示可能存在 IO 压力或参数配置问题） |
| Autovacuum/Autoanalyze | `automatic vacuum of table`、`automatic analyze of table` | 涉及表清单、耗时 Top、dead tuples 数量趋势，判断是否有表长期未被有效清理 |
| 临时文件 | `temporary file:` | 出现次数、总大小，提示可能 `work_mem` 不足 |
| 复制/WAL | `streaming replication`、`could not receive data from WAL stream`、`archive command failed` | 复制中断次数、WAL 归档失败次数 |
| 其他告警 | `WARNING`、`could not`、`skipping` | 归类展示，避免遗漏未预期的问题类型 |

若某一类在该时间段内完全没有记录，在报告中明确写"未发现"，不要跳过不提，也不要编造。

### Step 5: 关联分析（时间维度交叉）

把上述所有关键事件按时间排序，构建一条时间线，重点检查以下关联模式（有则指出，没有就不要牵强附会）：

- 慢查询集中爆发的时间段是否与 checkpoint、autovacuum 的执行窗口重叠
- 连接错误/认证失败暴增是否伴随 `too many connections` 或应用侧重连风暴
- 死锁频发是否集中在特定表或特定时段（如批量任务窗口）
- 临时文件暴增是否与某类慢查询的语句结构一致（提示同一 SQL 反复触发外部排序/哈希）

对每一条关联结论，给出**支持证据**（引用具体时间点和事件计数），并明确这是"相关性观察"而非确诊，附上"如何进一步验证"的建议（如开启 `auto_explain`、检查具体表的统计信息等）。

### Step 6: 生成并保存报告

用 Markdown 输出，保存到当前项目 `markdown/` 目录（不存在则创建），文件名格式：`pg-log-analysis_{开始时间}_{结束时间}.md`（时间用 `YYYYMMDD-HHMM`）。报告需包含时间线图（Mermaid `timeline` 或简单的 ASCII 时间轴均可）和统计表格，让 DBA 一眼看出这段时间数据库经历了什么。

## 输出格式

```markdown
# PostgreSQL 日志分析报告

## 数据说明
- 实例日志目录：...
- 分析时间段：... 至 ...（如为默认/推算得出的时间段需注明）
- 涉及日志文件：文件名列表
- 日志格式：stderr / csvlog / jsonlog
- 时区假设：...

## 健康度摘要
一句话结论 + 3-5 条关键发现（按严重程度排序）

## 关键发现 Top 5
1. ...（含证据：次数、时间点）

## 时间线
（Mermaid timeline 或时间轴表格，标出致命错误/死锁/连接风暴等关键节点）

## 分类明细
### 错误与致命错误
表格：错误类型 | 次数 | 首次出现 | 最近一次 | 代表样例（脱敏）

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

### 复制 / WAL
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
| stderr 文本格式的多行日志（ERROR + STATEMENT/DETAIL）被当成独立行统计，导致重复计数 | 解析时先做"事件归并"，把续行拼回主事件后再统计 |
| 慢查询语句里可能包含手机号、身份证、密码等敏感字面量 | 报告中一律用占位符替换字面量（如 `$1`、`'***'`），只保留 SQL 结构 |
| 大文件一次性读入内存导致 OOM 或极慢 | 用 `grep`/`zgrep` 流式过滤后再精细处理，避免一次性 `read()` 整个文件 |
| 时间戳时区与系统本地时区不一致，导致筛选区间偏移 | 优先确认 `log_timezone`，找不到时明确注明假设的时区，不要默默假定 UTC |
| checkpoint/autovacuum 日志默认可能未开启（`log_checkpoints`/`log_autovacuum_min_duration` 未设置） | 该类目日志缺失时，提示用户检查相关参数是否开启，而不是直接判定"无问题" |
| 把相关性当因果，给出过度确定的根因结论 | 所有关联分析必须标注为"观察到的相关性"，并给出证据和进一步验证方法 |

## 注意事项

- 本 skill 仅读取日志文件，不连接数据库、不执行任何 SQL、不修改任何配置或系统文件
- 日志中的字面量数据（用户输入、SQL 参数）在报告中一律脱敏，不得原样透出
- 若日志目录权限不足，提示用户调整权限或使用有权限的账户重试，不要尝试提权
- 若关键日志类别（如慢查询、checkpoint）因参数未开启而缺失数据，必须在报告中明确说明"数据不可得"，不得凭经验编造结论
- 报告中的所有优化建议需说明适用前提（如"若确认瓶颈在 IO，可考虑..."），不做无条件的参数修改建议
