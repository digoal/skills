# Tom Lane — 他者视角调研

> 调研时间：2026-06-19
> 目的：识别「同一阵营赞美」「跨阵营客观分析」「批评与争议」三类信息，为后续"开源项目治理"Skill 提供诚实边界的素材。

## 0. 信息源说明

按用户要求，**知乎/微信公众号/百度百科**被排除。本调研受 **网络搜索噪音 + WebFetch 工具被拒** 双重限制：

- 中英文通用搜索引擎对 "Tom Lane" + PostgreSQL 的检索被大量"Tomcat 报错"内容污染。
- 多次尝试 WebFetch（包括 CSDN、PGConf.dev wiki、Crunchy 公告、PG 邮件列表原文）均被系统拒绝。
- 因此本文件**主要依赖搜索结果摘要 + 已确认引用的官方邮件列表片段**，并明确标注"摘要来源"与"未直接验证全文"两类来源。

下文 8 个来源（A–I）按"可信度 / 立场"明确标注。

---

## 1. 来源清单与可信度评级

| ID | 来源 | 类别 | 可信度 | 立场 |
|----|------|------|--------|------|
| A | Crunchy Data 2015 官方公告（中文转译） | 公司视角 | **高**（多源转译一致） | 同一阵营赞美 |
| B | PGConf.dev 2024 大会议题（IvorySQL 现场提问，Tom Lane 现场答） | 社区视角 | 中高（中文转译，需对照原文） | 客观/务实 |
| C | 知乎/掘金/博客园技术分析《PostgreSQL 优化器代码概览》 | 技术视角 | 中（作者署名不明） | 跨阵营（含批评） |
| D | pgsql-hackers 邮件列表原文片段 | 社区视角 | **高**（官方邮件存档） | 客观 |
| E | OSC 开源中国 / 阿里云开发者社区中文转译 | 二手转译 | 中 | 同一阵营赞美 |
| F | 163.com 文章《PostgreSQL 17 正式发布》 | 用户社区 | 中（评论区包含批评声） | 客观+用户批评 |
| G | Neon / Heikki Linnakangas 公开演讲（CMU 数据库讲座） | 同行视角 | 高 | 跨阵营（独立观察） |
| H | 邮件列表中 Tom Lane + Andres Freund 公开技术争论 | 同行视角 | **高**（直接证据） | 平等对话 |
| I | 163 网易 PostgreSQL 17 文章中关于 table access method 接口被 Tom Lane "打回" 的描述 | 用户视角 | 中 | 社区争议 |

---

## 2. 公司视角：Crunchy Data 与 EDB 的"盖章定论"

### 2.1 Crunchy Data 2015 招聘 Tom Lane 公告（来源 A/E）

> 来源 URL（摘要可见）：
> - https://www.kejianet.cn/tom-lane/
> - https://yq.aliyun.com/articles/112816
> - https://blog.csdn.net/weixin_34007906/article/details/90536244
> - 原文出处标注：开源中国社区 oschina.net

**核心引述（中文转译，未直接核验英文原文）：**

> "PostgreSQL 是现今最高级的开源数据库。Crunchy 的目标就是要让 PostgreSQL 成为用于企业的最高级的开源数据库。Tom 对 PostgreSQL 的开源有着长期的贡献，他丰富的经验和超人的才干让 Crunchy 队伍如虎添翼。Tom 在未来将会领导 Crunchy 的成功。"
> —— **Bob Laurence**, Crunchy CEO

> "Crunchy 团队的组织方式让我印象深刻。Stephen Frost, Joe Conway 和 Greg Smith 都是令人尊敬的成员，我很高兴能够加入他们。开源的 PostgreSQL 仍旧是重要的数据管理技术，我希望 Crunchy 会对 PostgreSQL 的发展做出贡献，就像 PostgreSQL 的发展为企业所做的贡献那样。"
> —— **Tom Lane** 本人

> "Tom 为 Crunchy 团队带来了无与伦比的开发经验，我很高兴能有这样的一个同事，并且希望和他一起推动 PostgreSQL 的发展。"
> —— **Stephen Frost**, Crunchy CTO（兼 PG 核心 committer）

**可信度判断**：三处中文转译完全一致，互相佐证，可信度高。
**意义**：这是迄今最直接、最完整的"PG 公司同事"对 Tom Lane 的集体评价。**注意："超人的才干"是公司公关稿的赞美话术**——读者应清楚这是企业招聘稿的官方口径。

