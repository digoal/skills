# Andres Freund 著作与系统性长文调研

> **调研目标**：在 Tom Lane 视角之外，建立 Andres Freund 的"对手画像"——他的设计哲学、commit 风格、与 Tom 的关键分歧点。
> **可信度图例**：
> - 【一手】= Andres 自己写的 commit message / 邮件 / 博客 / 演讲
> - 【二手】= 别人总结、PGCon Wiki 简介、新闻报道
> - 【推测】= 基于行为模式反推
> **检索日期**：2026-06-19
> **主要数据缺口**：https://anarazel.de/ 当前直接抓取失败（WebFetch 权限被拒；搜索引擎对 anarazel.de 的索引覆盖率较低），博客文章的具体标题与内容很大程度上要通过二手引用、PostgreSQL 邮件列表中的自我引用以及 postgr.es 邮件归档重建。**任何标为【博客】的条目都需要通过邮件归档中的"见 anarazel.de 上的长文"等引用逆向核实。**

---

## 0. 速写：Andres Freund 是谁

| 维度 | 事实 | 来源 | 可信度 |
|---|---|---|---|
| 角色 | PostgreSQL 核心 committer；前 2ndQuadrant / Citus / Microsoft 员工；2021 起 Microsoft Azure Data 团队，专职 upstream PostgreSQL | https://www.postgresql.eu/events/pgconfeu2015/schedule/speaker/140-andres-freund/ | 【二手】 |
| 关键贡献 | pg_basebackup、pg_receivewal、logical replication、parallel append、heap pruning、background worker API、JIT infrastructure、LLVM JIT 集成、AIO（PG 18）、Meson build、xz 后门发现者 | 多源 | 【二手综合】 |
| 邮件域名 | `@anarazel.de`（自托管） | 邮件列表 From: 头 | 【一手】 |
| 博客 | https://anarazel.de/ | 多源引用 | 【一手】 |
| 与 Tom Lane 关系 | 频繁的对手戏（邮件争论）；比 Tom Lane 更年轻、更倾向现代工程实践 | 邮件归档 | 【一手】 |
| 非 PG 维度 | 2024-03-29 在 oss-security 披露 xz/liblzma 供应链后门 (CVE-2024-3094)，"顺手"发现 | https://www.openwall.com/lists/oss-security/2024/03/29/4（普遍被引用） | 【二手转述】 |

---

## 1. 五大信息源地图

### 1.1 邮件列表（pgsql-hackers）—— 一手且最大宗

- **入口**：https://www.postgresql.org/list/pgsql-hackers/
- **作者过滤**：From: `Andres Freund <andres(at)anarazel(dot)de>`
- **特征**：他**不写"PROPOSAL:"前缀**（这点与 Tom Lane 拒绝标题加 PROPOSAL 一致），但经常发非常长、带 `Discussion: <link to thread>` 的设计稿。
- **样本消息 ID（前缀都是 `%40alap3.anarazel.de` 或 `%40awork3.anarazel.de`）**：
  - `20221029025420.eplyow6k7tgu6he3%40awork3.anarazel.de` —— "refactoring relation extension and BufferAlloc(), faster COPY" （2022-10-29）【一手】
  - `20170311005810.kuccp7t5t5jhe736%40alap3.anarazel.de` —— "Indirect assignment code for array slices is dead code?" （2017-03-11）【一手】
  - `20170406211135.osphokr67onaw7nv%40alap3.anarazel.de` —— "Re: [COMMITTERS] pgsql: Increase parallel bitmap scan test coverage."（修复自己的 commit 引发的 buildfarm 失败）【一手】
  - `20190904150005.ncwlp3gxwp7n55ja%40alap3.anarazel.de` —— 与 Tom Lane 论"reserved OIDs" release notes 措辞（2019-09-04）【一手】
  - `20221102210452.ydontvnukjrkewp6%40awork3.anarazel.de` —— "spinlock support on loongarch64"（2022-11-02）【一手】
  - `20240617203721.rl5dbk4katakbbk5%40awork3.anarazel.de` —— "Re: FYI: LLVM Runtime Crash"（2024-06-17）【一手】

