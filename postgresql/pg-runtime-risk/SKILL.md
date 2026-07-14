---
name: pg-runtime-risk
description: "PostgreSQL 高可用架构与运行时风险诊断专家技能。给定实例连接信息（主机、端口、用户名、密码），对实例进行只读全面运行时风险扫描，覆盖事务回卷、序列回卷、冻结风暴、复制延迟（物理/逻辑槽）、WAL 异常与堆积、连接数耗尽、集群单点故障、大对象泄漏等维度，输出按严重程度分级（🔴严重/🟠警告/🟡关注/🟢正常）的中文预警报告。触发场景包括但不限于：\"帮我评估一下这个 PG 实例的运行时风险\"、\"检查一下事务回卷/XID 回卷风险\"、\"序列要用完了吗\"、\"冻结风暴\"、\"复制延迟检查\"、\"逻辑复制槽是不是堆积了\"、\"WAL 堆积/归档失败排查\"、\"连接数是不是要满了\"、\"too many connections\"、\"max_connections 告警\"、\"连接池是不是耗尽了\"、\"这套集群有没有单点故障\"、\"大对象是不是泄漏了\"、\"pg_largeobject 太大了\"、\"数据库年龄检查\"、\"autovacuum 是否正常\"。即使用户只说\"帮我看看这个库有没有风险\"或提供了连接信息但未指明具体维度，也应触发本技能进行全面扫描。"
tags: [PostgreSQL, 运行时潜在风险分析, 连接数耗尽, 事务回卷, 序列回卷, 冻结风暴, 复制延迟, 逻辑复制槽推进延迟, 逻辑复制槽未激活, 归档日志异常, WAL堆积, 大对象泄露]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# PostgreSQL 运行时风险诊断（pg-runtime-risk）

对一个 PostgreSQL 实例做全维度只读运行时风险扫描：事务回卷、序列回卷、冻结风暴、
复制延迟、WAL 异常、连接数耗尽、集群单点故障、大对象泄漏，输出分级中文预警报告。

## 前置要求

- 环境需安装 PostgreSQL 客户端 `psql`，且版本 ≥ 10（`psql --version` 验证）。
  第二部分序列检查依赖 `\gset` + `\if :{?var}` 条件判断语法，该语法在 psql 10 才引入，
  低版本客户端会报语法错误，需提示用户升级 psql 客户端（与目标数据库服务端版本无关）。
- 连接账号建议具备 `pg_monitor` 角色或超级用户权限（`pg_ls_waldir()` 等函数需要更高权限，
  权限不足时会自动优雅降级并在报告中注明"因权限不足跳过"，不会导致整体扫描失败）。
- **密码仅通过 `PGPASSWORD` 环境变量传递**，不接受用户以明文形式粘贴到会话记录中长期保留，
  不写入任何脚本文件、不打印到日志、不落盘。
- 本技能全程只读：所有查询均包裹在 `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`
  的事务中执行，不会对目标实例产生任何写操作。

## 工作流程

### Step 0：获取连接信息

向用户确认：主机（host）、端口（port，默认 5432）、用户名（user）、密码、
目标数据库（database，默认 postgres，若实例有多个业务库，事务回卷等检查需遍历所有库）。

密码通过环境变量传递，例如：

```bash
export PGPASSWORD='xxxxxx'
```

不要将密码写入任何会保存的文件或命令历史。

### Step 1：执行只读扫描

调用 `scripts/run_scan.sh`：

```bash
PGPASSWORD='xxxxxx' bash scripts/run_scan.sh -h <host> -p <port> -U <user> -d <database> -o <output_dir>
```

该脚本会自动完成：

- 第零部分：版本、启动时间、运行角色、关键参数、复制槽、WAL 接收状态
- 第一部分：数据库/表级 XID 年龄、autovacuum freeze 进度
- 第二部分：所有非循环序列的剩余调用次数与风险等级（通过 `\gset` + 动态 SQL
  在只读事务内一次性计算，无需 Agent 再做算术）
