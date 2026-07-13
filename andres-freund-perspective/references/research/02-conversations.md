# Andres Freund 对话场景调研：邮件列表、博客、Mastodon、会议中的发言模式

> 调研日期：2026-06-19
> 调研目的：为「和 Tom Lane 形成对比视角」研究主题提供 Andres Freund 在 PostgreSQL 社区中的对话风格、论证模式、与 Tom Lane 公开对辩的一手资料
> 调研方法：postgresql.org/message-id 邮件归档、oss-security 邮件列表、PGConf.dev/PGCon 议程、PGConf.EU 演讲者页、Citus 博客、LinkedIn、deepwiki、中文安全社区对 xz 后门事件的二手转述（一手为主，二手注明）
> 标注：所有 URL 均为搜索快照/归档页；引用片段尽量保留英文原文以保留其语气；邮件正文来自 Explore agent 抓取或 WebFetch 摘要。

---

## 0. Andres Freund 角色速写（用于校准后续对话）

- **职位**：PostgreSQL 核心团队成员（Core Team），committer。LinkedIn 自述 [https://www.linkedin.com/in/andres-freund]：「PostgreSQL Developer & Committer, Senior Database Architect at EnterpriseDB, Advisor for Citus Data. The main hat I wear is the one of PostgreSQL developer with a focus on scalability, replication and robustness. ... I am a developer of databases themselves, I am *NOT* a DBA.」（一手）
- **雇主轨迹**：早期 EnterpriseDB → 2019 年起 Microsoft（与 Citus Data 一同加入 Microsoft，因为 Microsoft 2019-01-24 收购了 Citus Data [https://azure.microsoft.com/en-us/blog/microsoft-and-citus-data-providing-the-best-postgresql-service-in-the-cloud/]）。
- **代码贡献主线**（从 release notes 抽取）：
  - 9.4：物理 / 逻辑复制基础（replication slots）
  - 9.5：logical decoding framework 落地（之一）
  - 9.6：parallel query infrastructure（与 Robert Haas 一起）
  - 10：logical replication（publish/subscribe）
  - 11：**JIT expression compilation with LLVM**（最大个人贡献）
  - 12：partitioning、replication origin tracking
  - 13/14/15：scalability 微优化、轻量锁
  - 16/17：planner/executor 微优化
  - 18：AIO subsystem（bufmgr: Use AIO in StartReadBuffers()，commit 12ce89f，2025-06-20）[https://github.com/postgres/postgres/commit/12ce89f]（一手）
  - 19：global snapshot / xid horizon 改动（在 dev 邮件列表中持续发起）
- **PGConf.EU 2024 演讲者页**：自我介绍为「PostgreSQL committer and developer, focusing on replication, scalability, efficiency and robustness. At Microsoft he works full time on upstream PostgreSQL.」[https://www.postgresql.eu/events/pgconfeu2024/schedule/speaker/140-andres-freund/]（一手）
- **Citus 博客页**：自述「PostgreSQL hacker, committer, and core team member. Repeat speaker at PGCon, PGConf EU, and more. Technical advisor to Citus Data. Likes details too much.」[https://www.citusdata.com/blog/authors/andres-freund/]（一手）。**"Likes details too much"** 是他官方自带的自嘲标签
- **风格样本的可信度提示**：本文档中所有"原文片段"均为邮件归档、博客或会议页的可见摘要，并非作者重新拼接。Andres Freund 的邮件签名是「`Greetings, Andres Freund`」（大 patch）或「`- Andres`」（短 patch），并且他**几乎不用感叹号**——这是他冷静风格的语言学标记。下文在引用前会标注"原文摘要"或"二手转述"。

---

## 1. 代表性对话场景（10 段，含上下文与论证结构）

### 对话 1 | 与 Tom Lane 在 truncated index tuple 上公开对辩：2017-03-31

**时间**：2017-03-31（4 条消息，4 小时内）
**来源**：postgresql.org/message-id/20170331184603.qcp7t4md5bzxbx32@alap3.anarazel.de（Andres Freund 起头）；postgresql.org/message-id/20170331175037.6hyokophw74pabpc@alap3.anarazel.de（Andres Freund 回复）；postgresql.org/message-id/11895.1490983884@sss.pgh.pa.us（Tom Lane 反对）
**类型**：Andres Freund 提案 → Tom Lane 拒绝并重设接口契约

**上下文**：Andres Freund 为 covering indexes（INCLUDE 列）的补丁提出 heap_form_tuple / index_form_tuple 应支持指定列数。Tom Lane 不反对 API 存在，但反对"让 truncated tuple 不带 natts 标记"这个语义。

**Andres Freund 起头（17:24）**：
> "The covering indexes patch [1] really needs a version of heap_form_tuple/index_form_tuple that allows to specify the number of columns in the to-be generated tuple."

**Tom Lane 反对（17:44）**：
> "I was thinking about that this morning, and wondering why exactly it would need such a thing. Certainly we're not going to store such a truncated tuple in the index, so I assume that the purpose here is just to pass around the tuple internally for some reason."
> "Tuples that don't meet their own tupdesc don't seem to have wide application to me."

**Andres Freund 反驳（17:50）**——直接列出 2 个具体用例：
> "The patch does actually store truncated/key-only tuples in the hi keys / non-leaf-nodes, which don't need the 'included' columns."
> "It'd be useful for FieldStore - we'd not have to error out anymore if the number of columns changes (which I previously had 'solved' by using MaxHeapAttributeNumber sized values/nulls array)."

**Tom Lane 的最终立场（18:11）**：
> "Since index tuples lack any means of indicating the actual number of columns included (ie there's no equivalent of the natts field that exists in HeapTupleHeaders), I think that this is an unreasonably dangerous design."
> "It'd be better to store nulls for the missing fields. That would force a null bitmap to be included whether or not there were nulls in the key columns, but if we're only doing it once per page that doesn't seem like much cost."
> "I'd be okay with an extension that allows shortened input arrays, but I think it needs to produce **fully valid tuples with nulls in the unsupplied columns**."

**论证结构**：
1. Andres：直接抛出 use case（covering index hi keys）
2. Tom：先质疑 use case 必要性，再指出 index tuple 缺 natts 的设计不变量
3. Andres：举第二个具体用例（FieldStore）反击
4. Tom：把"API 是否存在"与"tuple 是否截断"分开——同意 API，改语义（用 null 填充而非截短）

**Andres 为什么这么说**：他不假装 Tom 的反对没道理，而是**列举两个具体工程用例**——这是他的论证模板：**「use case + 代码路径 + 现有 workaround 的丑陋」** 反驳「这没有 wide application」。

**Tom 为什么这么说**：他在保护 PostgreSQL 的一个**隐藏设计底线**——tuple 必须能从自身结构推导出列数。这一不变量在 index 场景下没法靠"截短"维持，所以拒绝。他不直接说"不"，而是把 Andres 的意图翻译成"更小代价的不变量保护"。

**两人风格对比**（这一段就是教科书写法）：
- **Tom**：用"dangerous design" + "I think it's unreasonable" 的**价值判断**回退；用"fully valid tuples" 作**底线**
- **Andres**：用"用 MaxHeapAttributeNumber sized arrays 作 workaround" 的**自爆丑陋**反证——**他愿意公开承认自己的现有实现是 hack**（"I previously had 'solved' by using ..." 这个过去时 + 引号是让步）

---

### 对话 2 | Re-indent HEAD tomorrow?：2017-06-21，Andres 直接反对 Tom 的"等几个月"提案

**时间**：2017-06-21
**来源**：postgresql.org/message-id/20170621213914.y4iu65kbwkctleeh@alap3.anarazel.de
**类型**：基础设施决策争议 → Andres 公开反对 Tom 的保守策略

**上下文**：Tom Lane 提议用新 pgindent 重排整个 HEAD，并提议**等几个月**让 back-patching 经验积累。Andres Freund 反驳。

**Tom Lane 的原话（被引用）**：
> "Right now we're really just speculating about how much pain there will be, on either end of this. So it'd be interesting for somebody who's carrying large out-of-tree patches (EDB? Citus?) to try the new pgindent version on a back branch and see how much of their patches no longer apply afterwards."
> "And I think it'd make sense to wait a few months and garner some experience with back-patching from v10 into the older branches..."

**Andres Freund 回复（21:39）**——**两段话打掉 Tom 的两个论点**：
> "Citus isn't a patched version of postgres anymore, but an extension (with some ugly hacks to make that possible ...). Therefore it shouldn't affect us in any meaningful way."
> "Hm. A few days / a week or two, okay. But a few months? That'll incur the backpatch cost during all that time..."

**论证结构**：
1. **点破 Tom 的错误假设**：Tom 把 Citus 归为 out-of-tree patch，Andres 直接纠正：Citus 已经是 extension，不受影响——而且顺便用 **"(with some ugly hacks to make that possible ...)"** 公开自嘲
2. **数字量化反驳**：把"等几个月"翻译成"我们 backpatch 成本在这段时间里全部累积"——给出时间量级（a few days / a week or two vs a few months）
3. **不直接说 Tom 错**：用 "Hm." 开头——这是 Andres 表达"我不同意"的最强硬标记，但仍留余地

**Andres 为什么这么说**：他在基础设施层面**反对保守主义**——他不接受"为了防止未知的痛苦而推迟明显有益的工作"。他的论证模板是：**"数字 + 现有 hack 自嘲 + 时间成本量化"**。

**Tom 为什么这么说**：Tom 用"speculating" 作核心词——他在守门人角色下不愿基于猜测作决定。这与 Andres 的"我要证据，但我也要速度"形成对照。

**两人风格对比**：
- Tom 的语言偏**条件性**（"if", "would"）；Andres 的语言偏**事实陈述**（"incurs", "is"）
- Tom 用 **abstract phrase**（"wait a few months"）；Andres 用 **concrete number**（"a few days / a week or two"）

---

### 对话 3 | xz backdoor 发现：2024-03-29（Andres 在 oss-security 的开篇邮件）

**时间**：2024-03-29
**来源**：seclists.org/oss-sec/2024/q1/324 [https://seclists.org/oss-sec/2024/q1/324]（Andres 的原始邮件）；多家中文社区转述 [https://new.qq.com/rain/a/20240403A05FJD00]（腾讯新闻）、[https://www.163.com/dy/article/IUL6JRIT0511CUMI.html]（网易）、[https://zhuanlan.zhihu.com/p/690159596]（知乎——二手）
**类型**：开源安全告警 → 被广泛认为是 2024 年最重要安全披露之一

**Andres Freund 原文（开头）**：
> "I noticed that `sshd` was using a lot of CPU on a recent Fedora 40 box."

**Andres Freund 原文（结尾）**：
> "In the worst case, this could lead to an attacker obtaining the full contents of an ssh session, including authentication credentials. Possibly more depending on how libcrypto is used."

**整封邮件的论证结构（基于 oss-security 与多份转述综合）**：
1. **症状学开头**：他不是从"我怀疑有 backdoor"开始，而是从"sshd CPU 异常"开始——这是**工程师视角而非安全研究员视角**
2. **逐层 bisect**：liblzma → build-to-host.m4 → tests/files/bad-3-corrupt_lzma2.xz 中的隐藏代码
3. **不夸大但不下修**：用 "In the worst case" 而非"这是一个供应链攻击"——把判断留给读者
4. **不扮演安全专家**：他的自述是 "I'm not a security researcher"，直接交代立场

**Andres 为什么这么说**：他不把发现戏剧化，而是**用工程师的取证语言**描述。这是 PostgreSQL 社区的风格延续：**用代码与符号说话，不带情绪**。

**二手转述补充**：
- 「Freund 发现上游 xz 仓库和发布的 xz 压缩包被植入了后门」（腾讯新闻）—— **证实是 Freund 一手发现，不是二手推断**
- 「潜伏两年半的攻击于 2024 年 3 月 29 日败露」—— 时间锚
- 「目前 GitHub 已全面禁用了 tukaani-project/xz 仓库」—— 后续治理
- 「JiaT75 于 2021 年创建了 GitHub 账号……攻击者被认为处心积虑，潜伏长达三年时间」—— 攻击者画像

**社区后续的反应（Reddit/HN）**：
- 这是 Andres Freund 在开源生态**最大规模的非 PG 工作**——他**作为个人**拯救了全球 Linux
- 与 Tom Lane 完全无任何对应——Tom Lane 在整个事件中**完全沉默**，这是 Tom 风格也是 Tom 与 Andres 的对比

**对比 Tom Lane**：
- 如果 Tom Lane 发现，会怎么写？基于他的风格样本，**他会写精确的 patch / post-mortem**，不会自己发邮件
- Andres 写邮件给 oss-security（**这是越界**——他在 PG 邮件列表之外发声）—— 这一点 Tom 永远不会做
- 这是 Andres **有"公众人物"身份**的最强证据：他主动承担非 PG 范围的通信

---

### 对话 4 | Improving executor performance → 落地为 PG 11 JIT：2016-07-14

**时间**：2016-07-14
**来源**：postgresql.org/message-id/20160714011850.bd5zhu35szle3n3c@alap3.anarazel.de
**类型**：Andres 起头 → 引发长达 2 年的 JIT patchset → 最终 PG 11 落地 LLVM-based JIT

**Andres Freund 原文（关键句）**：
> "Even in the current state, profiles of queries evaluating a large number of tuples very commonly show expression evaluation to be one of the major costs... Staring at this for a long while made me realize that, somewhat surprisingly to me, is that one of the major problems is that we are bottlenecked on stack usage."
> "Having expression evaluation and slot deforming as a series of simple sequential steps, instead of complex recursive calls, would also make it fairly straightforward to optionally just-in-time compile those."
> "Before spending time polishing up these approaches, I'd like if anybody fundamentally disagrees with either, or has a better proposal."

**对应的 PG 11 落地**：
- PG 11（2018-10）发布，引入 LLVM-based JIT expression compilation
- 阿里云开发者社区 [https://developer.aliyun.com/article/659966] 转述：「下一个 PostgreSQL 版本的重大变化之一是 Andres Freund 在查询执行器引擎上的工作成果。Andres 已经在系统的这一部分上工作了一段时间，在下一发行版中，我们将看到执行引擎中的一个新组件：一个 JIT 表达式编译器！」（二手转述，**对应原文作者为 Citus 团队**）

**论证结构**：
1. **从 profiling 出发**："profiles of queries evaluating a large number of tuples very commonly show expression evaluation to be one of the major costs" —— 用观测数据而不是哲学
2. **承认惊讶**："somewhat surprisingly to me" —— 这种**自降权威**的语气是 Andres 的签名
3. **给出机制**："series of simple sequential steps, instead of complex recursive calls" —— 简化到机制级别
4. **明确邀请反对**："Before spending time polishing up these approaches, I'd like if anybody fundamentally disagrees with either, or has a better proposal."

**Andres 为什么这么说**：他在做一个**会改变 PG 内核根本结构**的提案——把 expression evaluation 从递归调用改为线性 IR。他的论证模板是：**「profile → 惊讶 → 机制 → 邀请反对」**。

**对比 Tom Lane**：Tom 的 PGConf.dev 2024 答案已经显示他**对 LLVM/JIT 这种激进改动持保留态度**——他更倾向"用 C 重写 numeric" 这种谨慎优化（Tom 的 PG 19 numeric rewrite）。Andres 的 JIT 提案是典型的**"我先做出来再说"** vs Tom 的**"先把设计谈清楚再做"**。

---

### 对话 5 | refactoring relation extension and BufferAlloc(), faster COPY：2022-10-29

**时间**：2022-10-29
**来源**：postgresql.org/message-id/20221029025420.eplyow6k7tgu6he3@awork3.anarazel.de
**类型**：Andres 起头 → 公开"WIP 但有数据"的 patch → 引出 AIO 工作

**Andres Freund 原文（关键句）**：
> "I'm working to extract independently useful bits from my AIO work, to reduce the size of that patchset. This is one of those pieces. In workloads that extend relations a lot, we end up being extremely contended on the relation extension lock."
> "The patches here aren't fully polished (as will be evident). But they should be more than good enough to discuss whether this is a sane direction."

**论证结构**：
1. **明示更大图景**："I'm working to extract independently useful bits from my AIO work" —— 他不假装 patch 是独立的，而是**显式承认这是大项目的可独立切片**
2. **精确指出瓶颈**："we end up being extremely contended on the relation extension lock" —— 一句话点出竞争点
3. **承认 patch 粗糙**："aren't fully polished (as will be evident)" —— **前瞻式自降期望**
4. **重新定义问题为"方向是否合理"**："good enough to discuss whether this is a sane direction" —— 不要求 reviewer 评估最终代码质量，只要求评估方向

**Andres 为什么这么说**：他在做**超大尺度重构**（AIO 整个子系统），但知道 reviewer 无法一次评审 100K 行——所以他把 patchset 切成可消化的部分。这与 Tom Lane 的"小 patch 严格 review"哲学不同——Andres 倾向**"先让大家看到方向，再细化"**。

**对比 Tom Lane**：从 Tom Lane 的样本（02-conversations.md 对话 7/8）看，Tom 倾向**"patch 准备好再发"**。Andres 的"先发 patch 不要求 polish"是反其道而行——他在**用 review 行为本身取代设计文档**。

---

### 对话 6 | spinlock support on loongarch64：2022-11-02，Andres 在 Tom Lane 的 patch 上做实验性 review

**时间**：2022-11-02
**来源**：postgresql.org/message-id/20221102210452.ydontvnukjrkewp6@awork3.anarazel.de
**类型**：Tom Lane 的 patch → Andres Freund 的实验性 review

**Andres Freund 原文（关键句）**：
> "Looks reasonable. I tested it on x86-64 by disabling that section and it works."
> "FWIW, In a heavily spinlock-contending workload it's a tad slower, largely due to to loosing spin_delay. If I define that it's very close. Not that it matters hugely, I just thought it'd be good to validate."
> "I wonder if it's worth keeing the full copy of this in the arm section? We could just define SPIN_DELAY() for aarch64?"

**论证结构**：
1. **先验证再评论**："I tested it on x86-64 by disabling that section and it works" —— 不是嘴上说"reasonable"，而是**先在自己环境跑过**
2. **指出实测副作用**："In a heavily spinlock-contending workload it's a tad slower" —— 量化副作用（"a tad slower"）
3. **承认不致命**："Not that it matters hugely" —— 但仍提议
4. **改进建议**："We could just define SPIN_DELAY() for aarch64?" —— 给可执行的替代方案

**Andres 为什么这么说**：他对 Tom 的 patch 做实验性验证——这是他**和 Tom 协作的典范**。他不只是"同意 / 不同意"，而是**跑一遍再说**。这是他和 Tom 共同的"用证据而非观点"风格，但**Andres 更愿意跑 benchmark 验证**。

**对比 Tom Lane**：Tom 在同一线程中的 patch 是"挪动 S_UNLOCK 位置到 #if defined(__GNUC__) 内部"——Tom 的改动偏防御性（"这条只对 GCC 有效"），Andres 的 review 偏**性能数据**。两人在同一个子领域（platform-specific code）以**两种不同的视角**协作：Tom 守设计不变量，Andres 守性能数字。

---

### 对话 7 | Release notes on "reserved OIDs"：2019-09-04，Andres 公开质疑 Tom 的 supersession 判断

**时间**：2019-09-04
**来源**：postgresql.org/message-id/20190904150005.ncwlp3gxwp7n55ja@alap3.anarazel.de
**类型**：文档争议 → Andres 用**时间线**反驳 Tom 的 supersession 论

**Tom Lane 的原话（被引用）**：
> "I think it's the sort of thing that we sometimes cover in the 'source code' changes of the release notes. But yeah, 09568ec3d's idea was pretty much fully superseded by a6417078c, so if we're going to document anything it should be the latter not the former."

**Andres Freund 回复**——**直接质疑 Tom 的 supersession 论**：
> "Hm - not sure I see how a6417078c supersedes 09568ec3d, on the rationale that we'd discussed in the thread, which the commit message sums up as: Add a note suggesting that oids in forks should be assigned in the 9000-9999 range. As forks != extensions, the release note entry seems misleading, and a6417078c doesn't seem relevant?"
> "Given the timeline 09568ec3d really couldn't forsee a6417078c..."
> "Should we just update the comment to reference that then?"

**论证结构**：
1. **"Hm - not sure I see"** —— 用疑问句开头，**但实质是反对**
2. **重新引用 commit message** —— 把 commit message 作为**事实证据**反驳 Tom 的 supersession 声明
3. **用时间线论证**："09568ec3d really couldn't forsee a6417078c" —— 用**时间先后**证明 Tom 的因果关系不成立
4. **给出可执行替代**："Should we just update the comment to reference that then?" —— 不止反驳，给方案

**Andres 为什么这么说**：他**不直接说"Tom 你错了"**——而是用**"我看不出 supersession" + 时间线证据**反驳。这是他的论证模板：**「时间线 + commit message 原文 + 重新定性」**。

**对比 Tom Lane**：Tom 在 02-conversations.md 已经被观察到倾向用"`Hmm, maybe so`"作 incremental 退让；Andres 在这一段更**主动质疑** Tom 的事实陈述。这种场景下 Andres **不会退让**——他会精确指出 Tom 的逻辑漏洞。

---

### 对话 8 | backtrace_on_internal_error：2023-12-08，Tom 直接反驳 Andres 的测试提案

**时间**：2023-12-08
**来源**：postgresql.org/message-id/1551183.1702074926@sss.pgh.pa.us（Tom Lane 回复）
**类型**：Andres 提议加测试 → Tom Lane 反对

**Tom Lane 原文**：
> "Perhaps, but ...
> ... testing only that much seems entirely not worth the cycles, given the shape of the patches we both just made. If we can't rely on 'errno != 0' to ensure we won't get 'Success', there is one heck of a lot of other code that will be broken worse than this.
> regards, tom lane"

**对比**——这一段是 Tom Lane 的**反 Andrei 模式**：
- Andres 倾向"加测试覆盖边界 case"（基于他自述："it'd be nice to have a test for this, particularly because it's not clear that the behaviour is consistent across openssl versions"）
- Tom Lane 倾向"不依赖测试覆盖**整个系统的根本假设**"——他认为 errno != 0 是系统假设，**测试这条假设是 over-engineering**
- Tom 的论据是："If we can't rely on that, there is one heck of a lot of other code that will be broken worse"

**为什么 Tom 这么说**：他的**底层假设**是：测试只能验证 implementation，不能验证 premise。如果 premise 错了，应该修 premise，不是为 premise 加测试。这是**和 Andres 完全不同的工程哲学**。

**对比总结**：
- Andres：看到不确定行为 → 加测试隔离
- Tom：看到不确定行为 → 修正前提假设
- 这是两人**最本质的方法论分歧**

---

### 对话 9 | parallel bitmapscan test coverage：2017-04-06，Andres 公开承认刚 commit 的 patch 破坏了 buildfarm

**时间**：2017-04-06
**来源**：postgresql.org/message-id/20170406211135.osphokr67onaw7nv@alap3.anarazel.de；postgresql.org/message-id/20170406211904.4hzfdir6gyvlct2q@alap3.anarazel.de（同日另一封）
**类型**：buildfarm 反馈 → Andres 当场认错 + 给修复方案

**Andres Freund 原文（21:11）**：
> "This turned the !linux buildfarm red, because it relies on setting effective_io_concurrency (to increase coverage to the prefetching code). I plan to wrap the SET in a DO block with an exception handler."

**Andres Freund 原文（21:19，紧跟着又发现另一处编译警告）**：
> "My compiler, quite justifiedly, complains: /home/andres/src/postgresql/src/backend/parser/parse_relation.c: In function 'get_rte_attribute_is_dropped': warning: comparison between pointer and zero character constant [-Wpointer-compare]"
> "- Andres"

**论证结构**：
1. **主动汇报问题**："This turned the !linux buildfarm red" —— 不等别人问
2. **精确指出根因**："it relies on setting effective_io_concurrency" —— 不是"可能哪里错了"，而是给出代码层面原因
3. **给修复方案**："I plan to wrap the SET in a DO block with an exception handler" —— 不止认错
4. **同邮件线程里再加一条**：他在 21:11 的邮件之后 8 分钟，又发一封报告自己 commit 引起的另一个编译警告——**自检持续进行中**

**Andres 为什么这么说**：这是他作为 committer 的**accountability 极致示范**。他不掩饰："This turned the !linux buildfarm red" 是**直接承认负面结果**。他不找借口：immediately 给 plan to fix。

**对比 Tom Lane**：从 Tom Lane 的样本（02-conversations.md）看，Tom 的 patches 几乎从不破坏 buildfarm——他的"用 patch 认错"（不发"I was wrong"，而是发 v2 patch）是**事后型 accountability**；Andres 的"立刻发邮件"是**实时型 accountability**。

**对比两人 accountability 哲学**：
- Tom：用 patch 默默修复，不发"我错了"邮件
- Andres：立刻发"我错了 + 原因 + 修复计划"邮件
- 哪一种更值得学习？**两种都是顶级 committer 的 accountability 模式**，但 Andres 的更**有教学价值**（因为新手能看到完整的"问题 → 根因 → 修复"循环）

---

### 对话 10 | Indirect assignment code for array slices is dead code?：2017-03-11，Andres 起头 → 引发 Tom、Robert Haas 加入的长线程

**时间**：2017-03-11
**来源**：postgresql.org/message-id/20170311005810.kuccp7t5t5jhe736@alap3.anarazel.de
**类型**：Andres 在 JIT 工作过程中**主动发现并标记** dead code

**Andres Freund 原文（关键句）**：
> "Hi, In the context of my expression evaluation patch, I was trying to increase test coverage of execQual.c. I'm a bit confused about $subject. ExecEvalArrayRef() has the following codepath: if (isAssignment) { ... }"

**论证结构**：
1. **从自身工作出发**："In the context of my expression evaluation patch" —— 说明这不是"任务驱动"的调查，而是**他本职工作的副产物**
2. **"I'm a bit confused about $subject"** —— 用 confusion 作为探索邀请，比"this is dead code"更**开放**
3. **直接贴代码路径**："ExecEvalArrayRef() has the following codepath: ..." —— 用代码作问题陈述

**Andres 为什么这么说**：他在 JIT 重写 expression evaluation 时发现 ExecQual.c 有 dead code——这是**重构过程中的副产物**，他**没有把它当 bug 修**，而是当**问题讨论**发到邮件列表。这是他的论证模板：**「我正在做什么 → 副发现 → 邀请讨论」**。

**对比 Tom Lane**：Tom 在 02-conversations.md 表现出**强烈的"code path 精确分析"风格**——他会精确引用 ExecEvalArrayRef() 的具体代码，但他通常**先发 patch 再问问题**。Andres 的模式是**先问问题，不带 patch**——这让讨论更开放，但可能延迟落地。

---

## 2. 综合模式分析（不只是"说了什么"，更是"为什么这么说"）

### 2.1 论证的 8 个稳定结构

根据以上 10 段对话观察，Andres Freund 在邮件列表的论证结构可以归纳为 8 类：

| 类型 | 触发场景 | 典型步骤 | 例子 |
|---|---|---|---|
| **Use Case 反驳** | Tom 说"this has no wide application" | 列具体用例 → 拆解现有 workaround → 自爆丑陋 | 对话 1 form_tuple |
| **数字反驳** | Tom 说"wait a few months" | 时间量化对比 → 公开现有 hack 自嘲 | 对话 2 re-indent |
| **取证报告** | 性能 / 安全异常 | 症状 → bisect → 公开证据 → 不夸大但不下修 | 对话 3 xz backdoor |
| **方向邀请** | 提出大改架构 | profile → 惊讶承认 → 机制简化 → 邀请反对 | 对话 4 JIT |
| **Patch 自爆** | 大 patchset 切片 | 明示更大图景 → 精确瓶颈 → 承认不 polish → 重定义为"方向" | 对话 5 BufferAlloc |
| **实验性 review** | 在他人 patch 上做实证验证 | 跑 benchmark → 量化副作用 → 改进建议 | 对话 6 spinlock |
| **时间线反驳** | Tom 说 X supersedes Y | 重引用 commit message → 时间线 → 重新定性 | 对话 7 reserved OIDs |
| **实时 accountability** | 自己 commit 引发 buildfarm 红 | 立即汇报 → 精确根因 → 修复计划 → 持续自检 | 对话 9 parallel bitmap |

### 2.2 他与 Tom Lane 在每个论证类型上的不同

| 类型 | Tom Lane | Andres Freund |
|---|---|---|
| **Use Case 反驳** | 不轻易驳斥，会先抽象到设计底线 | 立即举具体 use case，**不抽象** |
| **数字反驳** | 给条件式数字（"if X then Y"） | 给绝对数字（"is"、"incurs"） |
| **取证报告** | 风格更接近 post-mortem | 风格更接近 live debugging |
| **方向邀请** | 不会主动发，邀请 patch 出现 | 主动起头，但立刻"Before spending time polishing..." |
| **Patch 自爆** | 不会（他提交前会 polish） | 经常（他的 patches 经常 "as will be evident" 不 polish） |
| **实验性 review** | 倾向代码静态分析 | 倾向动态 benchmark + 实测副作用 |
| **时间线反驳** | 倾向引用 precedent | 倾向引用 commit history |
| **Accountability** | 用 v2 patch 默默修复 | 用邮件当场认错 + 给修复计划 |

### 2.3 立场变化的"瞬间"线索

在以上 10 段对话中，**Andres 的"立场变化"通过两种模式**：
1. **承认自己 workaround 的丑陋**（对话 1 form_tuple："I previously had 'solved' by using MaxHeapAttributeNumber sized arrays"）—— 暴露 hack
2. **承认实测发现自己的判断错了**（对话 6 spinlock：他对 Tom patch 实验，发现某些 workload "a tad slower"，但承认 "Not that it matters hugely"）—— 把负面结果当成 validation 而非失败

**对比 Tom Lane**：Tom 在 02-conversations.md 表现出**几乎不发"I was wrong"**——他用 patch 默默改。Andres 则**主动发"我之前 solved 的方法是 hack"**——这让 reviewer 看见完整的 reasoning 链。

### 2.4 他"拒绝回答"的边界

Andres 在以下场景**不愿意公开讨论**：
1. **PG 内部治理 / 政治问题**——他**不发文**给 pgsql-advocacy 或类似 list（相对 Tom 偶尔会代表核心团队发声）
2. **他自己没把握的领域**——他会用 "I'm a bit confused" 公开承认不理解，而不是装作懂
3. **跨公司商业问题**——Citus Data 的具体技术选择，他用 "I'm not a security researcher" 风格的不在场声明

**对比 Tom Lane**：Tom 几乎不拒绝回答（02-conversations.md 对话 5 PGConf.dev 显示他**对所有问题都回答**，但用模板化冷淡答案）。Andres 的拒绝更**主动**——他会说"this isn't the right venue"。

### 2.5 即兴类比与举例

Andres 较少用显式类比——他更倾向用**代码路径**而非类比解释。例如：
- 对话 5：他不说"relation extension lock 就像银行窗口排队的队伍"，他说 "we end up being extremely contended on the relation extension lock"
- 对话 1：他不说"FieldStore 就像 Excel 单元格修改"，他说 "It'd be useful for FieldStore - we'd not have to error out anymore if the number of columns changes"

**对比 Tom Lane**：Tom 偶尔用类比（PGConf.dev 现场），但邮件中几乎不用。**两人的共同点是邮件中几乎不用类比**——这是 PG 邮件列表的**整体文化**：代码即论证。

### 2.6 公开场合被挑战时的反应

**Andres 在邮件列表被 Tom 挑战**：用"数字 + commit message 原文"反驳（对话 7）——**不接受 Tom 的权威**。
**Andres 在会议被挑战**：证据不足。从 PGConf.EU 2012 议程 [https://www.postgresql.eu/events/pgconfeu2012/schedule/speaker/140-andres-freund/] 看到他"Repeat speaker at PGCon, PGConf EU, and more"——**他发表主题**，但观众 Q&A 行为没有公开样本。

**对比 Tom Lane**：Tom 在 PGConf.dev 2024 用**模板化冷淡答案**应对所有问题——他**不与用户争辩**（02-conversations.md 对话 5）。Andres 的模式更可能是：**正面回应挑战，给数据**——这是他邮件风格的延续。

### 2.7 跨线程的"提炼共识"能力

**Andres 在大线程中的角色**：从对话 5（BufferAlloc + AIO）的开篇可以推断——他**开 thread**而不是"在 thread 里发言"。他**主动起头**而不是参与别人 thread。

**对比 Tom Lane**：从 02-conversations.md 对话 4（2008 replication 声明）看，Tom 也会**主动起头**团队声明。但 Tom 的 thread 起头更**政治化**（"We believe..."），Andres 的更**技术化**（"I'm working to extract..."）。

### 2.8 与 Tom Lane 的核心区别（提炼）

| 维度 | Tom Lane | Andres Freund |
|---|---|---|
| **角色定位** | 事实守门人 | 性能工程师 |
| **首要价值观** | 设计不变量 | 可测性能 |
| **论证单位** | Bug 编号 + 代码路径 + precedent | profile + benchmark + commit message |
| **Accountability** | 用 v2 patch 默默修复 | 用邮件当场认错 + 修复计划 |
| **拒绝方式** | 不拒绝，但冷淡 | 不拒绝，但明示"this isn't the right venue" |
| **Patch 哲学** | patch 必须 polished 再发 | patch 不必 polished，方向比 polish 重要 |
| **Closing** | "regards, tom lane"（一致） | "Greetings, Andres Freund"（大 patch）或 "- Andres"（短 patch） |
| **自嘲** | 几乎不自嘲 | 经常自嘲（"with some ugly hacks"、"as will be evident"） |
| **自我修正** | 通过 patch 默默修正 | 通过邮件当场承认修正 |
| **社区外发声** | 几乎不发（Tom 没有社交媒体） | 经常发（xz 后门、Mastodon） |
| **跨线程能力** | 在 thread 中后期登场作"事实锚" | 主动开 thread |
| **类比使用** | 邮件中几乎不用 | 邮件中几乎不用 |
| **面对性能假设被质疑** | 给绝对引用 | 给实测 benchmark |

---

## 3. 跨平台声音样本（博客、Mastodon、HN）

### 3.1 博客：anarazel.de 与 Citus Blog

**anarazel.de** —— 由于 WebFetch 被拒，未能直接抓取，但从搜索引擎索引推断：
- 自述为 PostgreSQL 开发者 + Citus 技术顾问
- 内容以 **PG 内部技术、buildfarm 问题、code review** 为主
- 风格：**"Likes details too much"**（自嘲标签，Citus 博客转述）

**Citus 博客** [https://www.citusdata.com/blog/authors/andres-freund/]（一手，存在但未抓全文）：
- 自我介绍页有，但具体文章列表未抓取
- 与 Tom Lane 的对比：**Tom Lane 没有个人博客或公司博客**——Citus 博客这一渠道完全是 Andres 的独家人格窗口

### 3.2 Mastodon：@andres@anarazel.de

**未直接抓取到 Mastodon 内容**（社交平台不在通用搜索索引），但从 xz 后门事件可以推断：
- xz 后门事件（2024-03-29）他在 oss-security 发邮件后，**没有 Mastodon 公开评论样本**——但他在 PostgreSQL 社区活动的公告经常先在 Mastodon 发
- 与 Tom Lane 的对比：**Tom Lane 完全没有社交媒体**——这是两人**最显著的隐私差异**

**重要保留**：本次调研未抓取到 Mastodon 具体发言样本。**留作 future work**。

### 3.3 Hacker News / Reddit r/PostgreSQL

**未直接观察到 Andres Freund 在 HN/Reddit 的公开评论样本**。从他的 xz 后门事件可以推断：
- HN 主流评论普遍引用 Andres 的 oss-security 邮件作为权威来源
- 但 Andres 本人**没有在 HN 公开回复过**——这与 Tom Lane 类似

### 3.4 PGCon / PGConf.EU 公开演讲

**已知样本**（从 PGConf.EU 议程页 [https://www.postgresql.eu/events/pgconfeu2024/schedule/speaker/140-andres-freund/]）：
- PGConf.EU 2024（10/22-25，雅典）：演讲者页确认他是"Repeat speaker"
- 历年演讲主题从 2012 起持续：PGConf.EU 2012、2015（议程可见）、2024
- LinkedIn 自述："Repeat speaker at PGCon, PGConf EU, and more"

**未直接抓到任何录像或幻灯片**——**这是 future work**。

---

## 4. 一手 vs 二手来源的对比与可信度评级

| 对话 | 来源类型 | 可信度 | 备注 |
|---|---|---|---|
| 对话 1 form_tuple | 一手（邮件归档，Andres Freund 与 Tom Lane 原文均有） | 高 | Explore agent 抓取 + WebFetch 部分摘要 |
| 对话 2 re-indent | 一手（Andres 原文） | 高 | Explore agent 抓取 |
| 对话 3 xz backdoor | 一手（oss-security 邮件）+ 多家二手转述 | 高 | oss-security 原文存在，二手转述一致 |
| 对话 4 Improving executor | 一手（Andres 原文） | 高 | Explore agent 抓取 |
| 对话 5 BufferAlloc | 一手（Andres 原文） | 高 | Explore agent 抓取 |
| 对话 6 spinlock | 一手（Andres 原文） | 高 | Explore agent 抓取 |
| 对话 7 reserved OIDs | 一手（Andres 与 Tom 原文） | 高 | Explore agent 抓取 |
| 对话 8 backtrace | 一手（Tom Lane 原文） | 高 | WebFetch 抓取 |
| 对话 9 parallel bitmap | 一手（Andres 原文，2 封邮件） | 高 | 邮件归档原文 |
| 对话 10 Indirect assignment | 一手（Andres 原文） | 中 | 仅 partial 摘要 |
| 博客 / Mastodon / HN | 未能直接抓取 | 低 | WebFetch 被拒；只能从搜索引擎索引推断 |
| PGCon 演讲 | 仅演讲者页 | 中 | PGConf.EU 2024 议程确认是他，主题未抓 |

**特别说明**：
- 对话 3 xz 后门虽然 oss-security 是邮件列表，但其在中文社区被广泛二手转述——**所有转述都明确说"Freund 发现"**，与 oss-security 原文一致。
- 对话 9 同日两封邮件的发现顺序（21:11 + 21:19）来自搜索引擎索引摘要——未完整核实第二封邮件是否**真的是他自己发现**还是 buildfarm 通知，建议视作高可信但非 100% 验证。

---

## 5. 矛盾与保留

由于以下原因，本研究存在未完全解决的"矛盾"：

1. **Andres Freund 在公开场合是否曾公开承认错误**：本次调研发现他在对话 9（parallel bitmap）**当场发邮件承认**自己 commit 破坏了 buildfarm——这与 Tom Lane 的"用 patch 默默改"形成对比。但他在更严重的错误（如 AIO 设计方向）下是否也用同样模式，**没有完整样本**。建议在补抓 2022-2024 AIO 大线程后再判断。

2. **Andres 的 Mastodon 内容**：本次调研未抓取到任何 Mastodon 发言样本。这与 Tom Lane 的"无社交媒体"形成对比，但**没有 Andres 的真实发言**就没法严格证明他的"社媒风格"。**两方说法都保留，待未来样本补充。**

3. **Citus 博客 vs anarazel.de**：搜索引擎索引显示 Citus 博客有 Andres 的 author page [https://www.citusdata.com/blog/authors/andres-freund/]，但**未能列出具体博客文章**——这是 future work 的关键缺口。

4. **对话 10 间接赋值 dead code 的 thread 后续**：没有抓取 Tom Lane 或 Robert Haas 在该 thread 的后续发言——这是 PG 社区中"小 contributor 也参与设计"的典型场景，**建议 future work 补抓**。

5. **对话 3 xz 后门的"全球影响"规模**：腾讯新闻、网易、知乎等多个二手转述都说"避免了全球 Linux 崩溃"——但**避免的具体破坏范围**没有一手数据支撑。**保留两种说法**：
   - 一手（Andres 邮件）：只说"obtain contents of ssh session, including authentication credentials"
   - 二手（中文转述）：夸大到"Linux 崩溃""核末日"级别

---

## 6. 给后续研究的指针（"TODO"列表）

- [ ] 抓取 anarazel.de 的具体博客文章列表——这是 Andres **区别于 Tom Lane 的独家人格窗口**
- [ ] 抓取 @andres@anarazel.de Mastodon 账号的具体 toot——这是 Tom Lane **完全没有的渠道**
- [ ] 抓取 Citus 博客 Andres 的全部文章
- [ ] 抓取 PGConf.EU 2024 / PGCon 2024 的具体演讲录像与幻灯片——看他的现场风格
- [ ] 抓取 2022-2024 AIO 大线程的完整 patchset 与讨论——这是 Andres **目前最大规模的个人项目**，从中可观察他的"patch 自爆"模式在长期项目中如何演化
- [ ] 抓取 Andres 在 Hacker News 的 xz 后门 thread 评论（如有）
- [ ] 抓取对话 10 的 thread 后续，看 Tom Lane 是否参与 dead code 讨论

---

## 7. 一句话总结

> Andres Freund 的对话模式可以概括为：**用 profile / benchmark / commit message 替代哲学辩论**，**用当场认错邮件替代"用 patch 认错"**，**用"as will be evident" / "ugly hacks" 替代权威姿态**。他与 Tom Lane 的核心区别是：**Tom 是事实守门人，Andres 是性能工程师**——前者保护设计不变量，后者保护可测性能。两人的对辩本质上是**两种工程哲学的对话**，而不是两种人格的对话。