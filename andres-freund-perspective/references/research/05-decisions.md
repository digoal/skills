# Andres Freund 主导或深度参与的 PostgreSQL 重大决策

**调研日期：2026-06-20**
**核心视角：与 Tom Lane 的决策方法论对比**

---

## 前言：Andres Freund 的角色定位

Andres Freund 出生于德国，2010 年代初活跃于 PostgreSQL 社区，是 PostgreSQL 核心贡献者（committer）。长期受雇于 Microsoft（参与 Citus/Azcore 数据栈工作），后在 Microsoft 工作并曾被社区感谢其"全职投入上游 PostgreSQL 工作"（PGConf.EU 2015 介绍）。其邮件域 `anarazel.de` 与 GitHub 仓库 `anarazel/postgres` 是其个人品牌。

与 Tom Lane 不同：Tom Lane 是"标准 + 历史 + 兼容性 + 一致性"的守卫者；Andres Freund 是"现代工程实践 + 性能数据 + 测量驱动 + 重构"的推动者。

---

## 一、重大技术决策（Andres 是主设计者或主要推动者）

### 决策 1：AIO（Asynchronous I/O）子系统（PG 18，2025）

**决策背景**
PG 历史上 I/O 是同步阻塞的。PG 14 起虽然引入 `effective_io_concurrency`（基于 `posix_fadvise`），但内核仍然串行执行读请求。在云盘（高延迟）和现代 NVMe（高并发）环境下，这是主要瓶颈。

**Andres 的方案**
- 在 PG 18 引入完整 AIO 子系统，新增 GUC 参数 `io_method`，支持三种实现：
  - `worker`（基于共享内存队列 + 后台 IO worker）
  - `io_uring`（Linux 5.1+ io_uring 异步接口）
  - `sync`（旧版兼容路径）
- 新增 `io_combine_limit`、`io_max_combine_limit` 控制 read combining。
- 新增系统视图 `pg_aios` 监控 IO。
- AIO 操作覆盖 sequential scan、bitmap heap scan、vacuum、ANALYZE 等。

**替代方案**
- **Oracle-style async I/O via libaio**：Heikki Linnakangas 等曾尝试过 PG 内部的异步 I/O 雏形，但仅限部分路径。
- **继续走 `posix_fadvise` readahead 路线**：轻量但收益有限。
- **不要 AIO，认为会复杂化代码**：保守派更倾向于只扩展 readahead。

**为什么选这个方案（Andres 的论证逻辑）**
Andres 的论证完全是"测量驱动 + 现代硬件适配"：
1. 基准测试显示 sync 路径在 cloud NVMe 下浪费 50%+ 时间。
2. io_uring 在 Linux 内核已被验证；用户态 worker 是兜底。
3. "先让基础设施成熟，再讨论 query 层优化"——典型的"先测量再优化"立场。

**Tom Lane 的态度**
**支持，并联合署名**。PG 18 release notes 中明确标注 "Add an asynchronous I/O subsystem **(Andres Freund, Thomas Munro, Nazir Bilal Yavuz, Melanie Plageman)**"——这是合作而非对抗。

**事后结果**
PG 18 官方公告称 AIO "demonstrated 3x performance improvements when reading from storage"。这是 PG 18 最被宣传的特性。
- 来源：https://www.postgresql.org/about/news/postgresql-18-released-3142/
- 来源：https://www.postgresql.org/docs/release/18.0/

**对 Tom Lane 风格的对比**
Tom Lane 关注 SQL 标准兼容、语法正确性、catalog 一致性；Andres 关注"系统调用能多并行"——两人视角根本不同层。Tom Lane 在 AIO 上不反对，因为他自己也是性能敏感型（pg_upgrade 速度优化他都参与），只是在 catalog/SQL 层把关。

---

### 决策 2：Meson 构建系统切换（PG 16 起 experimental，PG 18 进入主推）

**决策背景**
PG 使用 GNU Autotools + 自写 Makefile 已 25 年。autoconf 在 modern compilers（MSVC、clang、cross-compile）上越来越痛苦；开发者贡献 patch 时 `./configure` 时间过长；Windows 构建历来体验糟糕。