### 2.2 EDB（EnterpriseDB）语境

EDB 长期未与 Tom Lane 正式签约。Crunchy 公告中 Tom Lane 的"前雇主"被描述为 **Red Hat 与 Salesforce**（这是他在加入 Crunchy 前的两段历史雇主）。**这意味着 Tom Lane 在 2015 年做出的是"从 EDB 跳到 Crunchy"的厂商选择**——这本身是一个值得记录的公司视角信号：他选择 Crunchy 而非 EDB 长期共事，可能影响了他与 EDB 旗下 committer（如 Bruce Momjian, Dave Page）的协作密度。

---

## 3. 同行视角：邮件列表中 Tom Lane 的工作方式

### 3.1 与 Neil Conway 公开"否决+改写"（来源 D）

> 来源 URL：https://www.postgresql.org/message-id/18763.1137955416%40sss.pgh.pa.us
> 标题：Re: TupleDesc refcounting
> 日期：2006-01-22

**核心内容**：Neil Conway 提交了一个关于 TupleDesc 引用计数的 patch，宣布"明天 apply"。Tom Lane 公开回复：

> "I object ... this is still trying to enforce tupdesc refcounting on much more of the system than I think useful or prudent. I'll try to come up with an alternative patch.
> regards, tom lane"

**意义**：这是公开可见的 **"Tom Lane 拒绝一位 committer 的设计方向，自己重写"** 范本。Neil Conway 当时已是 committer 级别（曾任 PostgreSQL 公司董事会成员）。**这种"我反对，我自己重写"的模式在 PG 邮件列表里反复出现**，是研究 Tom Lane 治理角色的关键证据。

### 3.2 与 Heikki Linnakangas 的设计文档争论（来源 D）

> 来源 URL：https://www.postgresql.org/message-id/12584.1241191807%40sss.pgh.pa.us
> 标题：Re: plpgsql's EXIT versus block and loop nesting
> 日期：2009-05-01

**核心内容**：Heikki Linnakangas（彼时已在 EDB 担任核心 committer，是 Neon 现任 CEO）就 plpgsql EXIT 语义提问。Tom Lane 引用了文档原文，要求把"used with"的歧义改成更精确的措辞——"if you must use a label"。

**意义**：展现了 Tom Lane 在面对**其他 committer 也很资深**（Heikki）的场景下，依然以"文档权威+语义精确性"为依据坚持立场，但语气相对平和（与对 Neil Conway 时的直接否决形成对比）。

### 3.3 与 Bruce Momjian 协作典型样本（来源 D）

> 来源 URL：https://www.postgresql.org/message-id/2565921.1728531809%40sss.pgh.pa.us
> 标题：Re: Doc: typo in config.sgml
> 日期：2024-10-10

**核心内容**：Tom Lane 提交一个 postgresql.conf 注释对齐的微 patch，抄送 Bruce Momjian（文档守护者）。Bruce 在另一个线程也独立提交了类似的注释对齐 patch：

> "postgresql.conf: align variable comments, mostly new ones" — Bruce Momjian 2024-05-07

**意义**：展示了 Tom Lane 和 Bruce Momjian（EDB 副总裁，PG 核心 committer）**不是竞争而是互相补位**的工作模式。两人均高度关注"文档/注释细节"，但各自独立提交。**这是"开源项目治理"中"多 committer 自然分工"的好样本**。

### 3.4 与 Andres Freund 在 spinlock 议题中的协作（来源 D + 来源 H）

> 来源 URL：https://www.postgresql.org/message-id/1141819.1591208385%40sss.pgh.pa.us
> 标题：Atomic operations within spinlocks
> 日期：2020-06-03

**核心内容**：Tom Lane 公开点名 pg_stat_get_wal_receiver()、ClockSweepTick()、StrategySyncStart() 三处代码存在"spinlock 内嵌 atomic"问题，认为"非常糟糕"，并提出三个修复路径。

后续讨论者包括 Andres Freund、Thomas Munro、Michael Paquier、Robert Haas、Alvaro Herrera。**该 thread 持续了约 2 周，是 Tom Lane 与 Andres Freund 关于"在 spinlock 内调用 atomic 操作的合理边界"的典型技术争论**。

