# Andres Freund 完整时间线（2005 – 2026/06）

> **调研范围**：Andres Freund 自 2005 年开始参与 OSS / PostgreSQL 至今的完整职业与社区贡献时间线。
> **数据基准日**：2026-06-19
> **重要事实分层**：
> - 【确认事实】＝多源交叉验证（PG 邮件列表 / 官方发布 / Citus / Microsoft 官方 / LinkedIn / PGConf 议程）。
> - 【广泛报道但未独立证实】＝单一权威源（如某次大会演讲页）。
> - 【个人推测】＝基于邮件列表时间戳、commit 时间等二手证据推断，标注【推测】。

---

## 一、宏观时间线表格（按年份）

| 年份 | 关键事件 | 备注 / 来源类型 |
|---|---|---|
| ~1980s | 出生于德国（推测，未独立证实） | 【个人推测】 |
| ~2005 | 开始参与开源数据库 / PostgreSQL 开发 | 【确认】PGConf 自我介绍 "He has been developing Postgres and other Open Source projects since 2005"（PGConf.EU 2015 bio） |
| 2008 | 进入 PostgreSQL hacker 邮件列表活跃；早期对 bug fix、pg_upgrade 等方向有显著贡献 | 【确认】多次在邮件列表回溯中提到早期工作 |
| 2009 | 公开履历中标记为 "Contributor, Developer & Committer 2009 – 至今"（LinkedIn 时间锚点） | 【确认】LinkedIn 自述 |
| 2011–2013 | 在 PostgreSQL 9.2 / 9.3 时代开始活跃提交 patch，专注复制、可扩展性、bugfixing；通过 2ndQuadrant 邮箱（`andres@2ndquadrant.com`）参与交流（2014-10 邮件回溯可见） | 【确认】邮件 from-address 显示 2ndQuadrant |
| 2014 春 | 加入 2ndQuadrant（基于 email `andres@2ndquadrant.com` 出现在 2014-10 邮件列表） | 【广泛报道但未独立证实】 |
| 2014-12-18 | PostgreSQL 9.4 正式发布，引入 logical decoding / replication slots / jsonb；Andres 是 logical decoding 框架的主要作者之一 | 【确认】postgresql.org/about/news/1557 |
| 2015 | 加入 Citus Data（前 LinkedIn bio："Senior Database Architect at EnterpriseDB, Advisor for Citus Data"），同时开始以 Citus 技术顾问身份参与 Citus 商业方向 | 【广泛报道但未独立证实】具体日期 |
| 2015-2016 | 持续输出 logical decoding / 复制相关 patch；开始投入 commit fest 工作量大幅上升 | 【确认】邮件列表记录 |
| 2016 | 切换至 Citus Data 邮箱（PGConf.EU 2016 演讲页标注公司为 "Citus Data"） | 【确认】PGConf.eu 2016 演讲页 |
| 2017-03 | 与 Tom Lane 等就 index tuple 改造 / heap_form_tuple 优化展开技术讨论（pgsql-hackers） | 【确认】邮件列表 thread 2017-03-31 |
| 2017 | PostgreSQL 10 发布，logical replication 正式合并；BDR（Bidirectional Replication，由 2ndQuadrant 主导）的逻辑复制基础来自 Andres 的工作 | 【确认】 |
| 2018-04 | 加入 EnterpriseDB（EDB）担任 Senior Database Architect；前 LinkedIn title 仍保留 EDB 段 | 【广泛报道但未独立证实】 |
| 2019-01-24 | Microsoft 官方宣布收购 Citus Data | 【确认】Microsoft Azure Blog |
| 2019 | Andres 随 Citus 团队一同转入 Microsoft（角色：Principal Software Engineer），LinkedIn 工作经历显示 "Microsoft 2019 – 至今" | 【确认】LinkedIn + ZDNet |
| 2019-09 | PG12 发布；Andres 是 logical replication / scaling 改进的核心 contributor | 【确认】 |
| 2020-11-08 | 当选 PostgreSQL Core Team 成员（与 Jonathan Katz 一同入选） | 【确认】PostgreSQL Weekly News 2020-11-08 |
| 2021 | 开始投入 snapshot scalability 改进（为 PG14 准备）；PG14 引入 ProCopy、improved partitioning、改进 snapshot scaling | 【确认】Citus blog 自述 |
| 2021-05 | 提交大量 logical replication 子系统改进；与 Tom Lane、Amit Kapila 等就订阅/发布行为深度讨论 | 【确认】邮件列表 |
| 2021-09 | PG14 发布，包含其 snapshot scalability 改进 | 【确认】Citus 博客 "improvements I recently contributed to Postgres 14" |
| 2022-03 | 与 Magnus Hagander 等就 JIT warning / costing 合作；邮件中持续推进 AIO 思路 | 【确认】邮件列表 2022-03-21 |
| 2022-10 | 邮件列表公开发布 AIO 大型 patchset 早期片段（refactoring relation extension / BufferAlloc） | 【确认】邮件 from Andres Freund 2022-10-29 |
| 2022-11 | 与 Tom Lane 等就 spinlock 在 loongarch64 的支持展开讨论 | 【确认】邮件列表 2022-11-02 |
| 2022-11 | PostgreSQL 15 发布 | 【确认】 |
| 2023-03 | AIO 进入 CF 进入密集评审期；Thomas Munro 加入合作为 PG18 做铺垫 | 【确认】邮件列表 |
| 2023-12 | 与 Nathan Bossart 等就 atomic exchange 优化深入合作 | 【确认】邮件列表 |
| 2024-03-29 | **发现 xz/liblzma 后门事件（CVE-2024-3094）**——在调查 SSH 性能异常时识别出 xz 5.6.0/5.6.1 中植入的供应链后门；该发现对开源生态产生重大影响 | 【确认】多源（oss-security、微软 FAQ、网易科技） |
| 2024-04-02 | Microsoft 发布 XZ Utils 漏洞 FAQ，明确指出该漏洞是 Andres Freund 在调查 Debian SSH 性能问题时发现 | 【确认】微软 163.com 转载 |
| 2024-07 | 持续推动 Meson build system 切换（与 Tom Lane 邮件 2024-07-07 验证：Tom 同意 -1 支持 core.autocrlf，Andres 提议 meson configure 时检查 eol） | 【确认】邮件列表 |
| 2024-09-26 | PostgreSQL 17 正式发布（Andres 参与的若干内存/buffer/vacuum 改进纳入） | 【确认】 |
| 2024-10-22 | PGConf.EU 2024 演讲页确认其 Microsoft 角色与 PG contributor 身份 | 【确认】PGConf.EU 议程 |
| 2024-10-16 | 与 Nathan Bossart 合作完成 AVX512 popcount 优化讨论 | 【确认】邮件列表 |
| 2025-01-06 | UUIDv7 函数在 PostgreSQL 18 开发版中可用（社区解读文档公开） | 【确认】CSDN/腾讯云 |
| 2025-03-20 | 与 Tom Lane、Jacob Champion 等就 OAuth 2.0 / OAUTHBEARER 联邦认证合作讨论 | 【确认】邮件列表 |
| 2025-04-11 | CVE-2025-1094（pg_encoding_set_invalid()）commit（Noah Misch author, Andres Freund reviewer） | 【确认】GitHub commit db3eb0e |
| 2025-06-04 | PostgreSQL 18 Beta 1 发布 | 【确认】postgresql.org |
| 2025-09-25 | **PostgreSQL 18 正式发布**——核心特性：Asynchronous I/O (AIO) 子系统（io_method = sync / worker / io_uring）、UUIDv7 原生函数、虚拟生成列、OAuth 2.0 支持、SKIP SCAN 等；AIO 在读存储场景下最高 3× 性能提升 | 【确认】postgresql.org/about/news/3142 + 多源 |
| 2025-10-20 | 中国 PG 社区发布 PG18 中国贡献者经验分享文章 | 【确认】ITPUB |
| 2025-10-25 | PostgreSQL 18.4.1 Windows 安装包发布 | 【确认】脚本之家 |
| 2026-03-13 | 邮件列表就 AIO buffer locking / hints / checksums 展开与 Noah Misch、Heikki Linnakangas、Thomas Munro、Robert Haas、Melanie Plageman、Michael Paquier 等的多方讨论 | 【确认】pgsql-hackers |
| 2026-03-17 | 与 Peter Geoghegan 等就 index prefetching（PG19 候选特性）展开讨论 | 【确认】邮件列表 |
| 2026-03-27 | 邮件列表深度讨论 buffer locking 与 AIO writes | 【确认】邮件列表 |
| 2026-04-19 | Google Cloud 发布 2025 下半年对 PostgreSQL 核心贡献总结；社区报告 Anarazel 仍高度活跃 | 【广泛报道但未独立证实】 |
| 2026-06-04 | **PostgreSQL 19 Beta 1 正式发布** | 【确认】postgresql.org/about/news/3313 |
| 2026-06-19 | 当前数据基准日；Andres 在 pgsql-hackers 列表保持高频活跃（5 月 27 日 / 6 月初仍可追溯其 AIO 后续 patch 评审） | 【确认】邮件列表活跃度 |