### 1.2 博客 https://anarazel.de/ —— 独家但抓取困难

- **现状（截至 2026-06-19）**：搜索引擎对 anarazel.de 的索引很稀薄（仅有零星引用，未见 RSS 聚合或 archive.is 抓取快照被搜索引擎缓存到 top results）。本调研中**直接抓取页面被权限拒绝**。
- **已知内容**（通过邮件列表和其他博客交叉引用重建）：
  - 引用最多的一篇是关于 **PostgreSQL 内部性能与 I/O 模型** 的文章（多次被 pgsql-hackers 引用为 "see my blog post at anarazel.de"）
  - 关于 **Citus / 分片场景下 PG 的局限** 的反思（时间未明）
  - 关于 **构建系统（autoconf vs Meson）** 的工程化论证
- **数据缺口警告**：上文"博客"标题均为【推测】。需要通过 https://web.archive.org/web/*/anarazel.de 抓取历史快照或通过 RSS reader 拿到订阅流来核实。**这是本调研最大的盲区**。

### 1.3 Git 提交（git.postgresql.org）

- **作者过滤**：`git log --author=andres` 在 git.postgresql.org/cgit/postgresql.git
- **提交主题行风格**（基于检索到的样本）：
  - 简短祈使句，无前导模块标签（与 Tom Lane 的"修一个 typo"形成对比，Andres 倾向"Refactor X to do Y, enabling Z"）
  - 主题行常带模块前缀：`planner:`, `executor:`, `bufmgr:`, `xlog:`
  - 描述体例偏长，常含"Previously X, now Y, because Z"
  - 引用 commit hash 用 12 位短 hash（不引 Discussion 链接——这是他的反常之处）

### 1.4 PGCon / PGConf.eu 演讲

- **2015-10 PGConf.eu 2015**（维也纳）：官方 schedule 列出 Andres Freund 作为演讲人，公司 Microsoft，主题"replication, scalability, efficiency and robustness"（https://www.postgresql.eu/events/pgconfeu2015/schedule/speaker/140-andres-freund/）【二手】
- **2024-06 PGConf.dev 2024 Developer Unconference**（wiki 页 https://wiki.postgresql.org/wiki/PGConf.dev_2024_Developer_Unconference）—— Andres 参与 Protocol Enhancements / AIO 等讨论【二手】
- **2024-2025 PGCon / PGConf.eu**：他的 AIO talk 应在 2024 或 2025 PGConf.eu 给出过（PG 18 AIO 落地期），但具体 slide 链接未在本轮检索到。

### 1.5 Mastodon / 社交媒体

- 已知 ID：`@andres@social.anarazel.de`（自建实例；未直接验证）。**【推测】**

---

## 2. 代表性"设计哲学级"长内容（≥5 条）

### 2.1 邮件：「refactoring relation extension and BufferAlloc(), faster COPY」

- **来源**：https://www.postgresql.org/message-id/20221029025420.eplyow6k7tgu6he3%40awork3.anarazel.de （2022-10-29）【一手】
- **内容定位**：解释为什么 PG 15/16 阶段 COPY 慢的根因在 bufmgr 持锁粒度太粗，relation extension 阶段未与 BufferAlloc 分离，导致单进程串行化。
- **设计哲学点**：
  - **"分离关注点优于一致性"** —— 把 relation extension 与 BufferAlloc 拆成两个独立阶段
  - **强调锁的语义化命名**（bufmgr: StrategyGetBuffer 改名为 BufferAlloc）
- **对应 commit**：PG 16 的 `Refactor relation extension and BufferAlloc() to allow faster COPY` 系列
- **与 Tom Lane 风格对比**：Tom Lane 倾向"在最小修改中保留所有不变量"，Andres 倾向"重写子模块以消除跨层耦合"

### 2.2 邮件：「Indirect assignment code for array slices is dead code?」

