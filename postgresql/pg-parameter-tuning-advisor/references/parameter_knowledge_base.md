# PostgreSQL 关键参数调优知识库

本文件是 `pg-parameter-tuning-advisor` skill 的参考资料，供 Step 5（生成参数调整建议）查阅经验公式和取值范围。**所有公式都是起点，不是终点**——最终建议值必须结合 Step 2/3/4 实际采集到的证据做修正，不能直接套用。

## 一、内存类参数

### shared_buffers
- 作用：PostgreSQL 自己管理的共享缓冲区，缓存表/索引页面。
- 经验起点：物理内存的 **25%**（专用数据库主机），云托管/共享主机场景可能需要更保守（15%~20%），避免和 OS page cache 抢内存导致双重缓存浪费。
- 上限参考：一般不建议超过物理内存的 40%，除非有专门测试验证收益。
- 判断是否需要调整：缓存命中率 `blks_hit/(blks_hit+blks_read)` 持续低于 99%，且当前 `shared_buffers` 明显小于经验起点。
- 生效方式：**restart**。

### effective_cache_size
- 作用：告诉查询规划器"操作系统+数据库总共大概能缓存多少数据"，只影响执行计划选择（是否倾向索引扫描），不实际分配内存。
- 经验起点：物理内存的 **50%~75%**（shared_buffers + OS page cache 的估计总和）。
- 判断依据：若设置过小，规划器会低估缓存命中概率，倾向于顺序扫描而非索引扫描，即使数据实际都在缓存里。
- 生效方式：**reload**。

### work_mem
- 作用：单个查询中每个排序/哈希操作可用的内存，不是每个连接或每个查询的总额度。
- 经验起点公式：`(物理内存 × 0.25) / (预估最大并发连接数 × 预估每查询平均并发操作数)`，一般每查询预估 2~4 个并发排序/哈希操作。
- 判断依据：`pg_stat_database.temp_files`/`temp_bytes` 持续增长说明排序/哈希操作频繁溢出到磁盘，是加大 `work_mem` 的直接证据。
- 风险：高并发 + 复杂查询下总内存占用可能是 `work_mem × 并发连接数 × 每连接并发操作数`，务必给出总量估算并留足余量，避免 OOM。
- 生效方式：**reload**（也可在会话级用 `SET work_mem` 临时调整，用于个别报表类查询）。

### maintenance_work_mem
- 作用：`VACUUM`、`CREATE INDEX`、`ALTER TABLE` 等维护操作使用的内存，独立于 `work_mem`。
- 经验起点：物理内存的 **5%~10%**，通常设为几百 MB 到 2GB；autovacuum 并发 worker 也会各自占用一份，需要按 `autovacuum_max_workers` 数量估算总占用。
- 判断依据：大表 `VACUUM`/建索引耗时过长、或 `autovacuum` 因内存不足反复分批处理。
- 生效方式：**reload**。

### huge_pages
- 作用：使用操作系统大页内存，减少内存管理开销，对大 `shared_buffers` 场景效果明显。
- 判断依据：`shared_buffers` 超过几个 GB 时建议开启（`huge_pages = try` 或 `on`），需要操作系统层面预先分配 `vm.nr_hugepages`。
- 生效方式：**restart**，且依赖 OS 侧 `vm.nr_hugepages` 配置到位。

## 二、连接类参数

### max_connections
- 作用：允许的最大客户端连接数。
- 判断依据：`pg_stat_activity` 里的实际并发连接数、以及 `idle in transaction`/`idle` 状态占比。若空闲连接占比很高，优先建议应用层引入连接池（PgBouncer 等），而不是单纯加大 `max_connections`——连接数过多会增加上下文切换开销，且和 `work_mem` 乘积关系直接影响内存上限。
- 经验参考：物理核数的 **3~5 倍**作为不使用连接池时的粗略上限参考，具体仍需结合实际并发。
- 生效方式：**restart**。

## 三、WAL / Checkpoint 类参数