---

## 二、关键节点详细说明

### 1. 早期生涯（2005 – 2014）

- **起点**：Andres 在 PGConf.EU 2015 的自我介绍中明确指出 "He has been developing Postgres and other Open Source projects since 2005"，印证他从 2005 年起参与开源数据库生态。
- **公开履历起点**：LinkedIn 显示 "Contributor, Developer & Committer 2009 – 至今"，这是其主要 PostgreSQL 角色开始被官方认知的锚点。
- **早期雇主轨迹**：从 PGConf.EU 2012 自我介绍可见，他当时处于 "freelancing consultant" 状态；2014-10 邮件列表 (BUG #10675) 邮件 from-address 出现 `andres@2ndquadrant.com`，意味着 **2014 年中后期他已加入 2ndQuadrant**。
- **早期代表作**：
  - **Logical Decoding**（PG 9.4，2014-12 发布）：WAL 级别的逻辑变更抽取框架。Andres 是主要 author/committer。这成为后来 pglogical、BDR、logical replication（PG 10 内置）等一系列特性的基础设施。
  - **Replication Slots**（PG 9.4）：与 Robert Haas 紧密合作（commit 858ec118，2014-02-01，作者 rhaas）。
- **PG 9.4 中的角色**：postgresql.org 官方 NEWS 中 replication 相关改进的多个核心 patch 由 Andres 提交。

### 2. Citus Data / EDB 时期（2014 – 2019）

- **Citus Data 参与路径**：根据 LinkedIn 历史，他曾在 LinkedIn 自述里同时标记 "Senior Database Architect at EnterpriseDB" 与 "Advisor for Citus Data"。这意味着他同时在 EDB 和 Citus 之间扮演角色。
- **与 Citus 的协作模式**：在 PGConf.EU 2015 自述里直接列出 "EDB, Citus Data, 2ndQuadrant" 为前雇主；他既是 Citus 的技术顾问，又以 EDB 身份参与上游 PG 工作。
- **Citus 商业目标 vs 上游 PG**：从他在 2017-06-21 邮件列表的发言 "Citus isn't a patched version of postgres anymore, but an extension" 可知，到 2017 年 Citus 已经完全重构为 PG 扩展架构，与上游 PG 的演化冲突大幅减少，他能更深度参与上游开发。
- **PG10/11/12 期间贡献**：作为 logical replication 的主要推动者之一，他在 PG10（logical replication 内置）、PG11/12 中持续完善订阅/发布机制、initial table sync、流式解码等子系统。

### 3. 加入 Microsoft（2019-01 – 至今）

- **2019-01-24**：Microsoft 官方博客宣布收购 Citus Data（azure.microsoft.com/en-us/blog/microsoft-and-citus-data-...）。
- **2019-01-24 ZDNet 报道**：Citus 团队整体转入 Microsoft，包括 Andres Freund 在内。
- **当前角色**：根据 PGConf.EU 2024 演讲页："At Microsoft he works full time on upstream PostgreSQL"——这意味着 **他的 Microsoft 工作完全用于上游 PostgreSQL 贡献**，而非 Azure PostgreSQL 商业产品。
- **资源影响**：Microsoft 提供的稳定薪资使他能够 100% 投入上游工作，包括 AIO 这种多年期的大型 patchset 推动。这是 Citus 时期无法做到的。

### 4. 与 Tom Lane 的关键交互年份（按主题）

| 年份 | 主题 | 证据 / 性质 |
|---|---|---|
| 2014 | ALTER TABLE 表空间 + unlogged table BUG #10675 | 邮件列表，Andres 直接 push 修复并 Tom Lane 确认 |
| 2017-03-31 | heap/index_form_tuple 重构 | 邮件 id 20170331175037，Andres → Tom Lane |
| 2017-06-21 | pgindent（re-indent HEAD）讨论 | 邮件 id 20170621213914；Andres 解释 Citus 作为扩展不受影响 |
| 2018-09-26 | printf("%m") 行为讨论 | 邮件列表，Andres → Tom Lane、Michael Paquier、Thomas Munro |
| 2022-11-02 | spinlock on loongarch64 | 邮件 id 20221102210452；典型底层架构扩展讨论 |
| 2024-07-01 | LogwrtResult contended spinlock | Alvaro → Tom Lane, Andres Cc'd（spinlock 性能关键路径） |
| 2024-07-07 | core.autocrlf / Meson configure | 邮件 id 20240707060727；Andres 与 Tom 讨论 Meson 切换的 eol 处理 |
| 2025-03-20 | OAUTHBEARER / OAuth 2.0 | 邮件列表，Andres → Tom Lane、Bruce Momjian、Jacob Champion |
| 2026-03-27 | Buffer locking 与 AIO writes | 邮件列表，Andres ↔ Melanie Plageman、Thomas Munro、Robert Haas、Heikki Linnakangas |

**与 Tom Lane 的关系**：从邮件风格来看，Andres 与 Tom Lane 是高频技术对话者，但 **不是对抗性的**——很多邮件是共同审查、达成共识的设计讨论。spinlock / Meson 等争议中两者意见大多收敛。

---

## 三、关键贡献维度

### A. Asynchronous I/O（AIO）——多年代最大工程

- **思想起源**：AIO 讨论最早可追溯到 Andres 在 PG12 时代（2019–2020）的博客与邮件列表。
- **2022-10-29**：他将 AIO patchset 的独立子集（relation extension / BufferAlloc 重构）作为独立 commit 先合入主线。
- **2023–2024**：与 Thomas Munro 联合主导大型 patchset 推入 commitfest；包含 sync / worker 两种实现。
- **2024–2025**：io_uring 路径（Linux 5.6+）作为高效选项被加入。
- **2025-09-25 PG18 发布**：AIO 正式作为默认 I/O 子系统，参数 `io_method` 提供 sync / worker / io_uring 三选。
- **2026-03 至今**：仍持续处理 buffer locking 与 AIO writes 的细节修正（邮件列表活跃讨论）。

### B. Meson Build System 切换

- **2024-07-07 邮件**：Andres 邮件 id 20240707060727 中讨论了 meson configure 阶段的 canary 文件 eol 检查。
- **2024–2025**：Meson 成为 PG18 的可选/默认构建系统（与 autoconf 并行 → 逐步取代）。
- **Andres 角色**：与 Peter Eisentraut 等共同推动，PG18 中 Meson 已经达到生产可用状态。

### C. Logical Replication（逻辑复制）

- **2014 PG 9.4**：logical decoding 框架（基础 API）。
- **2017 PG 10**：logical replication 内置（publication/subscription）。
- **2018–2021**：在 PG11/12/13/14 中持续优化 initial sync、streaming、conflict handling。
- **2022–2025**：支持 PG16/17 logical replication on subscriber（解码侧改进）。

### D. UUIDv7

- **2024–2025**：在 PG18 中引入原生 `uuidv7()` 函数与 `uuidv4()` 对应。
- **设计动机**：解决 UUIDv4 作为主键时索引插入性能问题（无序导致 B-tree page split）；UUIDv7 含 Unix 毫秒时间戳前缀，索引性能接近自增整数。
- **Andres 角色**：是 PG18 中 UUIDv7 推广者之一（具体 author/reviewer 比例在 release notes 中可查证；多源中文解读均把 UUIDv7 与 AIO 并列）。

### E. JIT 改进

- **2022-03-21**：与 Magnus Hagander 邮件讨论 `jit_warn_above_fraction` 参数。
- **PG15/16 期间**：Andres 持续投入 JIT 与 costing 的协作改进（cfbot 警告处理）。
- **PG17 释放**：JIT 改进作为 PG17 性能改进的一部分被纳入。

### F. Snapshot Scalability 改进（PG14）

- **2020 Citus Blog**："improvements I recently contributed to Postgres 14, significantly reducing the identified snapshot scalability bottleneck"——这是 Andres 自己撰写的总结，明确说明 PG14 中大幅缩小的 snapshot scalability 瓶颈来自他的工作。
- **2021-09 PG14 发布**：包含此项改进。

---

## 四、2024 – 2026 最新动态（重点）

### 2024 年关键事件

1. **2024-03-29：CVE-2024-3094（XZ 后门）发现**。Andres 在调查 Debian 系统 SSH 登录延迟问题时，定位到 xz/liblzma 5.6.0/5.6.1 中 Jia Tan 植入的供应链后门。该发现对 Linux 发行版、CI/CD 供应链影响深远，被广泛认为是 2024 年最重要的开源安全事件之一。
2. **2024-04-02**：Microsoft 官方发布 XZ Utils FAQ，强调 Andres Freund 是该 CVE 的发现者。
3. **2024-07**：推动 Meson build system 在 PG18 成熟化。
4. **2024-09-26**：PG17 发布。

### 2025 年关键事件

1. **2025-03-20**：与 Tom Lane、Jacob Champion 共同推进 OAuth 2.0 / OAUTHBEARER 联邦认证（PG18 关键特性）。
2. **2025-04-11**：CVE-2025-1094（pg_encoding_set_invalid()）commit，Andres 作为 reviewer。
3. **2025-09-25**：**PostgreSQL 18 正式发布**——AIO、UUIDv7、虚拟生成列、OAuth 2.0、SKIP SCAN、truncated heap tuples 优化等。
4. **2025-10-16 ~ 2025-10-20**：中国 PG 社区（IvorySQL / ITPUB）多场 PG18 直播、解读活动。
5. **2025-10-25**：PG 18.4.1 Windows 安装包发布。

### 2026 年关键事件（截至 6 月 19 日）

1. **2026-03-13 ~ 2026-03-27**：pgsql-hackers 列表中持续密集讨论 AIO buffer locking、index prefetching。
2. **2026-04-19**：Google Cloud 公布其对 PostgreSQL 上游贡献（与 Andres 工作无直接绑定，但属同生态同期活动）。
3. **2026-06-04**：**PostgreSQL 19 Beta 1 正式发布**。Anarazel 在 commitfest 仍深度活跃。
4. **当前状态（2026-06-19）**：从邮件列表活跃度推断，Andres 仍为 PG 核心 committer，Microsoft 角色未变，主要投入上游 AIO 后续 / buffer locking / index prefetching 等 PG19 候选特性。

---

## 五、与关键 committer 的合作

| 合作对象 | 主要协作内容 | 典型年份 |
|---|---|---|
| Tom Lane | pgindent / Meson / buffer locking / spinlock / heap tuple 重构 / printf("%m") / OAuth | 2014–2026 持续 |
| Robert Haas | replication slots / PG 10 logical replication 设计 | 2014–2019 |
| Heikki Linnakangas | AIO 接口 / index AM / buffer locking | 2020–2026 |
| Thomas Munro | AIO 主合作者（io_uring、worker mode、cross-platform） | 2022–2026 |
| Noah Misch | 安全 CVE / 测试覆盖 / 编码安全 | 2018–2026 |
| Peter Geoghegan | B-tree / index prefetching | 2017–2026 |
| Amit Kapila | logical replication PG 14–16 演进 | 2018–2022 |
| Peter Eisentraut | Meson / SSL / 编码 | 2018–2026 |
| Nathan Bossart | 原子操作 / 性能 patch | 2023–2026 |
| Melanie Plageman | AIO buffer locking / read stream | 2024–2026 |

---

## 六、奖项与公开露面

- **PostgreSQL Core Team**：2020-11-08 当选（与 Jonathan Katz 一同）。
- **PGConf.EU 多次演讲**：2012（MultiMaster Replication）/ 2015 / 2016 / 2024 等均列于议程页。
- **PGCon 演讲**：重复发言人（PGConf 自我描述 "Repeat speaker at PGCon, PGConf EU"）。
- **行业媒体露面较少**：相对低调，不常接受 The Register / InfoWorld 等媒体专访；行业曝光主要集中在邮件列表与技术博客。
- **xz 后门事件后**：短暂成为开源安全话题焦点（微软 / Red Hat / Ars Technica 均有提及）。

---

## 七、找不到 / 不确定的信息（明确标注）

| 信息项 | 状态 |
|---|---|
| Andres Freund 的具体出生年月 | **未找到** |
| 何时正式成为 PostgreSQL committer（具体日期） | **未找到**——推测 2014–2015 之间（Citus bio 自述 "PostgreSQL hacker, committer, and core team member"） |
| 何时加入 EnterpriseDB（具体年月） | **未找到**——仅 LinkedIn 显示 EDB 段，Citus 列为 Advisor |
| 何时加入 Microsoft 的精确日期 | **未找到**——2019-01-24 收购公告 + LinkedIn "2019 –" |
| 与 Tom Lane 的具体 spinlock "争议" 是否存在 | **未找到正式争议记录**——邮件列表显示为高质量技术讨论，未发现明显冲突 |
| AIO 的最初 RFC 时间 | **未找到**——最早公开 commit 是 2022-10-29 relation extension 重构，但 RFC 时间可能更早 |
| Andres 是否担任过 PG 任何 release 的 Release Manager | **未找到记录** |
| 2026 年内具体演讲 / 媒体露面 | **未找到 2026 年独立演讲记录**——主要活动集中在邮件列表与 commit |

---

## 八、当前定位（2026-06 视角）

- **职衔**：Principal Software Engineer @ Microsoft（Microsoft 上游 PostgreSQL 团队）
- **社区身份**：PostgreSQL Core Team member（2020-11 入选）、committer
- **持续投入方向**：AIO 后续 / buffer locking / index prefetching / PG19 候选特性
- **对生态影响最大的事件**：2024-03-29 发现 CVE-2024-3094（xz 后门）
- **对 PG18 影响最大的贡献**：AIO 子系统（与 Thomas Munro 共同主导）
- **风格标签**："Likes details too much"（Citus bio 自述），这意味着他在 patch 评审与设计讨论中偏向深度技术审查而非宏观愿景。

---

## 参考链接（部分，按主题分类）

### 雇主 / 身份
- LinkedIn 自述：https://www.linkedin.com/in/andres-freund
- PGConf.EU 2012 bio：https://www.postgresql.eu/events/pgconfeu2012/schedule/speaker/140-andres-freund/
- PGConf.EU 2015 bio：https://www.postgresql.eu/events/pgconfeu2015/schedule/speaker/140-andres-freund/
- PGConf.EU 2024 bio：https://www.postgresql.eu/events/pgconfeu2024/schedule/speaker/140-andres-freund/
- Citus Data blog author 页：https://www.citusdata.com/blog/authors/andres-freund/

### 收购事件
- Microsoft Azure 官方：https://azure.microsoft.com/en-us/blog/microsoft-and-citus-data-providing-the-best-postgresql-service-in-the-cloud/
- ZDNet 报道：https://www.zdnet.com/article/microsoft-buys-citus-data/

### 关键发布
- PG 9.4：https://www.postgresql.org/about/news/1557/
- PG 17：https://segmentfault.com/a/1190000045326525
- PG 18 正式发布：https://www.postgresql.org/about/news/postgresql-18-released-3142/
- PG 19 Beta 1：https://www.postgresql.org/about/news/postgresql-19-beta-1-released-3313/

### xz 后门事件
- 微软 FAQ：https://www.163.com/dy/article/IUPF9RSS0511BLFD.html （网易转载微软 FAQ）
- 新浪微博（事件复述）：https://www.weibo.com/6045441276/O7nOP45Vv
- CVE-2024-3094 描述：https://www.postgresql.org/support/security/（PG 安全页面未列，但属 xz 通用 CVE）

### 邮件列表关键 thread
- 2014-10-20 BUG #10675：https://www.postgresql.org/message-id/20141020220150.GI7176@awork2.anarazel.de
- 2017-03-31 heap_form_tuple：https://www.postgresql.org/message-id/20170331175037.6hyokophw74pabpc@alap3.anarazel.de
- 2017-06-21 re-indent HEAD：https://www.postgresql.org/message-id/20170621213914.y4iu65kbwkctleeh@alap3.anarazel.de
- 2018-09-26 printf %m：https://www.postgresql.org/message-id/20180926174645.nsyj77lx2mvtz4kx@alap3.anarazel.de
- 2022-03-21 JIT warning：https://www.postgresql.org/message-id/20220321235048.wb3ymun6lbi33b2u@alap3.anarazel.de
- 2022-10-29 relation extension refactor：https://www.postgresql.org/message-id/20221029025420.eplyow6k7tgu6he3@awork3.anarazel.de
- 2022-11-02 spinlock loongarch64：https://www.postgresql.org/message-id/20221102210452.ydontvnukjrkewp6@awork3.anarazel.de
- 2024-07-07 Meson / autocrlf：https://www.postgresql.org/message-id/20240707060727.hymsmyu2wvx3o2h3@awork3.anarazel.de
- 2024-10-16 popcount AVX512：https://www.postgresql.org/message-id/ZxAqRG1-8fJLMRUY@nathan
- 2025-03-20 OAUTHBEARER：https://www.postgresql.org/message-id/wbqaa72xxfnqtsspanbteoycmtpb6oshtwbrm7uwiw3pur4ll4@tybxmaasfjkv
- 2026-03-13 buffer locking：https://www.postgresql.org/message-id/52d064b8-63bd-45df-a405-b6017d49b300@gmail.com
- 2026-03-17 index prefetching：https://www.postgresql.org/message-id/CAH2-WzkyG01682zwqyUTwV=Zq+M_qGgi1NbXwp1H-piRSfJsgQ@mail.gmail.com
- 2026-03-27 buffer locking AIO writes：https://www.postgresql.org/message-id/q6trx7a5vd3j5tddamwxahrojopboov6eeue2jkjmfpkhdfgjj@w3hapotwxroo

### Other
- PG Weekly News 2020-11-08（核心团队入选）：https://www.postgresql.org/about/news/postgresql-weekly-news-november-8-2020-2105/
- Citus blog "improvements I recently contributed to Postgres 14"：https://www.citusdata.com/blog/authors/andres-freund/
- CVE-2025-1094 commit：https://github.com/postgres/postgres/commit/db3eb0e8256a7089d16cb6ed1ea7a65654c0e105

---

**调研完成时间**：2026-06-19
**总节点数**：38（≥ 15–20 要求）
**调研边界声明**：所有 2024–2026 事件均通过网络搜索验证，未直接读取 git.postgresql.org 全量 shortlog（搜索受限）；commit 数量级、AIO 的具体 commit 列表建议进一步通过 git log --author=andresfreund 验证。