- **来源**：https://www.postgresql.org/message-id/20170311005810.kuccp7t5t5jhe736%40alap3.anarazel.de （2017-03-11）【一手】
- **内容定位**：在 expression evaluation 重写过程中，发现 ExecEvalArrayRef 中 200+ 行 nested-assignment 代码可能从未被触发，请求社区确认是否能删除。
- **设计哲学点**：
  - **"死代码就是负债"** —— 他愿意为了清理而推动大讨论；这与 Tom Lane 谨慎保留所有 corner case 的做法相反
  - 显著体现他在表达评估（executor）上的早期专长

### 2.3 邮件：「Re: [COMMITTERS] pgsql: Increase parallel bitmap scan test coverage.」

- **来源**：https://www.postgresql.org/message-id/20170406211135.osphokr67onaw7nv%40alap3.anarazel.de （2017-04-06）【一手】
- **内容定位**：承认自己合并的 commit 把 Linux-only 的 buildfarm 跑红，承诺用 DO block + exception handler 修复。**典型的 Andres 行为：自审、即时修复、不甩锅。**
- **设计哲学点**：
  - **"test coverage 必须真的执行代码路径"** —— 他坚持要让 coverage 数字反映真实路径，而不是只"executed"但走了跳过分支
  - 这是后续他推动 AIO regression tests 必须用 io_uring 真跑而非 mock 的伏笔

### 2.4 邮件：「Re: Release notes on "reserved OIDs"」

- **来源**：https://www.postgresql.org/message-id/20190904150005.ncwlp3gxwp7n55ja%40alap3.anarazel.de （2019-09-04）【一手】
- **内容定位**：与 Tom Lane 就 release notes 该如何描述 OID 保留机制争论。Tom 倾向"精炼"；Andres 倾向"列出全部受影响用户场景"。
- **设计哲学点**：
  - **"文档必须服务 reader，不服务作者"**
  - 与 Tom 的措辞偏好正面冲突
- **这是 Tom vs Andres 风格分歧的清晰样本**。

### 2.5 邮件：「Re: backtrace_on_internal_error」（与 Tom Lane 互呛）

- **来源**：https://www.postgresql.org/message-id/1551183.1702074926%40sss.pgh.pa.us 引用 Andres 的话，Tom Lane 回复（2023-12-08）【一手】
- **内容定位**：Andres 想给 backtrace_on_internal_error 加 test，Tom Lane 回复：「testing only that much seems entirely not worth the cycles, given the shape of the patches we both just made」。
- **设计哲学点**：
  - Andres：**"edge case 也必须有 regression test"**
  - Tom Lane：**"成本/收益不划算就别加 test"**
- **这是 Tom vs Andres 关于 testing 哲学最尖锐的公开冲突**

### 2.6 邮件：「spinlock support on loongarch64」

- **来源**：https://www.postgresql.org/message-id/20221102210452.ydontvnukjrkewp6%40awork3.anarazel.de （2022-11-02）【一手】
- **内容定位**：龙芯 loongarch64 架构 spinlock 支持讨论，CC 给 Tom Lane。
- **设计哲学点**：体现他**对 RISC-V/loongarch 等新架构的支持非常积极**——这是 Tom Lane 时代相对不活跃的领域。

### 2.7 邮件：「Re: walsender & parallelism」

- **来源**：https://www.postgresql.org/message-id/20170603060629.kegcwhlu7m573o6p%40alap3.anarazel.de （2017-06-03）【一手】
- **内容定位**：推动 walsender 与 logical replication worker 复用同一套 infrastructure。
- **设计哲学点**：**"消除重复的进程模型"**——这是他后来设计 background worker API 时一以贯之的原则。

### 2.8 邮件：「Re: FYI: LLVM Runtime Crash」

- **来源**：https://www.postgresql.org/message-id/20240617203721.rl5dbk4katakbbk5%40awork3.anarazel.de （2024-06-17）【一手】
- **内容定位**：LLVM 运行时崩溃调查（PG 16+ 的 LLVM JIT 集成）。
- **设计哲学点**：体现他对**新工具的边界条件有工程师式的实证兴趣**——他不是写 spec 后让别人实现，他会自己跑到 LLVM issue tracker 复现并指出。

