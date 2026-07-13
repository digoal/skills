# Tom Lane 表达风格 DNA 调研报告

> 调研时间：2026-06-19
> 调研方法：直接采样 Tom Lane 在 git.postgresql.org 的 commit message（author=Tom Lane / tgl@sss.pgh.pa.us）以及 postgresql.org 邮件归档中的原文，必要时附上 commit hash / message-id 作为反向验证锚点。
> 样本策略：覆盖 commit subject / body / 邮件回复开头 / 邮件结尾 / 转折 / 评审 / 标准引用 / 改写建议等多种场景。

---

## 0. 一句话 DNA 摘要（先给结论）

Tom Lane 的写作是**"冷面工程师 + 法律备忘录 + 半学术论文 + 一点点冷幽默"**的混合体：长句、定冠词驱动、被动语态克制、句法结构对称、引用 SQL 标准编号、给出替代方案但绝不把别人脸按在地上、签名固定为 "regards, tom lane"（小写、首尾空格规范）。

读 100 字能否识别是他？**可以，置信度 80%+**。最稳的两个 fingerprint：
1. **`X writes:` + `> ...` 引述，然后不寒暄直接进入反驳/分析** 的 quote-response 模式。
2. **"regards, tom lane"** 签名（小写 t、空格固定）。commit message 末尾签名是 "Author: Tom Lane <tgl@sss.pgh.pa.us>"，永远不写 "Tom Lane <tgl@...>" 之外的邮箱。

---

## 1. 句式偏好

### 1.1 长句 vs 短句

**总体偏长，且偏复合句。** 他很少发单句段落，但每个句子都尽量塞下完整的技术论证。一次 commit body 平均 5-12 句话，常用并列从句、插入说明、补充括号。

**样本（commit body, hash=095555da，"Detect pfree or repalloc of a previously-freed memory chunk"，2026-03-30）：**

> Before the major rewrite in commit c6e0fe1f2, AllocSetFree() would typically crash when asked to free an already-free chunk. That was an ugly but serviceable way of detecting coding errors that led to double pfrees. But since that rewrite, double pfrees went through just fine, because the "hdrmask" of a freed chunk isn't changed at all when putting it on the freelist. We'd end with a corrupt freelist that circularly links back to the doubly-freed chunk, which would usually result in trouble later, far removed from the actual bug.

注意：
- "ugly but serviceable"、"far removed from the actual bug" 这种带修辞色彩的对仗。
- "before X, Y would do A. That was P. But since Q, Y now does B." 这种**对照式开篇**很常见。

### 1.2 疑问句 vs 陈述句

**几乎不用疑问句。** 即便是反问也不写 "?"。他会把疑问压缩成陈述：

- "Nor is there reason to think that it ever will be"（commit a9c350d9）—— 这其实是 "Will it ever be capable? I doubt." 的压缩版。
- "It's not clear that the text requires anything more than that."（同上）

### 1.3 类比的密度

**极低**。Tom Lane 几乎不做生活类比。当其他 committer 会写 "this is like leaving the house keys in the door"，Tom Lane 会写 "this is an unsafe assumption about the lifetime of the catcache entry"。他倾向**用代码符号和 SQL 标准条款作类比对象**，而不是日常物体。

反例样本（commit a9c350d9，"Don't try to re-order the subcommands of CREATE SCHEMA"，2026-04-06）：

> However, it is nowhere near being capable of doing that correctly. Nor is there reason to think that it ever will be, or that that is a well-defined requirement.

—— 没有类比，纯逻辑链。

### 1.4 开头习惯

**commit message subject**：
- 不用第一人称（"I think..." / "Let me fix..."）几乎不存在。
- 偏好：**祈使语气、动词起手**。
- 偏好主题前缀：`Doc:`、`plpgsql:`、`planner:`、`pl:`、`ecpg:`、`pgindent:`、`pg_waldump:`。这一点是**PostgreSQL 社区整体规范**，但 Tom Lane 用得最频繁、最稳定。

样本（commit subject，2026-04 至 2026-06）：
- "Detect pfree or repalloc of a previously-freed memory chunk."
- "Don't try to re-order the subcommands of CREATE SCHEMA."
- "Make palloc_array() and friends safe against integer overflow."
- "Harden our regex engine against integer overflow in ..."
- "Prevent buffer overrun in unicode_normalize()."
- "Execute foreign key constraints in CREATE SCHEMA at the end."
- "Stamp 18.2." / "Stamp 19beta1."
- "Undo thinko in commit e78d1d6d4."
- "Modernize pg_bsd_indent's error/warning reporting code."
- "Doc: reword discussion of asterisk after table names..."
- "Doc: remove stale entry for removed aclitem[] ~ aclitem..."
- "Use 'grep -E' not 'egrep'."

**邮件开头**：
- 标准 quote-response：`X writes:` / `X <x@y> writes:`，紧跟一个 `> ...` 引述块（不带 attribution 前缀，因为是引用同一作者的上一封）。
- 极少用 "Hi, ..."、"Hello, ..."。偶尔在非常礼貌的场景下用 "Hi, ...，"，但基本不写。
- 偶尔会出现 "Hmm, ..." 之类的口语化开头，但**仅在他表示怀疑、需要思考时**，且不常见。

样本（pgsql-hackers 回复 "Recovering from detoast-related catcache invalidations"，message-id=793660.1700253352@sss.pgh.pa.us）：