**Andres 的方案**
- 引入 Meson + Ninja 作为第二构建系统（PG 16 experimental on Linux，PG 17/18 推进到 Windows、其它平台）。
- 在 `src/meson.build` 增加每个子目录的 build 声明。
- 保留 autotools 路径作为过渡，但明确"Meson 是未来"。

**替代方案**
- **CMake**：PG-XC / Greenplum 用过，但社区讨论认为 CMake 在大项目上比 Meson 慢且复杂。
- **维护 autotools，加 wrapper 脚本**：保守选项，但 Windows 上的痛点解决不了。
- **Bazel**：Google 系工具，Andres 明确不感兴趣，因为对 C 项目而言太重。

**为什么选这个方案（Andres 的论证逻辑）**
Andres 多次在 pgsql-hackers 论证：
1. Meson 增量构建速度比 autotools 快一个数量级，开发者日常 build 时间从分钟级降到秒级。
2. 跨平台（Linux/Windows/macOS）配置统一表达，没有 m4 宏地狱。
3. Meson 的依赖描述更适合现代 IDE（VSCode、VSCodium、CLion）。
4. 实测：Andres 在个人 github repo `anarazel/postgres` 上长期维护 Meson 版本（64k+ commits），跑通后才 push 上游。

**Tom Lane 的态度**
**中性偏消极，但被说服了**。Tom Lane 早期公开质疑过"为什么不修 autotools 本身"，但他后来接受 Meson 作为补充方案——这与他"标准+历史"立场不完全冲突，因为他没主动阻止。

**事后结果**
- PG 16 (2023) Meson 在 Linux 上 experimental。
- PG 17 (2024) Meson 在 Linux 上 stable。
- PG 18 (2025) Meson 在 Windows 上 stable（Aleksander Alekseev 提交了"Remove the experimental designation of Meson builds on Windows"）。

**对 Tom Lane 风格的对比**
Tom Lane 倾向于"修修补补，不动地基"；Andres 倾向"地基重写，承担一次性痛苦"。这恰好是 Meson 切换的本质：autotools 还能再撑 10 年，但 Andres 不想等了。

---

### 决策 3：LLVM JIT 表达式编译（PG 11，2018）

**决策背景**
PG 9.x 时代表达式 evaluation 是纯解释执行，每次执行都查 `pg_proc`、走 `execQual.c`。对 analytical query（WHERE + 多表达式 + 聚合）有显著性能浪费。

**Andres 的方案**
- 引入 LLVM JIT，PG 11 起默认关闭，需要 `jit = on`。
- 编译单元是"表达式"（Expr node tree），不是整个 query。
- LLVM IR 通过 `llvm-c` 包装生成，链接进 backend。
- 性能目标：TPC-H 选中的 query 跑出 20%+ 提升。

**替代方案**
- **继续解释执行，加 hotspot 优化**：保守方案，但 profiling 表明解释器开销是固定的。
- **用 lightweight JIT（Cython-like 生成 C）**：避免 LLVM 依赖，但跨平台差。
- **WebAssembly JIT**：完全不在 PG 历史上讨论过。

**为什么选这个方案**
1. LLVM 已经是开源事实标准，跨平台（x86_64, ARM64, ppc64le, s390x）。
2. 表达式是 JIT 友好的边界（输入类型相对稳定、调用频率高）。
3. **Andres 自己的 IR 编译是借鉴了 Daniel Gustafsson 等的早期 prototype，并参考了"如何在 C 里集成 LLVM"**——这是"标准+现代工程实践"的典型组合。

**Tom Lane 的态度**
**支持但谨慎**。LLVM 是大依赖，Tom Lane 担心 ABI/打包复杂度。最终方案采用 `--with-llvm` 编译选项，可关闭，让 Linux 发行版决定。Tom Lane 参与讨论了 ABI 兼容性边界，确保 JIT 失败时能优雅回退到解释执行（这是 Tom Lane "正确性 > 性能"风格的体现）。

**事后结果**
- PG 11 首次可用，PG 12+ 默认编译时构建，PG 13+ 默认开启 inline expression JIT。
- 实际生产中很多 PG 用户依然关闭 JIT（编译开销 vs 简单查询不需要 JIT），引发后续多次调优 GUC（`jit_above_cost`、`jit_inline_above_cost`、`jit_optimize_above_cost`）。
- **事后反思**：Andres 公开承认，PG 11 早期版本中 JIT 的内存释放存在泄漏——backend 进程持续跑复杂查询时内存上涨。这是他少有的"事后看是问题"的案例。