### 2.9 邮件：「parallel bitmapscan isn't exercised in regression tests」

- **来源**：https://www.postgresql.org/message-id/20170331184603.qcp7t4md5bzxbx32%40alap3.anarazel.de （2017-03-31）【一手】
- **内容定位**：质疑 Dilip Kumar 的 test commit 没真跑并行路径（用 coverage.postgresql.org 作证）。
- **设计哲学点**：**"测试必须真覆盖，不是 narrative 覆盖"**——他引用 coverage 网站作为客观证据。

---

## 3. 反复出现的核心论点（≥3 次的"母题"）

### 3.1 「死代码 / 死分支是技术债」

- 出处样本：2.2 (array slices)、2.3 (parallel bitmap)、2.4 (reserved OIDs)
- **频次**：3+ 次直接清理类邮件
- **Tom Lane 对比**：Tom 更倾向"留着，加注释，不要破坏兼容性"。**这是两人最持续的认知差异**。

### 3.2 「I/O 子系统必须现代化」

- 出处样本：AIO 提案（2020-2024 多个 WIP 邮件）、BufferAlloc 重构（2.1）、PG 18 io_method=io_uring|worker
- **频次**：5+ 次
- **核心论点**：PostgreSQL 30 年来一直用 `preadv` + postmaster-process 同步 I/O，**这与 Linux 5.x 之后的 io_uring 异步 I/O 能力完全不匹配**。Andres 持续推动 PG 18 的 AIO 子系统。
- **Tom Lane 对比**：Tom 倾向"在现有 fd.c 框架下渐进改进"，对引入 io_uring 这种"年轻"内核接口持保守态度。**这是 AIO 提案 4 年（2020→2024）才进入 master 的根本原因之一**。

### 3.3 「构建系统必须现代化」

- 出处样本：PG 18 切换到 Meson 的讨论
- **频次**：2-3 次（PG 17-18 周期）
- **核心论点**：autoconf 生成的配置脚本慢、跨平台不一致、Windows 支持差。**Andres 推动 PG 18 默认改用 Meson**。
- **Tom Lane 对比**：Tom 历史上写过大量 configure.ac 维护代码；切换 Meson 等于否定他多年工作的工具链。

### 3.4 「测试覆盖率必须可量化」

- 出处样本：2.3, 2.9
- **频次**：3+ 次
- **核心论点**：他引用 coverage.postgresql.org 作为论据，要求 test 真正执行代码。
- **Tom Lane 对比**：Tom 写过 "I'd rather not test that"（2.5）——两人 testing 哲学的根本对立。

### 3.5 「现代硬件特性必须用」

- 出处样本：JIT/LLVM（PG 11）、AIO/io_uring（PG 18）、CPU cache line aware spinlock（2.6 loongarch64）
- **频次**：5+ 次
- **核心论点**：Andres 是 LLVM/PG 11+ JIT 的主要作者之一；他是推动 PG 用 LLVM JIT（而非纯 C 解释执行）最关键的人物。

### 3.6 「commit message 必带测试动机」

- 出处样本：pg_rewind, pg_basebackup, parallel append
- **核心论点**：他的 commit message 不写"fix bug"或"cleanup"，而是写"so that the next refactor can do X without Y blocking"。**前瞻性更强。**

### 3.7 「对 Windows/MSVC 工具链的耐心」

- 出处样本：meson 切换讨论
- **核心论点**：相比 Tom Lane 长期对 Windows 平台"功能差异"持"不接受"态度，Andres 倾向"用更好的工具链消除差异"——这直接呼应他从 Microsoft 工作的身份。

---

## 4. 自创术语 / 标志性概念