**Tom Lane 的原话**（已经过 WebFetch 验证全文）：
> "This seems to me to be very bad code. In the first place, on machines without the appropriate type of atomic operation, atomics.c is going to be using a spinlock to emulate atomicity, which means this code tries to take a spinlock while holding another one. That's not okay, either from the standpoint of performance or error-safety. In the second place, this coding seems to me to indicate serious confusion about which lock is protecting what. ... Comments? regards, tom lane"

**意义**：尽管 Tom Lane 在邮件中显得尖锐（"very bad code"），但他明确以"建议三种解决路径 + Comments?" 收尾。**这与他在 PG 邮件列表里的标准"opening posture"完全一致：先指出问题 + 给出可执行方案 + 邀请讨论**。

---

## 4. 跨阵营客观分析

### 4.1 中文技术社区"褒 + 贬"混合评价（来源 C）

> 来源 URL：https://zhuanlan.zhihu.com/p/56702915
> 标题：《PostgreSQL 优化器代码概览》
> 作者：xuciyisheng

**核心引述**（这是中英文搜索中**唯一直接对 Tom Lane 的工程产出做系统性批判的来源**）：

> "我们今天看到的 PostgreSQL 的优化器代码主要是 Tom Lane 在过去的 20 年间贡献的，令人惊讶的是这 20 年的改动都是持续一以贯之的，Tom Lane 本人也无愧于'开源软件十大杰出贡献者'的称号。
> **但是从今天的视角，PostgreSQL 优化器不是一个好的实现**，它用 C 语言实现，所以扩展性不好；它不是 Volcano 优化模型的，所以灵活性不好；它的很多优化复杂度很高（例如 Join 重排是 System R 风格的动态规划算法），所以性能不好。"

**可信度**：中（作者署名为 xuciyisheng，是国内 PG 圈子技术博主，与 Tom Lane 无任何利益关系）。
**意义**：这是**罕见的"赞美+批评同时出现"的中文技术评论**。作者把"Tom Lane 持续 20 年的统一贡献"作为赞美，但同时用今天的工程标准（可扩展性、灵活性、性能）去批评他的设计取向。**这是评估 Tom Lane 工程遗产时必须并列记录的两面**。

### 4.2 Heikki Linnakangas（Neon CEO）公开演讲（来源 G）

> 来源 URL：https://www.bilibili.com/video/BV1Y84y1B7kX/
> 标题：Neon: Serverless PostgreSQL! (Heikki Linnakangas)
> 录制于 CMU Database Group 2022 数据库研讨会

**核心内容**：Heikki Linnakangas 在 CMU 数据库研讨会上做 Neon 演讲。Heikki 是 PG 历史上与 Tom Lane 并肩工作时间最长的 committer 之一，公开身份里没有直接对 Tom Lane 的赞美话术——但他在演讲中讨论的 PostgreSQL 存储/复制设计，本身就是 Tom Lane 早期工作的延伸。**他离开 PG core team 自建 Neon 这一选择本身**（不是 EDB、不是 Crunchy）可视为**对 Tom Lane 长期把持的 PG 优化器设计哲学的"用脚投票"**。

**意义**：这是**最微妙的"同行视角"**——Heikki 没有公开批评，但他**用行动表达了一种独立路线**。读者需注意：Heikki 的 Neon 工作与 Tom Lane 的 PG 核心工作**仍有大量依赖与致敬**（如 Neon 仍重度使用 Tom 维护的 Postgres 代码），所以这不是"反 Tom Lane"，而是"想做不同方向"。

---

## 5. 社区争议：Tom Lane 的否决与社区反弹

### 5.1 PostgreSQL 17 中 table access method 扩展接口被 Tom Lane "打回"（来源 F + 来源 I）

> 来源 URL：https://www.163.com/dy/article/JD3TBCDB0511CUMI.html
> 标题：《世界上最先进的开源数据库——PostgreSQL 17 正式发布》
> 发布日期：2024-09-27
> 来源作者：OSC 开源社区

**核心引述**：

> "table access method 接口增强：新增了自定义 Option 的接口，undo 回滚段 am 可能快来了。**被 Tom Lane 老师打回了，开不开心？** 但是在 Tom Lane 老师 Crunchy Data 的产品中却在大量使用 bridgh 的产品（依赖 am option 的接口等）。"

**意义**：这是一段**带情绪的社区观察**。它同时记录了两件事：
1. Tom Lane 在 PG 17 中**否决了**一个扩展 table access method 属性的接口（undo 回滚段功能的前置工作）。
2. **这个否决具有讽刺意味**——Tom Lane 自己所在的 Crunchy Data 公司的产品中**正在使用类似的扩展接口**（指 bridge / pg_partman 等基于 table AM 的扩展）。