- 第三部分：冻结风暴分桶统计
- 第四部分：物理复制延迟、逻辑复制槽状态
- 第五部分：归档状态、WAL 目录堆积统计
- 第六部分：连接数占用总览、按数据库/用户拆分、长时间 idle in transaction 明细
- 第八部分：大对象总量与疑似引用列

脚本对每个检查项都做了权限/版本容错：若某项因权限不足或函数不存在而失败，
会在对应 `<file>.csv.err` 中留痕，并在标准错误输出提示，视为正常的优雅降级，
**不代表整体扫描失败**，继续处理其余项即可。

### Step 2：解读结果并分级

逐个读取 `<output_dir>/` 下的 CSV 文件，对照 `references/thresholds.md` 中
每个维度的分级阈值表进行判定。重点：

1. **事务回卷**：先看 `01_database_xid_age.csv` 找出年龄最高的库，
   再结合 `01_table_xid_age_top20.csv` 定位阻碍该库年龄下降的具体表；
   若已进入警告区间，检查 `01_vacuum_progress.csv` 判断当前是否有 autovacuum
   worker 正在处理、能否在回卷前完成。
2. **序列回卷**：`02_sequence_risk.csv` 已直接给出 `risk_level` 列，
   按严重程度倒序整理；对 `data_type` 为 `integer`/`smallint` 且风险等级较高的，
   建议改为 `bigserial`（可用 `references/manual_checks.sql` 中的 A4 查询二次确认）。
3. **冻结风暴**：`03_freeze_storm_buckets.csv` 中若年龄较高的分桶集中了
   过半的表数量或表体积，判定为高风险，并结合 `00_key_settings.csv` 中
   `autovacuum_freeze_max_age` 给出参数调整建议。
4. **复制延迟**：`04_physical_replication.csv` 按物理延迟阈值判定；
   `04_logical_slots.csv` 需特别关注 `active=false` 的槽（WAL 无限堆积风险）
   以及有槽无消费进程的情况。
5. **WAL 异常**：先用 `00_key_settings.csv` 判断 `archive_mode`/`archive_command`
   是否为有效配置，排除主动关闭归档的情况后再用 `05_archiver_status.csv`
   判定归档失败/滞后；`05_wal_dir.csv` 的堆积量按 thresholds.md 中的
   根因排查顺序（复制延迟 → 槽推进延迟 → 槽未激活 → 槽未消费 → 归档失败 → 未知）
   逐层归因，输出根因分析表。
6. **连接数耗尽**：`06_connection_saturation.csv` 的 `usage_pct` 是主判据；
   若 `idle_in_tx_count`（含 aborted）占比偏高，即使 usage_pct 未达告警线也需单独标注，
   并提示这类长事务会同时加剧"事务回卷"与"冻结风暴"风险（阻塞 autovacuum 推进）；
   结合 `06_connection_by_database.csv` / `06_connection_by_user.csv` 定位是哪个库/账号
   占用了大部分连接；`06_long_idle_in_transaction.csv` 中 `idle_duration` 过长的记录需
   在报告中列出具体 pid，并在 (B) 部分给出 `pg_terminate_backend` 建议命令（需用户确认）。
7. **集群单点故障**：本项无法仅靠单节点只读查询完成，见 Step 3。
8. **大对象泄漏**：`08_large_object_summary.csv` 按体积判级；
   `08_lo_reference_columns.csv` 列出候选引用列供人工核对，
   不给出任何自动清理结论。

### Step 3：集群单点故障 —— 主动向用户提问

在处理到第七部分时，必须暂停并向用户提问，因为单点风险评估依赖集群全局拓扑信息，
仅凭当前主库无法完整判断：