### wal_buffers
- 作用：WAL 写入前的缓冲区。
- 经验起点：`shared_buffers` 的 **1/32**左右，常见设为 16MB（PG 会在 -1 时自动按此公式估算，多数场景无需手工设置过大）。
- 生效方式：**restart**。

### max_wal_size / min_wal_size
- 作用：`max_wal_size` 控制两次 checkpoint 之间允许积累的 WAL 量上限，是影响 checkpoint 触发频率最直接的参数。
- 判断依据：`pg_stat_bgwriter.checkpoints_req`（因达到 `max_wal_size` 触发）相对 `checkpoints_timed`（因达到 `checkpoint_timeout` 触发）占比高，说明 `max_wal_size` 偏小，导致 checkpoint 过于频繁，产生 IO 尖峰。
- 经验起点：写入密集型场景可设为 **4GB~16GB** 或更高，需结合磁盘 IO 能力和期望的崩溃恢复时间（越大恢复时间越长）权衡。
- 生效方式：**reload**。

### checkpoint_completion_target
- 作用：checkpoint 在下一次 checkpoint 前多长时间比例内完成脏页写入，越接近 1 越平滑但拖得越久。
- 经验起点：**0.9**（默认已是较好值），一般不需要大改。
- 生效方式：**reload**。

### checkpoint_timeout
- 作用：定时 checkpoint 的最大间隔。
- 经验起点：**15min~30min**（写入密集场景可适当延长配合更大的 `max_wal_size`）。
- 生效方式：**reload**。

## 四、Autovacuum 类参数

### autovacuum_vacuum_scale_factor / autovacuum_analyze_scale_factor
- 作用：表中死元组/变更行数达到 `表行数 × scale_factor + threshold` 时触发 autovacuum/autoanalyze。
- 判断依据：大表（千万行以上）用默认 `0.2`/`0.1` 会导致触发阈值过大、vacuum 间隔过长，`n_dead_tup` 长期偏高、统计信息陈旧导致执行计划劣化。
- 经验起点：大表场景可下调到 **0.05~0.1**，并可对单表用 `ALTER TABLE ... SET` 单独设置而非全局改动（全局改动会增加所有表的 autovacuum 频率，需评估整体 IO 影响）。
- 生效方式：**reload**（全局）；单表设置立即生效。

### autovacuum_max_workers / autovacuum_vacuum_cost_limit
- 作用：并发 autovacuum worker 数量、以及每轮 vacuum 允许消耗的 IO 成本预算。
- 判断依据：多个大表同时需要 vacuum 但 worker 数不够、或 `autovacuum_vacuum_cost_limit` 太小导致 vacuum 速度跟不上写入速度（`n_dead_tup` 持续攀升）。
- 生效方式：`autovacuum_max_workers` 需要 **restart**；`autovacuum_vacuum_cost_limit` 只需 **reload**。

## 五、Planner 类参数

### random_page_cost
- 作用：规划器估算随机 IO 相对顺序 IO 的代价倍数，默认 `4.0` 是为机械盘设计的。
- 判断依据：Step 3 采集到存储介质为 SSD/NVMe（`lsblk` 中 `ROTA=0`）时，随机 IO 与顺序 IO 的实际差距远小于机械盘。
- 经验起点：SSD/NVMe 场景常调整为 **1.1~2.0**，云盘（如网络存储）视具体延迟特征介于两者之间。
- 生效方式：**reload**。

### effective_io_concurrency
- 作用：控制 bitmap heap scan 等场景下预取的并发 IO 请求数，SSD/NVMe 上可以设置更高。
- 经验起点：机械盘 **1~2**，SSD **100~200**，NVMe 可以更高（部分场景 200~300）。
- 生效方式：**reload**。