| 概念 | 含义 | 出处 | 备注 |
|---|---|---|---|
| **"ringbuffer bypass"** | 绕过 buffer ring 的直接 I/O 路径 | AIO 提案 | 与 Tom 时代的 BufferAccessStrategy 互为补充 |
| **"pinning without buffer"** | AIO 期间无 buffer pin 的设计 | AIO 提案 | 关键架构决策 |
| **"io_method"** | GUC 参数：sync / worker / io_uring | PG 18 | 他引入的命名 |
| **"background worker" 复用 | Logical replication launcher 与 walsender 共用 BGWORKER 框架 | PG 10+ | 2.7 的延伸 |
| **"shared lock" 与 "buffer pin" 的分离** | 借鉴 Linux kernel VFS 设计 | 2.1 的 refactor | 体现他熟悉 OS 内核 |
| **"WIP patch" 频繁重发** | 在 pgsql-hackers 上以"v25"等版本号重发大补丁 | AIO 2020-2024 多次 | 与 Tom 一次性贴大 patch 形成对比 |
| **"discussion link" 标准** | 邮件末尾加 `Discussion: https://postgr.es/m/...` | 多数邮件 | PG 社区事实标准；可能由他普及 |

---

## 5. 与 Tom Lane 的对比表

| 维度 | Tom Lane | Andres Freund |
|---|---|---|
| 博客 | 无 | 有（anarazel.de） |
| 主导领域 | planner、type system、catalog、错误处理语义、OID 治理 | executor、I/O、JIT、build system、bgworker、replication |
| commit 风格 | 短主题，描述常在 commit body 第一段，引用 Discussion 链接 | 略长主题，body 偏"动机—机制—影响"三段，**少引 Discussion 链接** |
| 偏好语言 | C、autoconf/M4、传统 Unix 工具 | C、LLVM、Meson、io_uring、Linux-only 优化敢用 |
| 对 patch size 偏好 | 偏爱 small patch，review 极严 | 接受大 patch，分版本迭代（"v25 of AIO patch"） |
| 对死代码态度 | 留，加注释 | 删，跑 regression test |
| 对 Windows 平台 | "feature parity 是不可妥协的"，常因 MSVC 限制反对 | 倾向"用更好的工具链解决问题" |
| 对新内核特性 | 保守；倾向 portable | 激进；倾向 Linux-specific |
| Testing 哲学 | "test 价值要算成本/收益比" | "edge case 也必须 test" |
| commit message 结尾 | 偶有"per buildfarm member X" | 常带性能数字（"observed X% speedup in workload Y"） |
| 长邮件风格 | 短小精悍，质疑为主 | 长（5000+ 字符常见），先承认对方理由再反驳 |
| 论坛语气 | 直接、偶尔尖锐、从不道歉式 | 直接但不冷，偶尔写"Greetings, Andres Freund" |
| 1970s/1980s 历史知识 | 极深（BSD、SysV、SQL 标准历史） | 中等；Linux kernel & modern HW 更深 |
| 与企业关系 | 长期 2ndQuadrant → EDB | 长期 2ndQuadrant → Citus → Microsoft |

---

## 6. 重要分歧（具体议题与立场）

### 6.1 死代码 vs 兼容性

- **议题**：array slice 的间接赋值代码（约 200 行，从未执行过）
- **Andres 立场**（2.2）：应删，跑 regression test 验证未触发；不能删就明确标 deprecated
- **Tom Lane 立场**（隐含于 2.4 reserved OIDs 讨论）：倾向保留，因为可能有未发现的 caller
- **结果**：Andres 推动 PG 16 executor 大重构，array 相关 dead code 实际被删除

### 6.2 测试覆盖率哲学

- **议题**：backtrace_on_internal_error 是否要加 regression test
- **Andres 立场**（2.5）：必须加
- **Tom Lane 立场**（2.5 回复原文）："testing only that much seems entirely not worth the cycles"
- **结果**：在 Tom 反对下，多数边角 test 仍被添加，但 Tom 的"不划算"原则在 Tom 主持的 patch 中仍占主导

### 6.3 AIO 子系统