> 集群单点故障风险评估需要了解整个集群的拓扑结构。请提供：
> 1. 集群架构描述（如：1 主 2 备 + 1 个异步备库，是否使用 Patroni/Repmgr 等高可用方案）
> 2. 是否使用了连接池（如 PgBouncer），其部署是否为单节点
> 3. 是否使用了 VIP/负载均衡器（如 HAProxy/Keepalived），其部署是否为单节点
> 4. 最近一次有效备份的时间与类型（全量/增量）
>
> 如无法提供全部信息，将仅基于当前主库的复制拓扑（`04_physical_replication.csv`、
> `references/manual_checks.sql` 中 A1/A2/A3）做有限的单点风险评估。

拿到回答后，结合 `references/manual_checks.sql` 中的 A1（同步备库数量）、
A2（`synchronous_standby_names` 配置）、A3（`synchronous_commit` 取值）
按 `references/thresholds.md` 第 7 节的判定表输出单点故障风险矩阵
（组件 / 当前状态 / 是否为单点 / 故障影响 / 风险等级）。

### Step 4：生成最终报告

按 `references/report_template.md` 的结构输出完整中文报告，包含：
风险总览仪表盘、🔴/🟠/🟡 分级明细（含具体修复建议与预估处理时间）、
🟢 检查通过项、十维度风险雷达图（文字版进度条）、后续巡检与监控建议。

## 输出格式

严格遵循 `references/report_template.md`。修复建议中涉及破坏性操作
（删除复制槽、清理大对象、手动 VACUUM FREEZE、修改 `autovacuum_freeze_max_age` 等）
一律使用 `references/manual_checks.sql` 中 (B) 部分的模板，明确标注
"仅供参考，执行前请与用户二次确认"，**不得自动执行**。

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|---|---|
| `pg_ls_waldir()` 报权限不足 | 属预期内降级：在报告中注明"需 pg_monitor 角色或超级用户权限，本次跳过 WAL 目录堆积检查"，其余检查照常输出 |
| 序列数量很多导致动态 SQL 结果集很大 | `run_scan.sh` 已在 SQL 层完成分级计算，Agent 只需按 `risk_level` 排序摘取 🔴/🟠 项展示，避免把全部序列都塞进最终报告 |
| 多数据库实例，事务回卷需遍历所有库 | `01_database_xid_age.csv` 已按 `pg_database` 全库输出；若需要对非当前连接库做表级年龄分析（`01_table_xid_age_top20.csv`），需针对该库重新指定 `-d <database>` 执行一次 `run_scan.sh`，因为表级目录信息只能在连接到目标库后查询 |
| 密码误粘贴进对话记录 | 提醒用户后续修改该账号密码；本技能本身不会将密码写入任何持久化文件 |
| 用户要求直接执行破坏性修复命令 | 展示 (B) 类模板并明确询问"是否确认执行"，得到明确肯定答复后才可代为执行，且执行前建议用户自行备份 |
| 逻辑复制槽 `active=false` 但用户表示是刻意保留 | 不要自动建议删除，只做风险提示，是否清理完全由用户决定 |
| 连接数 usage_pct 很高，但大量是 PgBouncer/连接池的常驻连接 | 先确认是否使用了外部连接池；数据库侧看到的是池到库的连接数，不等于应用侧真实并发，报告中需注明口径，避免误判为"应用连接暴涨" |
| 想直接 `pg_terminate_backend` 杀掉长 idle-in-transaction 连接 | 属于破坏性操作，只能在 (B) 部分给出建议命令，需用户明确确认具体 pid 后才可执行，且要提醒该连接可能持有未提交事务，终止会导致其回滚 |

## 注意事项

- 全程只读：使用 `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` 包裹所有查询。
- 凭据只通过 `PGPASSWORD` 环境变量传递，不落盘、不写日志。
- 涉及删除复制槽、清理大对象、修改系统参数等破坏性操作，只以"建议命令"形式给出，
  必须经用户二次确认后才能执行，且执行前建议做好备份。
- 集群单点故障评估依赖用户提供的拓扑信息，缺失信息时明确告知"本次为有限评估"。
- 输出语言统一为中文。