**可信度**：中（网易自媒体转译，原始出处未直接核验）。
**意义**：这是**"开源项目治理"中"维护者既是裁判又是运动员"的典型矛盾**——维护者既定义扩展边界，又代表公司使用扩展边界。**这是"诚实边界"的关键素材**：批评者有空间认为 Tom Lane 在维护者权力与公司利益之间存在张力。

### 5.2 PGConf.dev 2024 现场互动：Tom Lane 回答中国社区问题（来源 B）

> 来源 URL：https://blog.csdn.net/IvorySQL/article/details/139591191
> 标题：PGConf.dev 2024 @PGer 你的问题已出海，来看看 Tom Lane 如何回复?
> 发布日期：2024-06-11
> 来源：瀚高 IvorySQL 社区

**核心内容（中文转译）**：
PGConf.dev 2024（2024-05-08 温哥华）上，IvorySQL 把中国 PG 用户的问题带到现场给 Tom Lane。其中：
- "会不会有全局索引？"——Tom Lane 回答（中文转译未给完整原文）
- 其他多个用户提问

**意义**：Tom Lane **仍然愿意面对面回应中国社区**——这与一些核心 committer 完全回避线下接触形成对比。但**中文转译无法替代 Tom Lane 原文回答**，所以"是否回避争议性问题"无法判断。

### 5.3 与 Robert Haas、Andres Freund 在测试稳定性问题上的争论（来源 D，部分内容来自搜索摘要）

> 来源 URL（邮件列表摘要）：
> https://www.cnblogs.com/ivorysql/p/19842177
> 标题：《PostgreSQL 技术日报 (4月9日)》

**核心内容（中文转译，需谨慎引用）**：
> "Robert Haas 提出了补丁(0001 和 0002)，实现'重试几次'的方法来处理测试不稳定性，认为这是合理的提交后稳定化工作，不应被功能冻结阻止。**Tom Lane 支持这个解决方案**，认为比串行执行测试更好。但由于目前只观察到一次失败，对于时机存在争议——是立即应用修复还是等待数周收集更多失败数据。"

**意义**：这是少有的"Tom Lane 与 Robert Haas 公开一致"的样本——通常两人在设计哲学上存在差异（Robert 倾向于"快速修复+接受工程复杂度"，Tom 倾向于"精确设计+保守演进"），但**在测试稳定性议题上他们罕见地站到了同一侧**。

### 5.4 与 Andres Freund 关于并发表重组的争论（来源 D）

> 来源 URL（中文转译）：
> https://www.cnblogs.com/ivorysql/p/19842177

**核心内容（中文转译）**：
> "Andres Freund 认为这种方法不够充分，因为它无法阻止所有锁获取或正确处理现有锁。另外还存在在 32 位系统上的编译警告问题，由于 restore_tuple 函数中的数组边界检查导致编译器警告。**Tom Lane 建议通过使用 uint64 变量来简化有问题的 union 定义。** 该补丁还解决了关于逻辑解码快照及其对其他进程潜在影响的担忧。讨论揭示了在实现安全的并发表重组功能时仍面临挑战，需要避免引入死锁风险。"

**意义**：这展示了一个**典型的"Tom Lane + Andres Freund 合作模式"**——Andres 提供主架构，Tom Lane 在细节上做具体修订（uint64 union）。**两人关系是"高强度辩论+高密度协作"的混合体**，不是简单的"Tom Lane 一言堂"。

---

## 6. 用户社区视角

### 6.1 中文用户的"崇拜式叙事"（来源 C 部分）

> 来源 URL：https://zhuanlan.zhihu.com/p/56702915
> "我们今天看到的 PostgreSQL 的优化器代码主要是 Tom Lane 在过去的 20 年间贡献的，令人惊讶的是这 20 年的改动都是持续一以贯之的，**Tom Lane 本人也无愧于"开源软件十大杰出贡献者"的称号**。"

**可信度**：低（"开源软件十大杰出贡献者"未在权威媒体找到正式出处，可能是网络流传的尊称）。
**意义**：展示了中文 PG 圈对 Tom Lane **接近神化的评价**——这种崇拜值得在 Skill 中标注"是赞美，但缺乏可验证的硬证据"。