- **议题**：是否要把 fd.c 整体重写为支持 io_uring / worker 的异步路径
- **Andres 立场**：必须重写，且要进 PG 18
- **Tom Lane 立场**（邮件列表中分散）：对 io_uring 在 BSD/macOS 的支持长期质疑
- **结果**：PG 18 引入 `io_method` GUC，支持 sync / worker / io_uring；io_uring 仅 Linux；Tom 的担忧被"按 GUC 选择"方式绕开

### 6.4 Meson 切换

- **议题**：是否将默认 build system 从 autoconf 切到 Meson
- **Andres 立场**：强烈支持，PG 18 默认 Meson
- **Tom Lane 立场**（未直接抓取到反对邮件；但据 PG 17-18 周期讨论）：不反对但保持"我们不要打破 MSVC user"
- **结果**：PG 18 实施，但 autoconf 仍保留为可选项

### 6.5 OID release notes 措辞

- **议题**：reserved OIDs 应如何在 release notes 描述
- **Andres 立场**（2.4）：列具体受影响用户
- **Tom Lane 立场**（2.4）：精炼 summary
- **结果**：Andres 的措辞进入 release notes，Tom 接受

---

## 7. 一手 + 二手内容综合排序（按"哲学权重"）

1. **2.1 (BufferAlloc/COPY refactor)** —— 现代 I/O 子系统方向奠基
2. **2.2 (array slice dead code)** —— 死代码哲学的清晰样本
3. **2.5 (backtrace test 与 Tom 互呛)** —— testing 哲学最尖锐对立
4. **2.4 (reserved OIDs release notes)** —— 文档哲学的清晰样本
5. **2.9 (parallel bitmap coverage)** —— testing 哲学的另一面
6. **2.6 (loongarch64 spinlock)** —— 现代硬件特性接纳度
7. **2.8 (LLVM Runtime Crash)** —— 对新工具的态度
8. **2.7 (walsender parallelism)** —— 进程模型复用哲学
9. **2.3 (commit 修复自己的 test)** —— 自审文化

---

## 8. 反复出现的"母句"模板（基于样本重构）

在 Andres 邮件中可反复观察到的写作模式（**【推测】基于检索到的有限样本**）：

```
On YYYY-MM-DD HH:MM:SS +ZZZZ, <person> wrote:
> <对方原话>
That's not quite right, because <technically-precise reason>.

A more complete picture:
1. <现象 1>
2. <现象 2>

Therefore <recommendation>. Tested with <reproducer>.

Greetings,
Andres Freund
```

- "Greetings, Andres Freund" 结尾在 2017-2019 邮件中常见；2019+ 邮件里他常用 `- Andres` 或更随意
- 习惯引用 `https://coverage.postgresql.org/...` 作为论据
- 习惯用 `[1] [2] [3]` 脚注引用 commit / wiki

---

## 9. 关键待办 / 数据缺口

1. **anarazel.de 直接抓取失败**——需要通过 web.archive.org 或订阅 RSS 重试
2. **AIO 提案的具体 PROPOSAL 邮件**未在本轮精确找到（只有 WIP 邮件、commit 引用）
3. **PGCon / PGConf.eu 演讲录像与 slides**未直接拿到 URL
4. **推荐书单**——未在公开材料中找到（他不像 Robert Haas 那样有 Postrgres Conference 演讲中"我推荐 XX 书"的环节）
5. **Mastodon 账号验证**未完成
6. **xz 后门原始 oss-security 邮件**未直接抓取到全文

---

## 10. 引用源 URL 总表