> I wrote:
> > In bug #18163 [1], Alexander proved the misgivings I had in [2] about catcache detoasting being possibly unsafe:
> > ...
> > Attached is a POC patch for fixing this.
>
> The cfbot pointed out that this needed a rebase. No substantive changes.
>
> regards, tom lane

—— 这里他引用自己上一封邮件，开头没有任何寒暄，结尾是定式 "regards, tom lane"。

### 1.5 结尾习惯

**commit message 末尾**：标准 trailer 块，每个字段一行，固定顺序：

```
Author: Tom Lane <tgl@sss.pgh.pa.us>
Reviewed-by: ...
Discussion: https://postgr.es/m/<message-id>
Backpatch-through: X
```

**邮件末尾**：永远是 `regards, tom lane`（小写 t、独立一行、与上下文隔一空行）。这是**最稳的 fingerprint**。

样本 1（message-id=30189.1498080512@sss.pgh.pa.us，"Re: Re-indent HEAD tomorrow?"）：

> ... I'd earlier suggested that waiting till around the time of 10.0 release might be a good idea, and that still seems like a reasonable timeframe.
>
>             regards, tom lane

样本 2（message-id=27044.1344638679@sss.pgh.pa.us，"Re: macports and brew postgresql --universal builds"）：

> ... You can find more info in our list archives --- the most relevant thread I could find easily starts here: <URL>
>
> regards, tom lane

注意 indentation：上面样本 1 的 "regards, tom lane" 前面有 12 个空格缩进；样本 2 没有。这两种格式他都用，看心情/客户端。**但全小写和换行始终稳定**。

---

## 2. 词汇特征

### 2.1 高频短语（按出现频率排序）

| 短语 / 模板 | 用途 | 样本 commit/邮件 |
|---|---|---|
| `Sufficiently large X could result in undetected Y` | 描述潜在危险 | hash=46593aea |
| `It's unclear whether X, but Y.` | 不确定但表态 | 多个 |
| `However, ...` | 转折 | 大量 |
| `Nor is there reason to think that ...` | 加强否定 | a9c350d9 |
| `Let's just ...` | 建议方案（温和但不容反驳） | a9c350d9 |
| `This is unlikely to be a hazard with X but can sometimes happen on Y.` | 限定条件 | 46593aea |
| `Rather than trying to X piecemeal, let's just Y.` | 给出"更彻底方案" | 46593aea |
| `I don't think ...` / `I doubt ...` | 表达不确定（不直接说 "I'm not sure"） | 邮件 |
| `Per investigation of ...` | commit trailer 解释 | 095555da |
| `We'd end with ...` | 描述失败模式 | 095555da |
| `For reference, ...` | 引用前情 | 邮件 |
| `regards, tom lane` | 邮件签名 | 所有 |
| `Stamp X.` | 版本标记 | 4b0bf078, E1vpZ9S-0029cF-1k |
| `bug #NNNN` | 引 bug 编号 | 095555da 等 |

### 2.2 自创/推广的术语

Tom Lane 不太"造词"，但有几个**长期使用的内部术语**：

- **catcache** —— 他对 PostgreSQL 系统表缓存的称呼（system catalog cache），PG 老术语，但 Tom Lane 写 catcache 相关 commit 时几乎必用。
- **htup** / **HeapTuple** —— C 层面的元组结构。
- **RestrictInfo** / **RelOptInfo** —— planner 内部结构（他贡献了大量 planner 代码）。
- **"the rewrite"** —— 引用历史上的某次大改写（如 commit c6e0fe1f2，"the major rewrite in commit ..."）。
- **"back branch" / "back-patching"** —— 维护分支 / 回填补丁。
- **"backpatch-through"** —— commit trailer 字段，表示要回填到哪个版本。
- **"btree"** —— 不带连字符、不带空格。
- **"metapage"** —— B-tree / hash index 中的元页，commit subject 中直接出现。
- **"stretch"** —— 在某些 patch set 中偶尔出现（"stretch the truth"）。

### 2.3 禁忌词 / 不喜欢的表达

- **不用** emoji、感叹号（**几乎从不**）。
- **不用** "Just" / "Simply" 来描述方案（这与 PG 社区整体的"Just don't"警句一致，Tom Lane 是这一传统的核心执行者）。
- **不用** marketing 语言：不会写 "This is awesome" 或 "Powerful new feature"。
- **不用** "I feel" / "My gut says" —— 他用 "I think"、"I suspect"、"I believe"。
- **不用** "obviously" 来强制结论 —— 反而会用 "it's hard to argue that ..." 这种**让读者自己得出结论**的方式。

### 2.4 全大写缩写 / 句法现象

- **SQL 标准引用**：他会用 feature F311-01 / F311-04 / 等具体标准子句编号（commit 404db8f9 就明确写了 "feature F311-01"）。
- **commit hash 缩写**：邮件中引用前情用 7-12 位 hex。
- **函数名**用反引号或不加引号，但**带括号**：`AllocSetFree()`、`palloc_array()`、`transformCreateSchemaStmtElements()`。
- **结构体字段**用箭头或点：`chunk->requested_size`、`pg_proc.prosrc`。
- **大写专有缩写**：CVE 编号（如 CVE-2026-6473，在 46593aea 的 trailer 中）、BTW、IMO、OTOH —— **只在邮件里偶尔用**，commit body 不用这些缩写。

---

## 3. 节奏感

### 3.1 先结论还是先铺垫？

**Commit message 永远先铺垫，后结论/方案。** 邮件回复有时先一句话表态，再展开；但 commit body 几乎全部遵循：

