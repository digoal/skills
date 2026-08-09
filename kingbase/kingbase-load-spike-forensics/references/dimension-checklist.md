# 六维度红旗信号速查表（KingbaseES）

供 SKILL.md 工作流程执行过程中随手核对，避免遗漏关键信号。每一行都是"看到这个现象 → 优先怀疑什么"的经验映射，最终结论仍需按 SKILL.md Step 7 的证据链方法核实，不可仅凭单一信号下结论。

> **KingbaseES 适配**：本表与 PG 版本大体一致；KB-extra 一节给出金仓独有视图（`sys_stat_sql`、`sys_stat_sysmetric_history` 等）能识别的额外红旗信号。

## 数据库日志维度

| 信号 | 优先怀疑 |
|---|---|
| `checkpoints are occurring too frequently` | `max_wal_size` 偏小 / 写入量突增 |
| `automatic vacuum ... to prevent wraparound` | 事务 ID 回卷紧急清理，长期占用 IO，需检查是否有长事务阻塞了 vacuum 推进 |
| `still waiting for ... lock` / `deadlock detected` | 锁竞争，需要 Step2 的阻塞链查询定位源头会话 |
| `temporary file: ... size` 大量出现 | `work_mem` 不足，排序/哈希落盘放大 IO |
| `could not fork new process` / `too many connections` | 连接数触顶或系统进程数/内存耗尽 |
| `terminating connection because of crash of another server process` | 有子进程异常终止（常见于 OOM），触发全库重连风暴 |
| 同一 SQL 的 `auto_explain` 计划与历史计划不同 | 计划回归，通常源于统计信息过期或参数嗅探 |
| **KB 特有**：`log_min_duration_statement = -1` 且无任何慢 SQL 日志 | 慢查询日志被关闭，窗口内慢 SQL 证据缺口，要求 DBA 立即打开 |
| **KB 特有**：`KshMain` 写入 AWR 仓库失败的 ERROR | `sys_kwr` 扩展异常或磁盘满，DBA 无法回溯历史 |
| **KB 特有**：`LogicalLauncherMain` 退出码非零 | 逻辑复制 launcher 异常，会导致逻辑订阅堆积、WAL 无法回收 |

## 数据库统计视图维度（PG 兼容）

| 信号 | 优先怀疑 |
|---|---|
| `wait_event_type = 'Lock'` 大量堆积 | 锁竞争是当前主要瓶颈 |
| `wait_event_type = 'IO'`（如 `DataFileRead`）大量堆积 | 存储层瓶颈，转向 Step5 |
| `wait_event_type = 'Client'` 大量堆积 | 应用/网络侧慢，数据库本身可能是"陪跑" |
| `hit_ratio`（`pg_stat_database`）骤降 | 缓存命中下降，可能是大表全扫/`shared_buffers` 不足 |
| `temp_files`/`temp_bytes` 骤增 | 同上，`work_mem` 不足 |
| `checkpoints_req` 占比远高于 `checkpoints_timed` | 写入压力大，被动触发检查点 |
| `replay_lag` 突增（从库） | 从库资源跟不上或主库产生大事务/大量 WAL |
| `n_dead_tup` 远超 `n_live_tup` 且 `last_autovacuum` 很久以前 | 表膨胀严重，autovacuum 可能被长事务卡住 |

## 数据库统计视图维度（KB-extra，金仓独有）

| 信号 | 优先怀疑 |
|---|---|
| `sys_catalog.sys_stat_sql` 中 `wait_time_pct` 远高于 `cpu_time_pct` | 当前负载主要是"等待"型，CPU 没满但大量会话被卡在某类事件 |
| `sys_stat_sql.wait_event_1` 集中在 `IO:DataFileRead` / `IO:WALWrite` | 存储层瓶颈，比 `pg_stat_activity` 的快照更全面（累计） |
| `sys_stat_sql.db_wait / db_time` 比例骤升（即"数据库时间几乎都花在等待上"） | 资源争用而非 SQL 计算瓶颈，**这是金仓独有的整体饱和度指标** |
| `sys_stat_sql.wal_size` 突增 | 写事务/批量更新暴增，结合 `pg_stat_database.tup_updated/tup_inserted` 验证 |
| `sys_stat_sql.temp_blks_write_size` 突增 | `work_mem` 不足或大查询排序落盘 |
| `sys_stat_sql.shared_blks_hit`（命中率）骤降 | 缓存命中下降 / 大表全扫增多 |
| `sys_stat_sql.wait_event_1` / `wait_event_2` 都集中到 `Lock:transactionid` | 锁等待成为主因 |
| `sys_catalog.sys_stat_wait` 中某 `wait_event` `dbtime_pct` 接近 100% | 单个等待事件吞噬了几乎所有 DB 时间，根因集中 |
| `sys_catalog.sys_stat_wal_buffer.utilization_rate` 持续接近 100% | WAL buffer 不够大或 WAL 写盘慢，检查 `wal_buffers` 设置 |
| `sys_catalog.sys_stat_wal_buffer.unwritten_lsn` 持续增长 | WAL 写盘卡住，复制延迟风险 |
| `sys_stat_sysmetric_history` 中 `CPU Usage Per Sec` 突增 / `QPS` 翻倍 | 窗口内负载真实升高（这是金仓 AWR 仓库的标准证据） |
| `sys_stat_sysmetric_history` 中 `Wait Time Per Sec` 突增 | 不是 CPU/IO 瓶颈，而是各种等待事件叠加 |