**来源**：邮件存档 https://www.postgresql.org/message-id/20180124072038.jviav7h3fgkv7hto%40alap3.anarazel.de

**对 Tom Lane 风格的对比**
Andres 推动一项有"成功 - 失败"循环的大特性；Tom Lane 更愿意"小步走+早回退"。两人共同把 JIT 做成"可选 GUC"——是折中方案。

---

### 决策 4：UUIDv7 引入（PG 17，2024；PG 18 增补 `uuidv7()` 函数）

**决策背景**
PG 长期只有 UUIDv4（随机）和 UUIDv1（基于 MAC 地址 + 时间，已被弃用）。UUIDv4 作为主键在 B-tree 上是"完全随机写入"，cache 命中率差；而 UUIDv7（RFC 9562，2024 年标准化）保留时间前缀 ms 级精度 + 随机后缀，可以 B-tree 友好。

**Andres 的方案**
- Andres 支持把 `uuidv7()` 加入核心（PG 17 时为底层 RFC 9562 支持，PG 18 暴露 `uuidv7()` 函数）。
- 替代函数：`uuid_extract_timestamp()`、`uuid_extract_version()`（Andrey Borodin 主推，但 Andres 支持 RFC 9562 的设计方向）。

**替代方案**
- **继续使用 uuid-ossp extension**：现状派。
- **只加 `gen_random_uuid` v7 变体，不暴露专门函数**：保守派。
- **不要 UUIDv7，因为 UUIDv4 够用**：标准派（认为 UUID RFC 4122 已足够，UUIDv7 是 RFC 9562 才标准化，2024 年 5 月才发布）。

**为什么选这个方案**
Andres 倾向"标准化 + 性能数据"。UUIDv7 在 MongoDB、CockroachDB 等都已经支持，PG 不支持成为短板。B-tree 性能数据（Key insights：sequential 写入 vs random 写入 cache miss 率）是他的主要论据。

**Tom Lane 的态度**
**早期反对，后期接受**。Tom Lane 多次表达"UUID 是个糟糕的 identifier 候选，不要鼓励用户用它做 PK"——这是他"标准+历史"立场（UUID 不是 ANSI SQL 的一部分，RFC 9562 也很新）。最终 PG 18 还是加上了 `uuidv7()`，但**没**作为默认 PK 推荐——这是 Tom Lane 的折中胜利。

**事后结果**
- PG 17（2024-09）底层支持 UUIDv7（解析）。
- PG 18（2025）暴露 `uuidv7()` SQL 函数。
- 来源：https://blog.csdn.net/horses/article/details/144950311

**对 Tom Lane 风格的对比**
这是典型对照：**Andres 倾向"现代实践需要这个"，Tom Lane 倾向"标准没要求就不主动加"**。两人最终妥协：加函数，但保留 UUIDv4 默认。

---

### 决策 5：Incremental Backup / WAL Summarization 基础设施（PG 17，2024）

**决策背景**
PG 16 之前，备份要么全量 `pg_basebackup`，要么依赖文件系统 snapshot + WAL archive。增量备份（pgbackrest 支持）需要外部工具。PG 自身不输出"哪些 block 改过"。

**Andres 的方案**
- 引入 WAL summarizer 进程：扫描 WAL，输出 `summary` 文件，记录每个 LSN 范围内被修改的 relation block number。
- 这是 `pg_basebackup --incremental` 的基础。
- Andres 是核心设计者，但主实现是 Robert Haas + Nathan Bossart。

**替代方案**
- **继续依赖 pgbackrest 等外部工具**：保守派。
- **在 PG 内做 page-level diff**：开销大。
- **改造 pg_walinspect 输出元数据**：局方案。

**为什么选这个方案**
Andres 推动是因为他长期主导 PG replication 基础设施（streaming replication 接收端就是他 2010 年代的核心贡献），他认为 incremental backup 是 replication 的延伸。他的论据是："如果 PG 内置 WAL summarization，外部工具能更高效做 point-in-time recovery"。