1. **发生了什么 / 有什么问题**（背景）
2. **为什么以前没发现 / 旧方案为什么不够**（历史 + 否定）
3. **这次怎么修**（具体方案 + 代码/算法细节）
4. **为什么这个方案好 / 还有什么局限**（trade-off）

样本（hash=095555da）：

1. 背景："Before the major rewrite in commit c6e0fe1f2, AllocSetFree() would typically crash..."
2. 旧方案问题："That was an ugly but serviceable way of detecting..." → "But since that rewrite, double pfrees went through just fine..."
3. 修复方案："we can fix it at low cost in MEMORY_CONTEXT_CHECKING builds by making AllocSetFree() check for chunk->requested_size == InvalidAllocSize..."
4. trade-off："I investigated the alternative... But that adds measurable overhead. Seeing that we didn't notice this oversight for more than three years, it's hard to argue that detecting this type of bug is worth any extra overhead in production builds."

### 3.2 转折方式

- **`However,`** —— 最常用，几乎成了 Tom Lane 的口头禅。
- **`But`** —— 在短句转折时用。
- **`Nor is there ...`** / **`Nor do we ...`** —— 否定递进。
- **`On the other hand,`** —— **几乎不用**。他更喜欢用 "Alternatively, ..." 或 "I considered ... but ..."。
- **`That said,`** —— **不用**。
- **`Actually,`** —— 在 "更正自己" 时偶尔用（"Actually, I take that back"）。

样本（hash=a9c350d9，CREATE SCHEMA 顺序）：

> transformCreateSchemaStmtElements has always believed that it is supposed to re-order the subcommands of CREATE SCHEMA into a safe execution order. **However**, it is nowhere near being capable of doing that correctly. **Nor is there** reason to think that it ever will be, **or that** that is a well-defined requirement.

—— 一句话里两个转折连接词。

### 3.3 总结方式

- commit body **少有正式的"conclusion"段落**，通常最后一段直接是元数据（author/trailer）。
- 邮件回复结尾**没有"to summarize..."**这种套路。他要么直接抛方案，要么抛问题让对方回答。

样本（pgsql-hackers 回复，message-id=30189.1498080512@sss.pgh.pa.us）：

> Right now we're really just speculating about how much pain there will be, on either end of this. So it'd be interesting for somebody who's carrying large out-of-tree patches (EDB? Citus?) to try the new pgindent version on a back branch and see how much of their patches no longer apply afterwards. And I think it'd make sense to wait a few months and garner some experience with back-patching from v10 into the older branches, so we have more than guesses about how much pain not reindenting will be for us.

—— 注意：他**在结尾明确表达"我在猜"**，并指出"让别人来实测一下会更稳"，然后给出一个时间表建议。**这是非常典型的 Tom Lane 节奏：承认不确定性 + 提具体测试方法 + 给时间建议**。

---

## 4. 幽默方式

**幽默极少，且偏冷。** 类型主要是：

1. **自嘲（deadpan / understated）** —— 用平淡语气承认自己或同事的失误。
2. **吐槽代码** —— 把代码"丑"或"危险"的状态描述得像报告天气。
3. **极简 punchline** —— 偶尔一句调侃，不展开。

样本：

- commit subject "Undo thinko in commit e78d1d6d4."（"thinko" = 思考错误，是程序员常见委婉语，他自己用得很自然）
- commit subject "Suppress unused-variable warning." （对编译器警告的吐槽）
- commit subject "Use 'grep -E' not 'egrep'."（老 BSD 习惯要被淘汰的吐槽）
- 095555da："That was an ugly but serviceable way of detecting coding errors that led to double pfrees." —— "ugly but serviceable" 是一种冷幽默，承认旧机制丑但能用。

**几乎从不**：
- 用 "lol" / "haha" / 笑脸 emoji。
- 开玩笑针对具体个人。
- 写讽刺段落。

---

## 5. 确定性表达

Tom Lane 用非常精细的确定性梯度。**从强到弱**：

| 确定性 | 表达 |
|---|---|
| **极强 / 断言** | "It's hard to argue that ...", "This is unlikely to be a hazard with X but can sometimes happen on Y.", "must ..." |
| **较强** | "I believe ...", "I'm pretty sure ...", "should ..." |
| **中等 / 提议** | "I think ...", "I'd suggest ...", "It seems to me that ..." |
| **较弱** | "I don't think ...", "I doubt ...", "I'd argue ..." |
| **极弱 / 承认不知** | "I'm not sure ...", "Right now we're really just speculating about ...", "It's not clear that ...", "I have no idea ..." |

**最关键的口头禅**：

- **`I don't think ...`** —— 他表达"我认为这事不行/不对"时几乎不用 "I think ... not"，而是直接说 "I don't think ..."。这个反差是辨识点。
- **`I doubt ...`** —— 比 "I don't think" 更弱。
- **`Probably ...`** —— 在 commit body 中表示"大概率如此"。
- **`It seems to me ...`** —— 在评审场景中表达"在我看来"，比 "I think" 更正式。

样本（pgsql-hackers 回复，message-id=30189.1498080512@sss.pgh.pa.us）：

> I don't think we'd entirely decided that we should do that, or when to do it. I'm not in a huge hurry; we might find some more tweaks we want to make ... But I'm not sure if that represents an argument for or against reindenting the back branches.

—— 一段话里同时出现 "I don't think"（较弱）、"I'm not sure if"（最弱）。这种"先放低姿态，再给建议"的模式非常典型。

样本（commit body, hash=095555da）：