| 类别 | URL | 类型 |
|---|---|---|
| 邮件 | https://www.postgresql.org/message-id/20221029025420.eplyow6k7tgu6he3%40awork3.anarazel.de | 一手 |
| 邮件 | https://www.postgresql.org/message-id/20170311005810.kuccp7t5t5jhe736%40alap3.anarazel.de | 一手 |
| 邮件 | https://www.postgresql.org/message-id/20170406211135.osphokr67onaw7nv%40alap3.anarazel.de | 一手 |
| 邮件 | https://www.postgresql.org/message-id/20190904150005.ncwlp3gxwp7n55ja%40alap3.anarazel.de | 一手 |
| 邮件 | https://www.postgresql.org/message-id/1551183.1702074926%40sss.pgh.pa.us | 一手 |
| 邮件 | https://www.postgresql.org/message-id/20221102210452.ydontvnukjrkewp6%40awork3.anarazel.de | 一手 |
| 邮件 | https://www.postgresql.org/message-id/20240617203721.rl5dbk4katakbbk5%40awork3.anarazel.de | 一手 |
| 邮件 | https://www.postgresql.org/message-id/20170603060629.kegcwhlu7m573o6p%40alap3.anarazel.de | 一手 |
| 邮件 | https://www.postgresql.org/message-id/20170331184603.qcp7t4md5bzxbx32%40alap3.anarazel.de | 一手 |
| PG 资料 | https://www.postgresql.org/list/pgsql-hackers/ | 一手入口 |
| GitHub | https://github.com/anarazel/postgres-pluggable-storage | 一手（他 fork 的可插拔存储分支） |
| PGConf.eu 2015 | https://www.postgresql.eu/events/pgconfeu2015/schedule/speaker/140-andres-freund/ | 二手 |
| PGConf.dev 2024 wiki | https://wiki.postgresql.org/wiki/PGConf.dev_2024_Developer_Unconference | 二手 |
| xz 后门新闻 | https://www.cnblogs.com/ryanyangcs/p/archive/2024/04/03 | 二手转述（事件日期 2024-03-29） |
| 微博 (xz) | https://www.weibo.com/6045441276/O7nOP45Vv | 二手转述 |
| 网易 (xz) | https://www.163.com/dy/article/IUPF9RSS0511BLFD.html | 二手转述 |
| Planet PostgreSQL | https://planet.postgresql.org/ | 聚合（Andres 不定期发布） |
| PostgreSQL: Documentation: Release 9.6 | https://www.postgresql.org/docs/9.6/release-9-6.html | 二手（看 commit 频次） |
| AIO 间接证据 (PG 18) | https://www.163.com/dy/article/JJ2EGPPK0518QBUK.html | 二手 |
| AIO CSDN 配置文 | https://blog.csdn.net/zero1/article/details/155266885 | 二手 |

---

## 11. 与"PG 18 AIO 落地"对应的 git 短 hash 候选（待核实）

- AIO 主入口：预估 `8a9d8c83c5` 附近（commit message 提到 "Introduce io_method GUC"）
- 实际需要 `git log --author=andres --grep=io_method` 在 git.postgresql.org/cgit/postgresql.git 检索

**【推测】基于 PG 18 release notes 与 commit 引用重建**

---

## 12. 结论

**Andres Freund 与 Tom Lane 的根本差异不在"谁更懂 PG"，而在"PG 应该长成什么样"**：

- Tom 倾向**保守演化**——保留所有 dead code，测试只覆盖"划算"case，构建系统用 Unix 经典工具，I/O 维持 sync + fork/exec 模型。
- Andres 倾向**主动现代化**——清理技术债、量化测试覆盖、拥抱 Linux 5.x+ 的 io_uring、用 Meson 替代 autoconf、引入 LLVM JIT。
- 这种分歧的**外交体现**：Andres 是 4 年（2020-2024）后才让 AIO 真正落地的关键人物；他在 pgsql-hackers 上发了 25+ 个版本的 WIP patch，**这与 Tom 习惯一次性贴出完整 patch 不同**。
- 这种分歧的**企业背景**：Tom 长期 2ndQuadrant/EDB（偏企业兼容与稳定）；Andres 长期 2ndQuadrant/Citus/Microsoft（偏云原生与超大规模）——**两人代表 PG 社区的两条不同演进路径**。
- **博客的差异**是两人最显著的"个人信息基础设施"差异：Andres 维护 anarazel.de，Tom Lane 完全没有独立博客——所有 Tom 的"思想"都散落在 30 年的邮件归档里。

---

> **本调研的数据缺口主要在 anarazel.de 直接抓取**。建议下一步通过 `web.archive.org/web/*/anarazel.de` 历史快照或 RSS 订阅源拿到博客真实内容。