### default_statistics_target
- 作用：`ANALYZE` 收集列统计信息的采样粒度，影响执行计划准确性。
- 判断依据：复杂查询（多表 join、范围查询）执行计划频繁偏离预期、`pg_stat_statements` 中某些查询的估算行数和实际行数差距很大。
- 经验起点：默认 `100`，问题列可以单独 `ALTER TABLE ... ALTER COLUMN ... SET STATISTICS` 提到 `500~1000`，全局调高会显著增加 `ANALYZE` 耗时，一般不建议全局大改。
- 生效方式：**reload**（配合重新 `ANALYZE` 才能生效到具体表）。

## 六、并行查询类参数

### max_worker_processes / max_parallel_workers / max_parallel_workers_per_gather
- 作用：控制后台 worker 总数、并行查询可用 worker 总数、单个查询可用 worker 数。
- 经验起点：`max_worker_processes` 略高于物理核数（预留给 autovacuum、逻辑复制等其他后台进程），`max_parallel_workers` 不超过物理核数，`max_parallel_workers_per_gather` 一般为 **2~4**，避免单个查询占满所有核心影响其他并发。
- 判断依据：OLAP/大查询场景且 CPU 有空闲余量时可以提高；OLTP 高并发场景下过高的并行度反而会因为频繁调度产生开销。
- 生效方式：`max_worker_processes` 需要 **restart**；`max_parallel_workers`/`max_parallel_workers_per_gather` 只需 **reload**。

## 七、提交/复制类参数

### synchronous_commit
- 作用：控制事务提交时是否等待 WAL 落盘/同步到备库才返回给客户端。
- 判断依据：对写入延迟极度敏感、可以接受极小概率丢失最近事务的场景，可考虑 `off` 或 `local`；有强一致性要求（金融类）应保持 `on` 甚至配合同步复制。
- 生效方式：**reload**，且可以按会话级别 `SET` 覆盖，无需全局强改。

## 八、操作系统层面配套参数（非 postgresql.conf，但直接影响数据库表现）

| 参数/设置 | 位置 | 建议 | 说明 |
|-----------|------|------|------|
| Transparent Huge Pages | `/sys/kernel/mm/transparent_hugepage/enabled` | `madvise` 或 `never` | `always` 模式下 THP 的合并/拆分开销可能造成随机的延迟毛刺 |
| vm.swappiness | `sysctl` | 数据库专用主机建议调低（如 1~10） | 避免 OS 在内存尚有富余时就开始换出，影响缓存命中率 |
| vm.overcommit_memory / overcommit_ratio | `sysctl` | 按实际内存规划评估 | 影响大内存分配（如大 `shared_buffers`）时是否会被 OOM killer 误杀 |
| IO 调度器 | `/sys/block/<dev>/queue/scheduler` | NVMe/SSD 场景常用 `none`/`mq-deadline`，机械盘用 `deadline` | 不同调度器对随机 IO 延迟影响不同，需结合实际测试 |
| ulimit -n（打开文件数） | `/etc/security/limits.conf` 或 systemd unit | 需大于 `max_connections` 相关文件句柄预估 | 连接数多、表/索引文件多的场景容易触顶 |
| 文件系统挂载选项 | `/etc/fstab` | 数据目录挂载建议 `noatime` | 避免每次读取都触发 atime 更新写入，减少不必要的 IO |

## 九、常见 workload 画像与优先关注参数对照

| Workload 类型 | 特征 | 优先关注参数 |
|----------------|------|--------------|
| OLTP 高并发短事务 | 大量简单点查/小事务、连接数高 | `max_connections`、连接池、`work_mem`（保守）、`autovacuum` 及时性、`synchronous_commit` |
| OLAP 少量长查询 | 大范围扫描、聚合、join 多 | `work_mem`（可适当放大配合并行）、`max_parallel_workers*`、`effective_cache_size`、`random_page_cost`/`effective_io_concurrency` |
| 写入密集型 | 高频 INSERT/UPDATE、WAL 生成快 | `max_wal_size`、`checkpoint_*`、`wal_buffers`、存储 IO 能力、`synchronous_commit` |
| 混合型 | 兼具上述特征 | 需要按证据分先后优先级，避免顾此失彼（如为了 OLAP 加大 work_mem 而拖垮 OLTP 并发内存预算） |