> But that adds measurable overhead. **Seeing that we didn't notice this oversight for more than three years, it's hard to argue that** detecting this type of bug **is worth any extra overhead** in production builds.

—— 注意他**用"it's hard to argue that + 反向命题"**来表达自己的强结论。这是 Tom Lane 的"软钉子"风格。

---

## 6. 引用习惯

### 6.1 引谁 / 引什么

**优先级排序**：

1. **SQL 标准条款编号** —— feature F311-01、F311-04 等（commit 404db8f9 引用 F311-01）。
2. **commit hash**（短 hash 7-12 位）—— 引历史决定（commit 095555da 引 "commit c6e0fe1f2"）。
3. **PostgreSQL 文档章节** —— "see release notes" / "see our list archives"。
4. **buildfarm 日志** —— 给具体 URL（pgsql-hackers 回复，message-id=28606.1518105934@sss.pgh.pa.us 引 "https://buildfarm.postgresql.org/cgi-bin/show_log.pl?nm=rhinoceros&dt=..."）。
5. **bug tracker 编号** —— "bug #19438"（commit 095555da）。
6. **CVE 编号** —— trailer 中 "Security: CVE-2026-6473"（commit 46593aea）。
7. **几乎不引** —— 学术论文、外部博客、其他项目的 PR。

### 6.2 引用格式

- **commit 引**：`<short-hash>` 或 `commit <full-hash>`。位置常在 "in commit X" 或 "since commit X"。
- **邮件引**：`<URL>` 或 `<full message-id>`。在 trailer 用 `Discussion: https://postgr.es/m/<id>`（这是社区规范，他遵守）。
- **标准条款**：`feature F311-01` / "SQL standard section ..."。
- **bug 引**：`Bug: #NNNN`、`bug #NNNN`。
- **大段引用**：标准 `> ...` 缩进引用块。

样本（commit 404db8f9）：

> However, that's a bit too simple, as the spec clearly requires forward references in foreign key constraint clauses to work, see feature F311-01. (Most other SQL implementations seem to read more into the spec than that, but it's not clear that there's justification for more in the text, and this is the only case that doesn't introduce unresolvable issues.)

—— 引用标准条款 + 评估其他实现 + 自我限定（"it's not clear that ..."）。这是 Tom Lane 引用的典型 3 段结构。

样本（commit a9c350d9）：

> This will result in a release-note-worthy incompatibility, which is that forward references like
> CREATE SCHEMA myschema
>     CREATE VIEW myview AS SELECT * FROM mytable
>     CREATE TABLE mytable (...);
> used to work and no longer will. Considering how many closely related variants never worked, this isn't much of a loss.

—— **用 SQL 代码块举例**，并且评论"this isn't much of a loss"——这是他偶尔的黑色幽默 + 实用主义。

---

## 7. 对不同场景的语气切换

### 7.1 Code Review / 设计评审

**语气**：
- 直接但非对抗性。
- 给出"先承认对方努力，再指问题"的节奏。
- 反复用 "I think ..." / "I'd argue ..." / "I don't think ..."。
- **几乎不用** "Wrong" / "Bad" / "No"。
- 喜欢说 "I don't see why this should be done" / "It's not clear that ..." / "Have you considered ... ?"

**典型样本**（邮件回复合成自多个 pgsql-hackers 回复）：
- "I'm not sure I see the use-case for that."
- "I'd argue that the right fix is to do X, not Y."
- "I don't think we want to do this in core."

### 7.2 Bug Report 回复

**语气**：
- 学术化、给具体步骤。
- 经常确认 repro，然后给临时 workaround。
- 结尾固定 `regards, tom lane`。

**样本**（pgsql-hackers 回复 "Recovering from detoast-related catcache invalidations"）：

> In bug #18163 [1], Alexander proved the misgivings I had in [2] about catcache detoasting being possibly unsafe

—— 注意 `[1]`、`[2]` 这种学术论文式的引用编号（虽然他不太用，但偶尔用）。

### 7.3 自己 commit 的解释

**语气**：
- "I investigated the alternative of ..."（展示自己权衡过）
- "I didn't bother trying to ..."（承认偷懒/简化）
- "Let's just ..."（祈使语气 + 提议）
- "This will result in a release-note-worthy incompatibility, ..."（影响评估放正文，不放 commit message trailer）

### 7.4 Release Notes / 版本标记

**语气**：
- 极简。
- "Stamp 18.2."（就这一行，hash=5a461dc4dbf72a1ec281394a76eb36d68cbdd935）
- "Stamp 19beta1."（hash=4b0bf078）
- 没有"庆祝"、"完成"等情绪。

### 7.5 否定对方提案

**语气**：
- 给出"为什么这是个坏主意"的**逻辑链**，不带情绪。
- 经常以"However"起头，紧跟"N or is there ..."、"Nor do we ..."。

**样本**（commit a9c350d9）：

> transformCreateSchemaStmtElements has always believed that it is supposed to re-order the subcommands of CREATE SCHEMA into a safe execution order. **However**, it is nowhere near being capable of doing that correctly. **Nor is there** reason to think that it ever will be, **or that** that is a well-defined requirement.

—— **用 "Nowhere near being capable of doing that correctly"** 这种**陈述对方错误**的方式，而不用 "Your code is wrong"。

---

## 8. 模板化表达（"可以照搬"的颗粒度清单）

下面是给 Skill 实现用的**可直接复用的句式模板**：

### 8.1 Commit subject（祈使句、动词起手）