## 扩展/插件维度

| 信号 | 优先怀疑 |
|---|---|
| `sys_stat_statements` 中某 SQL `total_exec_time` 占比异常高 | 该 SQL 是本次窗口资源消耗的主要来源，需结合两次快照做差确认是否为窗口内新增 |
| `sys_catalog.sys_stat_sql` 同时给出 db_cpu / db_wait / parse / plan / exec 拆分 | **优先用这张表** —— 单表即完成 PG 中 3-4 个视图的合并查询 |
| `sys_stat_sysmetric_history` 窗口内某指标突增 | 弥补 `pg_stat_activity` 无历史快照的缺陷，是回溯型证据的第一来源 |
| 未安装 `sys_kwr` 扩展 | AWR 仓库为空，事后无法回溯历史时序；要求 DBA 开启 |
| `log_min_duration_statement = -1` 且无 auto_explain | 慢查询日志 / 计划回溯双重缺口，要求 DBA 立即打开 |

## 操作系统维度

| 信号 | 优先怀疑 |
|---|---|
| `%iowait` 高、`%user`/`%system` 正常 | 存储瓶颈 |
| `%system` 高 | 内核态开销大，常见于频繁系统调用、锁竞争、上下文切换过多 |
| `dmesg` 出现 `Killed process ... (kingbase)` | OOM Killer 误杀，需检查 `overcommit`/内存限制配置 |
| load average 远高于 CPU 核数但 `%util` 不高 | 大量进程处于不可中断睡眠（D 状态），通常是等待 IO |
| cgroup `throttled_time` 骤增 | 容器 CPU limit 过小，被限流，根因在编排层而非数据库 |

## 存储维度

| 信号 | 优先怀疑 |
|---|---|
| `%util` 接近 100% 且 `await` 远高于基线 | 磁盘 IO 饱和 |
| `df -h` 数据盘可用空间在窗口内趋近于 0 | 磁盘写满风险，KingbaseES 会在写满时 PANIC 停止写入，属最严重级联故障 |
| `pg_wal` / `wal` 目录体积异常膨胀 | 检查点被动触发增多，或存在长时间未确认的复制槽（replication slot）导致 WAL 无法回收 |
| `df -i` inode 使用率接近 100% | 非直觉的存储故障，容易被忽略 |
| 云盘场景：云监控显示 IOPS/带宽被限流 | 根因在云基础设施层，数据库内部指标可能"看似正常" |

## 网络维度

| 信号 | 优先怀疑 |
|---|---|
| 连接数暴涨但 `pg_stat_activity` 中多为 `idle`/`idle in transaction` | 应用侧连接池配置问题或未正确释放连接，而非数据库慢 |
| TCP 重传率异常升高（`sar -n ETCP`） | 网络质量问题，可能是跨机房/跨可用区延迟或抖动 |
| 网卡吞吐骤降 | 网络链路故障或对端限流 |
| 云环境：安全组/负载均衡层当时有限流或异常日志 | 根因可能完全在数据库可见范围之外，需要云侧协同排查 |

## KB 独有后台进程维度

| 信号 | 优先怀疑 |
|---|---|
| `KshMain` wait_event 长期不为空 | 快照助手异常，AWR 仓库可能未落盘 |
| `LogicalLauncherMain` 状态异常 | 逻辑复制 launcher 异常 |
| `AutoVacuumMain` 长时间执行同一张大表 | 防回卷强制清理，长期持有锁，会阻塞其他 vacuum |

## 常见"倒因为果"陷阱

- 连接数暴涨 → 大概率是症状，不是根因；先看是否有更早的锁/IO/计划异常。
- CPU 飙高 → 需先拆分 `%user`/`%system`/`%iowait`（OS 视角）和 `sys_stat_sql.db_cpu` vs `db_wait`（DB 视角），二者根因完全不同。
- 从库延迟 → 需先确认是从库自身资源不足，还是主库产生了异常大的写入/大事务。
- OOM 击杀 kingbase → 表现为"瞬时抖动 + 快速恢复"的脉冲形态，与持续性资源饱和的表现不同，不要混为一谈。
- **`sys_stat_sql.db_wait` 飙高 ≠ 一定在等 IO** → 需配合 `wait_event_1/wait_event_2` 看是 `Lock` / `IO` / `LWLock` / `Client` 还是别的。