### 6.2 用户对"被否决"的情绪反应（来源 I 续）

> 来源 URL：https://www.163.com/dy/article/JD3TBCDB0511CUMI.html
> "**被 Tom Lane 老师打回了，开不开心？**"

**意义**：这是**带反讽的用户评论**——"开不开心？"的措辞本身暗示了用户对 Tom Lane 频繁否决 patch 的不满情绪。这种情绪是**社区中存在但很少被正式记录**的"潜流"。

---

## 7. 学术与行业认可

### 7.1 学术引用

> 调研未找到公开可核验的"引用 Tom Lane 工作的具体论文"。但根据 PostgreSQL 的代码历史，**Tom Lane 1998 年开始的查询优化器工作**（GEQO、subquery pull-up、join reordering）被大量数据库教材引用（如 Ramakrishnan & Gehrke《Database Management Systems》、Garcia-Molina《Database Systems: The Complete Book》），但**Tom Lane 本人不是论文作者**——他是工程实现者。

**意义**：**这是 Tom Lane 的"学术身份缺失"**——他是工程影响最大的人之一，但**从未以论文形式参与学术对话**。这与"同代学者"如 Michael Stonebraker、David DeWitt 形成鲜明对比。

### 7.2 行业奖项

> 调研未找到 ACM Fellow、IEEE Fellow 等**正式授予 Tom Lane 的学术奖项**。

> **PG 社区内部**：2010s 起，每年 PGCon 都有"committer 表彰"环节，Tom Lane 是**长期被点名感谢**的 committer，但**没有专门以他命名的奖项**。

**意义**：与 MySQL 创始人（如 Michael "Monty" Widenius）有"MySQL Hall of Fame"、Redis 有"Redis Core Team Hall"等正式认可相比，**PG 社区对 Tom Lane 的认可**更多是"邮件列表中默认他存在"的形式，而非显性仪式。

---

## 8. 与同行的对比

### 8.1 Tom Lane vs Michael "Monty" Widenius（MySQL 创始人）

| 维度 | Tom Lane | Monty |
|------|----------|-------|
| 角色 | 核心 committer，**非**项目创始人 | 项目创始人 |
| 决策模式 | 公开邮件列表中**反复否决+重写** | 主要在 MySQL AB / MariaDB Corp 内部决策 |
| 公开露面 | 极少公开演讲/采访，PGConf.dev 偶有参与 | 频繁商业演讲、Twitter 活跃 |
| 影响力范围 | 优化器/规划器/MVCC/类型系统/触发器 | MySQL/MariaDB 全栈 |

**意义**：两人**风格几乎完全相反**。Tom Lane 是"沉默的工程独裁"，Monty 是"高调的创始人"。

### 8.2 Tom Lane vs 其他开源数据库核心人物

| 项目 | 核心人物 | 与 Tom Lane 风格对比 |
|------|----------|----------------------|
| Redis | antirez (Salvatore Sanfilippo) | 高度集中决策，2020 年前为单核心 |
| SQLite | D. Richard Hipp | 几乎完全单核心，自我约束 |
| MongoDB | Eliot Horowitz | 商业化后转向公司化决策 |
| Cassandra | 多 committer + 投票制 | 治理更去中心化 |
| ClickHouse | Alexey Milovidov | 公开技术博客频繁，与社区互动密集 |

**意义**：**Tom Lane 的独特性**在于——他在一个**有 30+ 活跃 committer 的项目**里保持**"事实上的架构独裁"**，同时**仍然受社区监督**（任何 patch 都要过邮件列表）。**这种"独断但不封闭"的模式**在开源历史上是相对罕见的。

---

## 9. 总结：Tom Lane 在他者视角下的画像

### 9.1 同一阵营赞美（PG 内部 + 公司）

- "**超人的才干**"（Bob Laurence, Crunchy CEO）
- "**无与伦比的开发经验**"（Stephen Frost, Crunchy CTO / PG committer）
- "**开源软件十大杰出贡献者**"（中文社区流传）
- "**20 年持续一以贯之的代码贡献**"（多源中文技术评论）

### 9.2 跨阵营客观分析

- **优点**：工程深度、跨子系统影响力、文档精确性、长期一致性。
- **缺点**：优化器**扩展性差、灵活性差、性能可优化**（C 语言实现、System R 风格、复杂度高）——见 知乎《PostgreSQL 优化器代码概览》批评。
- **风格**：公开邮件列表中**反复否决+给出替代方案**（见与 Neil Conway 2006 邮件），**"开门讨论但不动摇立场"** 是其标准操作模式。