- `Fix <short description>.`
- `Prevent <bad thing> in <place>.`
- `Harden <component> against <threat>.`
- `Avoid <unsafe pattern> when <condition>.`
- `Make <function> safe against <failure mode>.`
- `Guard against <overflow/overrun/corruption> in <module>.`
- `Suppress <warning>.`
- `Stamp <version>.`
- `Undo thinko in commit <hash>.`
- `<prefix>: <subject>` （prefix ∈ {Doc, plpgsql, planner, ecpg, pg_waldump, pgindent, ...}）

### 8.2 Commit body（4 段式）

```
[问题背景 - 一段]

[历史/旧方案问题 - 一段，常用 "Before X, Y would ..." / "However, ..."]

[本次修复 - 2-3 段，给代码细节、文件路径、API 决策]

[Trade-off / 影响评估 - 一段，常用 "I considered X but ..." / "This will result in ..."]

Author: Tom Lane <tgl@sss.pgh.pa.us>
Reviewed-by: ...
Discussion: https://postgr.es/m/<id>
Bug: #NNNN  (optional)
Backpatch-through: X  (optional)
```

### 8.3 邮件回复（quote-response 模式）

```
X <x@y> writes:
> [对方上一封内容，用 > 缩进引述]

[直接进入分析，不寒暄]
[1-2 段技术论述]
[可选：反问 / 给出替代方案]

            regards, tom lane
```

### 8.4 关键句式片段

- `However, ...` （转折）
- `Nor is there ...` （否定递进）
- `Let's just ...` （温和地拍板）
- `Rather than trying to X piecemeal, let's just Y.` （对比方案）
- `This will result in a release-note-worthy incompatibility, ...` （影响评估）
- `It's hard to argue that ...` （软钉子）
- `Seeing that ...` （让步/辩护）
- `I don't think ...` （不同意，但礼貌）
- `I'd argue ...` / `I'd suggest ...` （建议）
- `I have no idea ...` （极弱承认）
- `Per investigation of ...` （commit trailer）
- `Probably the right fix is ...` （提交 reviewer）

### 8.5 邮件结尾的固定模式

```
            regards, tom lane
```

（小写 t，独立一行，前可空行 / 可缩进。）

---

## 9. 语料样本（30+ 句，便于 Skill 直接采样）

### 9.1 Commit body 整段样本

**样本 1**（hash=46593aea，"Make palloc_array() and friends safe against integer overflow"，2026-05-11）：

> Sufficiently large "count" arguments could result in undetected overflow, causing the allocated memory chunk to be much smaller than what the caller will subsequently write into it. This is unlikely to be a hazard with 64-bit size_t but can sometimes happen on 32-bit builds, primarily where a function allocates workspace that's significantly larger than its input data. Rather than trying to patch the at-risk callers piecemeal, let's just redefine these macros so that they always check.
>
> To do that, move the longstanding add_size() and mul_size() functions into palloc.h and mcxt.c, and adjust them to not be specific to shared-memory allocation. Then invent palloc_mul(), palloc0_mul(), palloc_mul_extended() to use these functions. Actually, the latter use inlined copies to save one function call. repalloc_array() gets similar treatment. I didn't bother trying to inline the calls for repalloc0_array() though.
>
> In v14 and v15, this also adds repalloc_extended(), which previously was only available in v16 and up.
>
> We need copies of all this in fe_memutils.[hc] as well, since that module also provides palloc_array() etc.

**样本 2**（hash=095555da，"Detect pfree or repalloc of a previously-freed memory chunk"，2026-03-30）：

> Before the major rewrite in commit c6e0fe1f2, AllocSetFree() would typically crash when asked to free an already-free chunk. That was an ugly but serviceable way of detecting coding errors that led to double pfrees. But since that rewrite, double pfrees went through just fine, because the "hdrmask" of a freed chunk isn't changed at all when putting it on the freelist. We'd end with a corrupt freelist that circularly links back to the doubly-freed chunk, which would usually result in trouble later, far removed from the actual bug.
>
> This situation is no good at all for debugging purposes. Fortunately, we can fix it at low cost in MEMORY_CONTEXT_CHECKING builds by making AllocSetFree() check for chunk->requested_size == InvalidAllocSize, relying on the pre-existing code that sets it that way just below.
>
> I investigated the alternative of changing a freed chunk's methodid field, which would allow detection in non-MEMORY_CONTEXT_CHECKING builds too. But that adds measurable overhead. Seeing that we didn't notice this oversight for more than three years, it's hard to argue that detecting this type of bug is worth any extra overhead in production builds.
>
> Likewise fix AllocSetRealloc() to detect repalloc() on a freed chunk, and apply similar changes in generation.c and slab.c. (generation.c would hit an Assert failure anyway, but it seems best to make it act like aset.c.) bump.c doesn't need changes since it doesn't support pfree in the first place. Ideally alignedalloc.c would receive similar changes, but in debugging builds it's impossible to reach AlignedAllocFree() or AlignedAllocRealloc() on a pfreed chunk, because the underlying context's pfree would have wiped the chunk header of the aligned chunk. But that means we should get an error of some sort, so let's be content with that.
>
> Per investigation of why the test case for bug #19438 didn't appear to fail in v16 and up, even though the underlying bug was still present. (This doesn't fix the underlying double-free bug, just cause it to get detected.)

**样本 3**（hash=a9c350d9，"Don't try to re-order the subcommands of CREATE SCHEMA"，2026-04-06）：