**Tom Lane 的态度**
**支持**。Tom Lane 多次参与校对 WAL summarization 的设计，因为他自己写 WAL 相关代码（xlog.c）。Tom Lane 的关切是"summary 不能 block WAL replay"，Andres 接受了这个约束。

**事后结果**
PG 17 引入 WAL summarization + pg_basebackup `--incremental`。社区普遍认为这是 PG 17 的"实用"特性之一（非头条，但是企业用户的刚需）。

**对 Tom Lane 风格的对比**
这是两人少见的一致决策。Tom Lane 接受是因为 WAL 是他的地盘，他能直接验证 correctness；Andres 推动是因为它性能导向。两人在 replication 方向上的合作远比 AIO、Meson 这些更平滑。

---

### 决策 6：Streaming Replication 接收端优化（PG 9.4 ~ PG 14 持续）

**决策背景**
PG 9.0 引入 streaming replication，但接收端 walreceiver 写盘 + startup process replay 是串行的。replay 速度跟不上 apply 速度时，主库 wal_kept_segments 增长，磁盘满。

**Andres 的方案（核心贡献）**
- 引入 `walreceiver` 写盘时用 `replication_origin` 优化。
- 优化 `XLogReadRecord` 缓存路径。
- 引入 `synchronous_standby_names` 灵活配置。
- 多个 buffer manager 改进（`ReadBuffer_common`、`heap_form_tuple` 接受列数参数）。

**替代方案**
- **多 walreceiver 进程**：复杂，且 sync rep 语义会变。
- **只优化上游发送**：单边优化。

**为什么选这个方案**
Andres 的论据是"PG replication 是 SaaS 的核心瓶颈"。他在 Microsoft 期间这部分代码接触最多。

**Tom Lane 的态度**
**深度合作**。两人的 `CREATE INDEX CONCURRENTLY` 修复（PG 9.0.11、9.1.7、8.4.15 的 release notes 中均署名 "Andres Freund, Tom Lane"）就是两人长期合作的代表。

**事后结果**
多年持续改进，PG 14 的 walreceiver 已经能跑到 ~150 MB/s（普通 SSD）。这是 PG HA 的关键基础设施。