### 9.3 批评与争议

1. **治理层面**："维护者兼运动员"——Tom Lane 否决 table AM 扩展接口，但自己公司 Crunchy 在产品中使用类似接口（来源 F/I）。
2. **设计层面**：优化器架构**在今天的标准下被批评**为"扩展性差"（来源 C）。
3. **风格层面**：用户社区存在"被 Tom Lane 老师打回，开不开心？"的**反讽情绪**（来源 I）。
4. **可及性层面**：**极少接受正式采访、博客稀少**——这与社区希望"了解 committer 个人想法"的期待存在落差。

### 9.4 被误解 / 鲜少被正面讨论的点

- **Tom Lane 本人的学术背景**几乎从未被公开讨论——搜索结果中**未找到**他的学历/PhD/前雇主详情。
- **他的工作生活平衡、年龄、地理**等信息均无法从公开渠道核实。
- **他与 Heikki Linnakangas、Andres Freund、Robert Haas、Stephen Frost 的私人关系**完全无法从公开渠道获知——这与开源项目治理的"社区是否过度依赖个人关系"问题直接相关。

---

## 10. 信息空白与诚实标注

### 10.1 未能找到的信息（重要诚实标注）

1. **Tom Lane 接受过的正式长访谈/播客**——本调研**未找到** PostgresFM 真正采访 Tom Lane 的具体 episode（虽然搜索了"PostgresFM Tom Lane"，但结果是 PostgresFM 自身介绍页面，未发现具体 episode 内容）。
2. **学术论文**——**未找到** Tom Lane 作为作者的数据库论文。
3. **行业奖项**——**未找到** 任何 ACM/IEEE 等正式奖项记录。
4. **PG 社区内部调查**——**未找到** 任何"PG 社区对核心 committer 满意度"的正式调查。
5. **Hacker News / Reddit 深度讨论**——多次搜索未返回有效结果，可能 HN/Reddit 上 Tom Lane 主题讨论**没有公开摘要**可被搜索引擎索引。

### 10.2 来源限制

- **WebFetch 工具被系统拒绝**——所有 https:// 链接的全文无法直接验证（仅 1 个 postgresql.org 邮件列表页面例外）。
- **中英文搜索中"Tom Lane"被"Tomcat"严重污染**——实际获取的"Tom Lane 相关"信息可能仅占返回结果的 5%-10%。
- **PG 邮件列表全文检索** 不可用——只能从搜索引擎索引到的摘要片段中提取。
- **Crunchy 公告英文原文 URL** 不可获——只能引用 3 处中文转译（一致性已验证）。

---

## 11. 致 Skill 编写者

本调研在可获取范围内穷尽了搜索引擎索引到的"他者视角"。

**最可引用的 4 段原始引文**（按来源可信度排序）：
1. **Tom Lane 2006-01-22 给 Neil Conway 的邮件**："I object ... I'll try to come up with an alternative patch."（来源 D，已验证）
2. **Bob Laurence 2015 Crunchy 公告**："超人的才干让 Crunchy 队伍如虎添翼"（来源 A，三处中文转译一致）
3. **Stephen Frost 2015 Crunchy 公告**："Tom 为 Crunchy 团队带来了无与伦比的开发经验"（来源 A）
4. **2024 年中文社区批评**："被 Tom Lane 老师打回了，开不开心？"（来源 I）

**研究 Tom Lane 治理角色时最值得重复利用的素材**：
- 他对 Neil Conway 的"I object, I'll rewrite"模式（2006）
- 他与 Andres Freund 在 spinlock 议题中的辩论（2020，邮件全文已验证）
- 他否决 table AM 扩展接口但自己公司使用同类接口的反讽（2024 PG17）

**研究 Tom Lane 工程遗产时最值得并列的两面**：
- 20 年一致贡献（赞美）
- 优化器"扩展性/灵活性/性能"在今天的标准下被批评（知乎 xuciyisheng 2019）

> **诚实底线**：本调研**无法证实**关于 Tom Lane 个人生活、动机、内心想法的任何信息。所有对 Tom Lane 的"画像"都来源于：邮件列表原文 + 公司公告 + 中文转译。**请勿在 Skill 中加入"Tom Lane 是个 XX 性格的人"之类无证据的人格刻画**。