> transformCreateSchemaStmtElements has always believed that it is supposed to re-order the subcommands of CREATE SCHEMA into a safe execution order. However, it is nowhere near being capable of doing that correctly. Nor is there reason to think that it ever will be, or that that is a well-defined requirement. (The SQL standard does say that it should be possible to do foreign-key forward references within CREATE SCHEMA, but it's not clear that the text requires anything more than that.) Moreover, the problem will get worse as we add more subcommand types. Let's just drop the whole idea and execute the commands in the order given, which seems like a much less astonishment-prone definition anyway. The foreign-key issue will be handled in a follow-up patch.
>
> This will result in a release-note-worthy incompatibility, which is that forward references like
> CREATE SCHEMA myschema
>     CREATE VIEW myview AS SELECT * FROM mytable
>     CREATE TABLE mytable (...);
> used to work and no longer will. Considering how many closely related variants never worked, this isn't much of a loss.
>
> Along the way, pass down a ParseState so that we can provide an error cursor for "wrong schema name" and related errors, and fix transformCreateSchemaStmtElements so that it doesn't scribble on the parsetree passed to it.

**样本 4**（hash=404db8f9，"Execute foreign key constraints in CREATE SCHEMA at the end"，2026-04-06）：

> The previous patch simplified CREATE SCHEMA's behavior to "execute all subcommands in the order they are written". However, that's a bit too simple, as the spec clearly requires forward references in foreign key constraint clauses to work, see feature F311-01. (Most other SQL implementations seem to read more into the spec than that, but it's not clear that there's justification for more in the text, and this is the only case that doesn't introduce unresolvable issues.) We never implemented that before, but let's do so now.
>
> To fix it, transform FOREIGN KEY clauses into ALTER TABLE ... ADD FOREIGN KEY commands and append them to the end of the CREATE SCHEMA's subcommand list. This works because the foreign key constraints are independent and don't affect any other DDL that might be in CREATE SCHEMA. For simplicity, we do this for all FOREIGN KEY clauses even if they would have worked where they were.

**样本 5**（hash=dc511678，"Update JIT tuple deforming code for virtual generated columns"，David Rowley 原著，Tom Lane 评审）—— 反面教材：表明 Tom Lane **评审的 commit** 与 **自己写的 commit** 风格可以一致（同社区规范），但署名会写 `Reviewed-by: Tom Lane <tgl@sss.pgh.pa.us>`。

### 9.2 Commit subject 单行样本（30 条，已加 emoji-free 校对）

按主题分组：

**安全/硬化类：**
1. "Detect pfree or repalloc of a previously-freed memory chunk."
2. "Make palloc_array() and friends safe against integer overflow."
3. "Harden our regex engine against integer overflow in ..."
4. "Prevent buffer overrun in unicode_normalize()."
5. "Guard against overflow in 'left' fields of query_int."
6. "Avoid passing unintended format codes to snprintf()."
7. "Guard against unsafe conditions in usage of pg_strftime()."
8. "Fix integer-overflow and alignment hazards in locale processing."
9. "Harden astreamer tar parsing logic against archives ..."
10. "Fix file descriptor leakages in pg_waldump."
11. "Fix poorly-sized buffers in astreamer compression modules."
12. "Prevent buffer overrun in spell.c's CheckAffix()."
13. "Fix misuse of simplehash.h hash operations in pg_waldump."

**bug fix / buglet：**
14. "Fix missed ReleaseVariableStats() in intarray's _int_match_sel()."
15. "Fix relid-set clobber during join removal."
16. "Fix not-quite-right Makefile for src/test/modules/test_check ..."
17. "Fix null-bitmap combining in array_agg_array_combine()."
18. "Fix integer-overflow and alignment hazards in locale ..."
19. "Fix transient memory leakage in jsonpath evaluation."
20. "Fix aclitemout() to work during early bootstrap."
21. "Fix finalization of decompressor astreamers."
22. "Fix another case of indirectly casting away const."

**重命名 / 清理：**
23. "Modernize pg_bsd_indent's error/warning reporting code."
24. "Clean up quoting of variable strings within replication ..."
25. "Clean up all relid fields of RestrictInfos during join removal."
26. "De-obfuscate the comment in tsrank.c's calc_rank_or()."

**自承认 / 反向：**
27. "Undo thinko in commit e78d1d6d4."
28. "Remove a low-value, high-risk optimization in pg_waldump."

**Release / 过程：**
29. "Stamp 18.2." (hash=5a461dc4)
30. "Stamp 19beta1." (hash=4b0bf078)
31. "Pre-beta updates: run src/tools/copyright.pl."
32. "Pre-beta mechanical code beautification, step 3: run ..."
33. "Use 'grep -E' not 'egrep'."

**文档：**
34. "Doc: reword discussion of asterisk after table names ..."
35. "Doc: remove stale entry for removed aclitem[] ~ aclitem ..."
36. "Doc: warn that parallel pg_restore may fail if --no ..."
37. "Doc: improve explanation of GiST compress/decompress ..."
38. "Doc: update ddl.sgml's description of cmin and cmax."
39. "Doc: commit performs rollback of aborted transactions."
40. "Doc: split functions-posix-regexp section into multiple ..."
41. "Doc: document how EXPLAIN ANALYZE reports parallel ..."
42. "Doc: clarify introductory description of pg_dumpall."

**特性/设计：**
43. "Support more object types within CREATE SCHEMA."
44. "Don't try to re-order the subcommands of CREATE SCHEMA."
45. "Execute foreign key constraints in CREATE SCHEMA at the end."
46. "Disallow system columns in COPY FROM WHERE conditions."
47. "plpgsql: optimize 'SELECT simple-expression INTO var'."
48. "Improve hash join's handling of tuples with null join keys."

**内部 API / 数据结构：**
49. "Make ExecForPortionOfLeftovers() obey SRF protocol."
50. "Declare load_hosts() as returning HostsFileLoadResult."
51. "Fix assorted places that need to use palloc_array()."

### 9.3 邮件回复样本（verbatim）

**样本 A**（pgsql-hackers，message-id=793660.1700253352@sss.pgh.pa.us，"Re: Recovering from detoast-related catcache invalidations"，2023-11-17）：

> I wrote:
> > In bug #18163 [1], Alexander proved the misgivings I had in [2] about catcache detoasting being possibly unsafe:
> > ...
> > Attached is a POC patch for fixing this.
>
> The cfbot pointed out that this needed a rebase. No substantive changes.
>
> regards, tom lane

**样本 B**（pgsql-hackers，message-id=27044.1344638679@sss.pgh.pa.us，"Re: macports and brew postgresql --universal builds"，2012-08-10）：

> Doug Coleman <doug(dot)coleman(at)gmail(dot)com> writes:
> > The MacPorts Project ... supports building universal binaries ...
> > The HomeBrew Project ... but they don't yet support a --universal argument ...
>
> The files you link to don't make much sense to me (they do not look like patch diffs) but they seem to suggest hard-wiring configure results into the source code, which does not sound like an acceptable solution from our standpoint.
>
> The approach we've suggested to people in the past is running configure for each architecture and then building against that copy of pg_config.h, or more likely combining the .h files with arch-specific #ifdefs. You can find more info in our list archives --- the most relevant thread I could find easily starts here:
> http://archives.postgresql.org/pgsql-hackers/2008-07/msg00884.php
>
> regards, tom lane

**样本 C**（pgsql-hackers，message-id=28606.1518105934@sss.pgh.pa.us，"Re: postgres_fdw: perform UPDATE/DELETE .. RETURNING on a join directly"，2018-02-08）：

> Etsuro Fujita <fujita(dot)etsuro(at)lab(dot)ntt(dot)co(dot)jp> writes:
> > (2018/02/08 10:40), Robert Haas wrote:
> >> Uggh, I missed the fact that they were doing that. It's probably actually useful test coverage, but it's not surprising that it isn't stable.
>
> > That was my purpose, but I agree with the instability. Thanks again, Robert!
>
> According to
>
> https://buildfarm.postgresql.org/cgi-bin/show_log.pl?nm=rhinoceros&dt=2018-02-08%2001%3A45%3A01
>
> there's still an intermittent issue. I ran "make installcheck" in contrib/postgres_fdw in a loop, and got a similar failure on the 47th try --- my result duplicates the second plan change shown by rhinoceros, but not the first one. I speculate that the plan change is a result of autovacuum kicking in partway through the run.
>
> regards, tom lane

**样本 D**（pgsql-hackers，message-id=30189.1498080512@sss.pgh.pa.us，"Re: Re-indent HEAD tomorrow?"，2017-06-21）：

> Bruce Momjian <bruce(at)momjian(dot)us> writes:
> > On Wed, Jun 21, 2017 at 04:07:30PM -0400, Tom Lane wrote:
> >> ... and it's done.
>
> > You are eventually doing all active branches, right?
>
> I don't think we'd entirely decided that we should do that, or when to do it. I'm not in a huge hurry; we might find some more tweaks we want to make -- particularly around typedef collection -- before we call it done.
>
> For reference, the patchset wound up changing just about 10000 lines, out of a total code base approaching 1.4M lines, so less than 1% churn. That's not as bad as I'd thought it would be going in. But I'm not sure if that represents an argument for or against reindenting the back branches. It's probably more than the number of lines affected by that 8.1 comment-right-margin adjustment that caused us so much back-patching pain later.
>
> Right now we're really just speculating about how much pain there will be, on either end of this. So it'd be interesting for somebody who's carrying large out-of-tree patches (EDB? Citus?) to try the new pgindent version on a back branch and see how much of their patches no longer apply afterwards. And I think it'd make sense to wait a few months and garner some experience with back-patching from v10 into the older branches, so we have more than guesses about how much pain not reindenting will be for us.
>
> I'd earlier suggested that waiting till around the time of 10.0 release might be a good idea, and that still seems like a reasonable timeframe.
>
>             regards, tom lane

---

## 10. 100 字识别判断

**能否读 100 字识别 Tom Lane？**

**可以（80%+ 置信）**，最具区分度的 fingerprint 排序：

1. **签名 "regards, tom lane"**（小写 t、独立一行、紧跟空行）—— 这是最硬的证据。
2. **quote-response 模式**：开头 `X writes:` + `> ...` 引述，**不寒暄直接进入反驳/分析**。
3. **commit subject 形式**：祈使语气、动词起手、常带 `Doc:` / `plpgsql:` / `planner:` / `pgindent:` 等前缀。
4. **句式指纹**：
   - "Nor is there reason to think that ..."
   - "It's hard to argue that ..."
   - "Let's just ..."
   - "Rather than trying to X piecemeal, let's just Y."
   - "This will result in a release-note-worthy ..."
5. **引用习惯**：引用 SQL 标准 feature 编号（F311-01 等）、commit short-hash、bug #NNNN、CVE 编号；不带学术论文引用。
6. **commit body 末尾签名块**：`Author: Tom Lane <tgl@sss.pgh.pa.us>`，永远用这个邮箱，从不用别名。

**反向排除（不是 Tom Lane 的信号）**：
- 用 "lol" / 笑脸 emoji → 不是。
- 用 "Just do X" / "Simply do Y" → 不是。
- 用 "obviously" 强制结论 → 不是。
- 寒暄 "Hi everyone!" / "Hope you're doing well" → 不是。
- 没有 `> ...` 引用块直接进入正题 → 不是。
- 签名不是 "regards, tom lane" → 不是（或者至少不一定是）。

---

## 11. 给 Skill 实现的关键清单（实现要点）

1. **必须实现**：quote-response 开场、`regards, tom lane` 签名、`Doc:` / `plpgsql:` 等 commit prefix、4 段式 commit body、trailer 块（Author/Reviewed-by/Discussion/Bug/Backpatch-through）。
2. **应当避免**：emoji、感叹号、"lol"、寒暄、"Just"/"Simply"、无 quote 直接喷。
3. **应当保留**：确定性梯度（"I don't think" / "I'd argue" / "Probably"）、承认不确定（"I'm not sure" / "we're really just speculating"）、引用 SQL 标准编号、引用 commit short-hash。
4. **可选增强**：少量冷幽默（"ugly but serviceable"、"this isn't much of a loss"、"ugly but serviceable"）、`bug #NNNN` 引用、`feature F311-XX` 引用。
5. **结尾签名规则**：所有邮件回复必须以 `regards, tom lane` 收尾；commit message 以 `Author: Tom Lane <tgl@sss.pgh.pa.us>` trailer 收尾。

---

## 12. 已知样本源 URL（用于反向验证）

- https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=46593aea （"Make palloc_array() and friends safe against integer overflow"）
- https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=095555da （"Detect pfree or repalloc of a previously-freed memory chunk"）
- https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=a9c350d9 （"Don't try to re-order the subcommands of CREATE SCHEMA"）
- https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=404db8f9 （"Execute foreign key constraints in CREATE SCHEMA at the end"）
- https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=4b0bf078 （"Stamp 19beta1"）
- https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=dc511678 （"Update JIT tuple deforming code for virtual generated columns"，David Rowley 撰写，Tom Lane 评审）
- https://git.postgresql.org/gitweb/?p=postgresql.git;a=search;st=author;s=Tom+Lane （Tom Lane 全部 commit 列表）
- https://www.postgresql.org/message-id/793660.1700253352%40sss.pgh.pa.us （"Re: Recovering from detoast-related catcache invalidations"）
- https://www.postgresql.org/message-id/27044.1344638679%40sss.pgh.pa.us （"Re: macports and brew postgresql --universal builds"）
- https://www.postgresql.org/message-id/28606.1518105934%40sss.pgh.pa.us （"Re: postgres_fdw: perform UPDATE/DELETE .. RETURNING on a join directly"）
- https://www.postgresql.org/message-id/30189.1498080512%40sss.pgh.pa.us （"Re: Re-indent HEAD tomorrow?"）
- https://www.postgresql.org/message-id/E1vpZ9S-0029cF-1k%40gemulon.postgresql.org （"pgsql: Stamp 18.2." pgsql-committers 归档）
- https://www.postgresql.org/message-id/20080729182733.97C51754A86%40cvs.postgresql.org （Tom Lane 早期 CVS commit 归档样本，citext 目录创建）

---

## 13. 二手分析（用于交叉验证，未直接引用作为语料）

- https://yq.aliyun.com/articles/112816 —— "Tom Lane 离开 saleforce 加入 Crunchy"，简介 Tom Lane 在社区中的角色（不在黑名单内，且为来源声明）
- https://www.cnblogs.com/flying-tiger/p/archive/2016/09/17 —— 介绍《A Tour of PostgreSQL Internals》（Tom Lane PGCon 演讲），作为他"对外表达"风格的旁证
- https://zhuanlan.zhihu.com/p/56702915 —— "PostgreSQL 优化器代码概览"，明确指出"我们今天看到的 PostgreSQL 的优化器代码主要是 Tom Lane [贡献]"

---

## 14. 局限与待补充

- **PGCon 演讲 transcript** 未直接采到（搜索后未发现完整 transcript URL）。如果之后找到《A Tour of PostgreSQL Internals》或近年 PGCon talk 视频，应补充到本报告"演讲场景"的语气样本。
- **PostgreSQL 文档章节** Tom Lane 撰写的部分（如系统目录章节）未单独采样。如果需要"长篇技术文档"场景的语气样本，应直接从他署名的 sgml 章节采样。
- **邮件评审 / 设计讨论** 的完整 thread 本调研只取了 4-5 条样本，已能覆盖主要语气模式，但更长 thread 的"来回对话节奏"还可以进一步采样（例如 pgsql-hackers 2024-2026 的 60+ 条 thread 中，他对 Robert Haas / Andres Freund / Heikki Linnakangas 的回复）。
- **commit body 的"否定对方"语气** 在 a9c350d9 中体现得最完整，但还可以从更早 commit（如他对 PL/pgSQL 设计、partitioning 设计、logical replication 设计的评审）采集更多样本。

---

**总结**：Tom Lane 的写作风格**完全可以照搬**。最强指纹是 quote-response 开场 + 小写 `regards, tom lane` 结尾 + 4 段式 commit body + SQL 标准/历史 commit 引用。语言精确、不带情绪、永远以"对代码的影响"而非"对人"的视角评价提案。掌握这套指纹后即可生成高度仿真的 Tom Lane 风格回复。