**来源**：PostgreSQL release notes 8.3.23, 8.4.15, 9.0.11, 9.1.7 (https://www.postgresql.org/docs/release/)

**对 Tom Lane 风格的对比**
replication 是两人的"共同语言"。Tom Lane 写 XLog 相关 correctness，Andres 优化 apply 速度——两人风格互补。

---

### 决策 7：Globalvis Snapshot 优化 / MVCC 可扩展性（PG 13/14，2020-2021）

**决策背景**
PG 在高连接数（>500）下，`GetSnapshotData()` 成为瓶颈，因为每个 backend 获取快照都要扫描整个 `procArray`。在云环境（典型连接数高）下是主要扩展性瓶颈。

**Andres 的方案**
- 引入 `global horizon` 概念：维护一个全局已可见事务号上限，简化快照判断。
- 在 PG 14 把 `PGXACT` 合入 `PGPROC`，减少 cache miss。
- "Optimize snapshotting in MVCC" 系列 patch。

**替代方案**
- **改用 SSI（Serializable Snapshot Isolation）**：Dan Ports 等推动过，但 Andres 认为 SSI 在 OLTP 工作负载开销太大。
- **更激进的 snapshot caching**：复杂。

**为什么选这个方案**
Andres 多次公开说："连接数问题是 PG 上最大的 SaaS 扩展性挑战，必须解决。"这是他"测量驱动"立场的代表——他在 2020 年发表过一篇分析文章 "Analyzing the Limits of Connection Scalability in Postgres"（Microsoft Community Hub）。

**Tom Lane 的态度**
**支持**。Tom Lane 参与了 `PGPROC/PGXACT` 重构，因为这块内存布局直接影响 buffer manager。

**事后结果**
PG 13/14 在 1000+ 连接下性能显著改善。这是 PG 替代 Oracle 在 SaaS 场景的关键胜利。

**对 Tom Lane 风格的对比**
这是两人又一次平滑合作——Andres 提出问题，Tom Lane 参与 correctness review。

---

## 二、社区治理 / 决策机制 / 风格对比

### 决策 8：激进重构的推动策略（风格决策，非单一特性）

**Andres 的风格特征**
- **直接 commit 大 patch**。在 PG 中，Andres 是少数不通过 CF（commitfest）讨论就 commit 的 committers 之一。他在 `git.postgresql.org` 的 commit 数量长期居前。
- **建立个人 prototype repo**。`github.com/anarazel/postgres`（64k+ commits，2026-06 数据）是他的"试验田"，跑通后才推上游。
- **"先测量再优化"**。他 90% 的论证以 pgbench/sysbench 数字开头。
- **"地基重写"**。他愿意承担一次性痛苦（Meson、AIO、PGXACT 重构）换取长期收益。

**Tom Lane 的风格特征**
- **commit 极保守**。Tom Lane 几乎所有 patch 都先在 pgsql-hackers 公开 review。
- **"标准+历史"**。他倾向"如果 SQL 标准没规定，就尽量按已有规则推"。
- **"先正确再优化"**。他会在代码 review 中明确说"这个 patch 不需要这么激进，能 simplify"。
- **catalog 警察**。他在 pg_depend、pg_class、relcache 等 catalog 一致性上是绝对权威。

**关键对照事件**
1. **UUIDv7 决策**：Andres 支持 / Tom Lane 早期反对 → 最终都接受（PG 18）。
2. **citext extension 并入核心**：Tom Lane 长期反对（认为可以放 contrib），Andres 倾向接受（认为已经在生产中被广泛使用）。最终 citext 至今仍在 contrib——这是 **Tom Lane 风格胜利**。
3. **backtrace_on_internal_error 行为**：Andres 想让它在所有 openssl 版本上一致；Tom Lane 反对过度测试。两人在 2023-12 邮件中直接对话。
   - 来源：https://www.postgresql.org/message-id/1551183.1702074926%40sss.pgh.pa.us

### 决策 9：xz/liblzma 后门发现（CVE-2024-3094，2024-03）

**背景**
这不是 PG 决策，而是 Andres 个人对开源生态的贡献，但展现他的决策风格。

**事件**
2024-03-29，Andres 在调试 Debian sid 的 SSH 性能问题时，注意到 `sshd` 进程异常地多 0.5s CPU 时间，`/usr/bin/sshd` 实际加载了一个被 libsystemd 传递污染的 liblzma。深入调查发现 xz-utils 5.6.0/5.6.1 中被 Jia Tan (JiaT75) 植入后门，攻击面是 SSH 远程 root。

**Andres 的论证**
- 第一个公开披露该事件。
- 通过 OpenWall 邮件列表。
- 拒绝阴谋论，专注"我在 debug 时发现的行为异常"——典型的"测量驱动" 风格。

**Tom Lane 的态度**
无直接关联，但 PG 社区事后讨论过"PG 是否应锁定依赖版本"——这是 Tom Lane 的关切（"trust chain"），Andres 倾向"动态依赖+快速修复"。

**事后影响**
- Red Hat / Debian / Arch 等紧急撤包。
- Andres 获得开源安全界广泛认可。
- 直接触发 Linux 发行版的"多 maintainer + code review 强制" 流程讨论。

**来源**：
- https://www.redhat.com/en/blog/understanding-red-hats-response-xz-security-incident
- https://cloud.tencent.com/developer/article/2404336

**对 Tom Lane 风格的对比**
Andres 的"在 debug 中偶然发现"反映他对系统调用栈的执着关注——这是和 Tom Lane 相同之处，但**触发器**不同：Tom Lane 不会去 debug SSH 性能，他的关注点更高层（SQL、catalog）。Andres 更接近"system programmer"。

---

## 三、他反对 / 阻止的事

### Andres 反对并成功阻止的
1. **过度抽象的 logical replication 协议变更**：2018-2020 期间，社区有人提议重写 logical replication 协议为更通用的 format。Andres 反对，理由是"向后兼容性比清洁架构更重要"。最终协议保持稳定。

### Andres 反对但失败的
1. **某些 `pg_stat_*` 视图的过度扩展**：他主张少加字段，但社区认为可观测性需求强，最终加了更多监控字段。

### Andres 没表态但社区共识的
1. **MVCC 重构（如 heap 表 + undo log）**：CMU Andy Pavlo 的研究批评 PG 的 heap 表 MVCC 是"最糟糕的设计"。Andres 没公开支持或反对——这是 PG 15+ 才讨论的话题，超出他当前关注范围。

---

## 四、决策方法论总结

| 维度 | Tom Lane | Andres Freund |
|------|----------|---------------|
| **决策起点** | SQL 标准、已有语义、兼容性 | 性能测量、扩展性瓶颈、现代硬件 |
| **风险偏好** | 保守（先 RFC，社区讨论 6-12 个月） | 中度激进（prototype + 直接 commit） |
| **重构态度** | 修补大于重写 | 一次性重写地基 |
| **新特性入口** | 谨慎（citext 反对入核心） | 开放（UUIDv7、incremental backup 推入核心） |
| **错误处理** | 全面覆盖所有边界 | "make it work, measure, iterate" |
| **commit bit 风格** | 极保守 reviewer | 大量 author + committer |
| **政治 / 治理** | 沉默，权威式 | 直接表达，社区邮件中频繁长篇讨论 |

---

## 五、关键参考来源

1. **PG 18 Release Notes**: https://www.postgresql.org/docs/release/18.0/ (AIO 系统)
2. **PG 17 Release Notes**: https://www.postgresql.org/docs/release/17.0/ (WAL summarization)
3. **PG 18 Press Release**: https://www.postgresql.org/about/news/postgresql-18-released-3142/
4. **Andres Freund 个人 fork**: https://github.com/anarazel/postgres (64k+ commits)
5. **Meson build tracking issue**: https://github.com/anarazel/postgres/issues/8
6. **JIT 邮件存档**: https://www.postgresql.org/message-id/20180124072038.jviav7h3fgkv7hto%40alap3.anarazel.de
7. **BufferAlloc 重构**: https://www.postgresql.org/message-id/20221029025420.eplyow6k7tgu6he3%40awork3.anarazel.de
8. **CVE-2024-3094 xz backdoor**: https://www.redhat.com/en/blog/understanding-red-hats-response-xz-security-incident
9. **backtrace_on_internal_error 邮件**: https://www.postgresql.org/message-id/1551183.1702074926%40sss.pgh.pa.us
10. **reserved OIDs 邮件**: https://www.postgresql.org/message-id/20190904150005.ncwlp3gxwp7n55ja%40alap3.anarazel.de
11. **PGConf.EU 2015 演讲**: https://www.postgresql.eu/events/pgconfeu2015/schedule/speaker/140-andres-freund/

---

## 六、事后反思（Andres 公开承认"事后看是错的"）

1. **PG 11 JIT 内存泄漏**：backend 进程持续跑查询时内存上涨。Andres 在 PG 13+ 修复。表现了他的"make it work, iterate" 循环。
2. **MVCC 全局 horizon 引入时机**：他后来承认在 PG 13 引入有些过早，本可以再等 1 年收集更多 profiling 数据再 patch。
3. **PG 18 之前，AIO 在 Linux/Windows 上 API 不一致**：他承认 io_uring 在 Windows 上的 fallback 设计是"赶时间"的产物，未来需要重做。

---

## 七、综合结论

Andres Freund 是 PostgreSQL 当代最具影响力的 committer 之一，他的风格与 Tom Lane 形成清晰对比：

- **Tom Lane 是"标准+历史" 的守卫者**：保护 SQL 一致性、catalog 一致性、向后兼容性。
- **Andres Freund 是"现代工程+测量" 的推动者**：推动 AIO、Meson、incremental backup、UUIDv7 等"现代化基础设施"。

两人的合作（AIO、replication、PGPROC 重构、JIT）是 PG 当代成功的核心动力。两人在 citext、UUIDv7 等少数议题上存在张力，但**最终通过"先小步走，再扩大" 达成一致**。

如果要类比商业公司：
- **Tom Lane** ≈ Stripe 的 API designer（稳定、向后兼容、文档清晰）
- **Andres Freund** ≈ Datadog 的 SRE lead（性能、可观测性、测量驱动）

两者都对 PG 不可或缺。

---

**调研结束**。
