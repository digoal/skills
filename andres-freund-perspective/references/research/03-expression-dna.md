# Andres Freund 表达风格 DNA 调研报告

> 调研时间：2026-06-20
> 调研方法：直接采样 Andres Freund 在 git.postgresql.org 的 commit message（author=Andres Freund / andres@anarazel.de）、postgresql.org 邮件归档的原文、oss-security 邮件列表的原文、github.com/postgres/postgres 的 commit message 全文。附 message-id / commit hash 作为反向验证锚点。
> 样本策略：覆盖 commit subject / body / 邮件回复开头 / 邮件结尾 / 转折 / 评审 / 性能基准 / 错误报告 / 安全披露 / 复杂设计讨论等多种场景。

---

## 0. 一句话 DNA 摘要（先给结论）

Andres Freund 的写作是**"高性能系统工程师 + benchmark-driven 怀疑论者 + 偶尔急躁的德国直男程序员"**的混合体：短到中长句、第一人称驱动（"I think ..."、"I'm unconvinced ..."、"I suspect ..."）、使用 `*way* too much` 这种 *asterisk-emphasis* 斜体、签名随场景切换（`Greetings, Andres Freund` / `Regards, Andres` / `- Andres` / 无签名 / `WFM`），更爱用**具体性能数字**而不是 ALL-CAPS 警告来推动观点。

读 100 字能否识别是他？**可以，置信度 70-80%**。最稳的几个 fingerprint：
1. **斜体强调用 `*word*` 或 `**word**`（markdown 风格）** —— 在 PostgreSQL 邮件列表中几乎是独家标志。
2. **签名随时代漂移** —— 2016 年用 `Regards, Andres` / 2017-2024 年用 `Greetings, Andres Freund` / 临时信里 `- Andres` / 更老的 `Andres` 一行。**这是 Tom Lane 永远固定的 `regards, tom lane` 的反面**。
3. **"WFM" / "imo" / "afaict" / "IIUC" / "I don't really understand" / "Am I standing on my own foot here?"** 这类缩写和德式英语独白。
4. **基准数据驱动论证** —— "goes from ~240 tps to ~190 tps" 这种数字成段出现。
5. **`Author: Andres Freund <andres@anarazel.de>`** —— 邮箱永远是 `anarazel.de`（不写 Microsoft / 任何雇主邮箱）。

---

## 1. 句式偏好

### 1.1 长句 vs 短句

**混合型。短到中长句为主，关键论点用长复合句撑住。** Tom Lane 是"长句+被动语态+法律备忘录"，Andres 是"短句起手+长句展开+短句收尾"的工程师节奏。邮件长度从 3 行（"Re: parallel bitmapscan"，2017-03-31）到 200+ 行（AIO/COPY 设计讨论，2022-10-29）跨度很大，但**关键判断总是单段一个段落**。

**样本 1（极短邮件，hash=f35742ccb7 的回归测试覆盖问题，message-id=20170331184603）：**

> Hi,
>
> The parallel code-path isn't actually exercised in the tests added in
> [1], as evidenced by [2] (they just explain). That imo needs to be
> fixed.
>
> Greetings,
>
> Andres Freund

注意：
- 整个邮件**只有 3 个句子**。
- "That imo needs to be fixed." 句号结束，**没有任何寒暄、解释、缓冲**。
- 引用用 `[1]` / `[2]` 数字脚注，文末列链接。

**样本 2（长邮件，AIO/COPY 设计讨论，message-id=20221029025420）：**

> Hi,
>
> I'm working to extract independently useful bits from my AIO work, to reduce the size of that patchset. This is one of those pieces.
>
> In workloads that extend relations a lot, we end up being extremely contended on the relation extension lock. We've attempted to address that to some degree by using batching, which helps, but only so much.
>
> The fundamental issue, in my opinion, is that we do *way* too much while holding the relation extension lock. We acquire a victim buffer, if that buffer is dirty, we potentially flush the WAL, then write out that buffer. Then we zero out the buffer contents. Call smgrextend().
>
> Most of that work does not actually need to happen while holding the relation extension lock. As far as I can tell, the minimum that needs to be covered by the extension lock is the following:
>
> 1) call smgrnblocks()
> 2) insert buffer[s] into the buffer mapping table at the location returned by smgrnblocks
> 3) mark buffer[s] as IO_IN_PROGRESS
>
> 1) obviously has to happen with the relation extension lock held because otherwise we might miss another relation extension. 2+3) need to happen with the lock held, because otherwise another backend not doing an extension could read the block before we're done extending, dirty it, write it out, and then have it overwritten by the extending backend.

注意：
- 第一段**用 2 个短句开门**（"I'm working to..." + "This is one of those pieces."）——这是 Andres 风格："我现在在做什么 / 这是为什么"两句话搞定背景。
- 关键论点用 `*way* too much` 斜体强调（在 PostgreSQL 邮件列表里几乎没人这么用）。
- 紧接着用编号列表 1)/2)/3) 把抽象论点拆成可验证的子句。
- 每条列表项后用 `1) obviously has to ... 2+3) need to happen with the lock held, because otherwise ...` 这种**长复合句 + 假设性反例**展开。

**样本 3（geographic fact-check，message-id=20190904150005）：**

> If we were trying to honor that rule, we'd be asking patches to use
> temporary OIDs that don't fall into the 9K range. Otherwise, a fork
> that thinks it has private OIDs up there is going to have intermittent
> trouble tracking HEAD.
>
> Given the timeline 09568ec3d really couldn't forsee a6417078c...

注意：
- 条件句 `If we were trying to honor that rule, we'd be ...` 起手，**没有"我认为"/"似乎"**，直接给出反事实推演。
- 偶尔用**德式英语独白**：`09568ec3d really couldn't forsee a6417078c...` —— 用提交 hash 直接当主语。这是 Tom Lane 永远不会做的事（Tom Lane 用 "Before commit c6e0fe1f2, AllocSetFree() would typically crash..." 这种正式语法包装）。

### 1.2 疑问句 vs 陈述句

**陈述句为主，但带"德式修辞疑问"**。他不写 "?"，但偶尔会在结尾抛一个伪疑问：

- "Am I standing on my own foot here?"（message-id=20170311005810，array slice 死代码讨论）
- "Comments?"（message-id=20160714011850，表达评估长邮件末尾）
- "What gains have you measured in somewhat realistic workloads?"（message-id=wps75qdtwpyk...，prune/freeze 压缩评审）
- "Should we just update the comment to reference that then?"（message-id=20190904150005）

**"Am I standing on my own foot here?"** 是非常典型的 Andres 表达 —— "I might be missing something obvious" 的德语直译版本（"Stehe ich mir selbst auf dem Fuß?"）。这在英美工程师写作中**几乎不会出现**。

**对比 Tom Lane**：
- Tom Lane 几乎**不用疑问句**（"Nor is there reason to think..."、"It's not clear that..."）。
- Andres 的疑问是**真的在问**（"What gains have you measured?"），是 discussion-starter。
- Tom Lane 的反问是**压缩成的反断言**。

### 1.3 类比的密度

**中等偏低，但偏爱"工程内部类比"而不是"生活类比"**。和 Tom Lane 类似，他不做"this is like leaving the house keys in the door"这种类比，但他**偶尔**会做很具体的工程类比：

**样本（message-id=20221029025420，AIO/COPY 设计）：**

> The reason that I'm bringing this up before submitting actual 'batch operation' patches is that the architectural improvements are quickly hidden behind these bottlenecks.

—— "architectural improvements are quickly hidden behind these bottlenecks" 是修辞性的，但**用的是"hiding behind bottleneck"这种技术隐喻**，不是日常物体。

**样本（"Citus isn't a patched version..."，message-id=20170621213914）：**

> Citus isn't a patched version of postgres anymore, butan extension (with some ugly hacks to make that possible ...).

—— "(with some ugly hacks ...)" 是**技术债自嘲**，不是生活类比。

**对比 Tom Lane**：
- Tom Lane 几乎**不做任何类比**，用 SQL 标准条款编号代替。
- Andres 偶尔做类比，但**永远是技术隐喻**（"hidden behind bottlenecks"、"chain of locks"、"lock chains between two partitions"）。

### 1.4 开头习惯

**commit message subject：**
- **前缀化、模块驱动**：`bufmgr:` / `lwlock:` / `heapam:` / `aio:` / `ci:` / `instrumentation:` / `jit:` / `walreceiver:` / `read_stream:` / `tableam:` / `freespace:` / `meson:`。比 Tom Lane 用得更密集、更系统化。
- **动词起手、不用第一人称**：`Fix ...` / `Use ...` / `Improve ...` / `Allow ...` / `Add ...` / `Refactor ...` / `Optimize ...` / `Avoid ...`。
- **没有 Tom Lane 的"Doc:"、"plpgsql:"、`planner:`** 这种语义域前缀 —— Andres 的前缀是**实现层**（bufmgr、lwlock、aio），不是**功能层**（plpgsql、planner）。这反映他**写存储/buffer/I/O 层代码**。
- **不用"Stamp X"**（那是 Tom Lane 的 release-stamp 专属）。

**样本（2025-2026 年间 Andres Freund commit subjects，节选）：**
- "Update JIT tuple deforming code for virtual generated columns"
- "ci: Improve ccache handling"
- "ci: Remove support for cirrus-ci based CI"
- "ci: Add GitHub Actions based CI"
- "Make stack depth check work with asan's use-after-return"
- "pg_test_timing: Show additional TSC clock source debug..."
- "instrumentation: Avoid CPUID 0x15/0x16 for Hypervisor..."
- "instrumentation: Allocate query level instrumentation..."
- "Allow retrieving x86 TSC frequency/flags from CPUID"
- "Minimal fix for WAIT FOR ... MODE 'standby_flush'"
- "Fixups for a4f774cf1c7"
- "read_stream: Only increase read-ahead distance when..."
- "aio: io_uring: Trigger async processing for large IOs"
- "bufmgr: Return whether WaitReadBuffers() needed to..."
- "bufmgr: Fix ordering of checks in PinBuffer()"
- "bufmgr: Improve StartBufferIO interface"
- "bufmgr: Make UnlockReleaseBuffer() more efficient"
- "Use UnlockReleaseBuffer() in more places"
- "bufmgr: Don't copy pages while writing out"
- "bufmgr: Restructure AsyncReadBuffers()"
- "bufmgr: Make buffer hit helper"
- "bufmgr: Switch to standard order in MarkBufferDirtyHint()"
- "bufmgr: Remove the, now obsolete, BM_JUST_DIRTIED"
- "lwlock: Remove support for disowned lwlwocks"
- "lwlock: Remove ForEachLWLockHeldByMe"
- "bufmgr: Implement buffer content locks independently..."
- "bufmgr: Change BufferDesc.state to be a 64-bit atomic"
- "aio: io_uring: Fix danger of completion getting reused..."
- "bufmgr: Make definitions related to buffer descriptor..."
- "lwlock: Invert meaning of LW_FLAG_RELEASE_OK"
- "heapam: Add batch mode mvcc check and use it in page..."
- "heapam: Use exclusive lock on old page in CLUSTER"
- "freespace: Don't modify page without any lock"
- "bufmgr: Optimize & harmonize LockBufHdr(), LWLockWaitListLock()"
- "bufmgr: Add one-entry cache for private refcount"
- "bufmgr: Separate keys for private refcount infrastructure"
- "Improve documentation for pg_atomic_unlocked_write_u32()"
- "Rename BUFFERPIN wait event class to BUFFER"
- "bufmgr: Turn BUFFER_LOCK_* into an enum"
- "lwlock: Fix, currently harmless, bug in LWLockWakeup()"
- "bufmgr: Use atomic sub for unpinning buffers"
- "bufmgr: Allow some buffer state modifications while..."
- "jit: Fix accidentally-harmless type confusion"
- "ci: debian: Switch to Debian Trixie release"
- "ci: macos: Upgrade to Sequoia"
- "ci: Fix Windows and MinGW task names"
- "bufmgr: Fix valgrind checking for buffers pinned in..."
- "bufmgr: Don't lock buffer header in StrategyGetBuffer()"
- "bufmgr: fewer calls to BufferDescriptorGetContentLock"
- "bufmgr: Fix signedness of mask variable in BufferSync()"
- "bufmgr: Introduce FlushUnlockedBuffer"
- "Improve ReadRecentBuffer() scalability"
- "Mark shared buffer lookup table HASH_FIXED_SIZE"
- "ci: openbsd: Increase RAM disk's size"
- "bufmgr: Remove freelist, always use clock-sweep"
- "bufmgr: Use consistent naming of the clock-sweep algorithm"
- "aio: Stop using enum bitfields due to bad code generation"
- "ci: Simplify ci-os-only handling"
- "ci: Per-repo configuration for manually trigger tasks"
- "ci: windows: Stop using DEBUG:FASTLINK"
- "Reduce ExecSeqScan* code size using pg_assume()"
- "meson: add and use stamp files for generated headers"
- "Fix buggy interaction between array subscripts and..."
- "Default to hidden visibility for extension libraries where possible"
- "bufmgr: Use AIO in StartReadBuffers()"

**邮件开头：**
- **永远是 `Hi,`**（2016 至今不变，**几乎所有 Andres 邮件都用这个**）。
- 偶尔会**直接不寒暄**进入 quote-response，特别是当邮件是技术 follow-up 时：
  - "> On 2017-04-06 20:43:48 +0000, Andres Freund wrote: ... This turned the !linux buildfarm red, because it relies on setting effective_io_concurrency (to increase coverage to the prefetching code). I plan to wrap the SET in a DO block with an exception handler. - Andres"
- 极偶尔会有 `Well, ...` 起手（"Well, either they work, or they don't."，message-id=20170601000716）。

**对比 Tom Lane**：
- Tom Lane 邮件开头是 `I wrote:` / `X writes:` + `> ...` 引述块，**几乎不写 "Hi"**。
- Andres 邮件开头是 `Hi,` + 偶尔 quote，但**经常不写 quote-response 引述**直接进入论点。
- Tom Lane 的开头是**回指上一封邮件**，Andres 的开头是**陈述当前论点**。

### 1.5 结尾习惯

**commit message 末尾（trailers）**：标准 PostgreSQL 社区规范，但 Andres 写得**特别密集**：

```
Author: Andres Freund <andres@anarazel.de>
Reviewed-by: ...
Reviewed-by: ...
Reviewed-by: ...
Discussion: https://postgr.es/m/<message-id>
Backpatch-through: X
```

**关键 fingerprint**：
1. **邮箱永远是 `andres@anarazel.de`**，从不写 `andres@microsoft.com` / `andres@anarazel.de` 之外的邮箱 —— 即使他在 Microsoft 工作时也用 anarazel.de。
2. **多个 `Reviewed-by:` 同行排列**（不像 Tom Lane 那样 `Reviewed-by:` 单独一行），并经常**多个 `Discussion:` 链接**（这反映了 Andres 的设计经常源自多年迭代的邮件线程）。
3. **多作者时用多个 `Author:` 行**（如 `Default to hidden visibility for extension libraries where possible` commit 089480c，Andres Freund + Tom Lane 双 Author）。

**样本（commit 089480c，2025-06-20）：**

> Author: Andres Freund <andres@anarazel.de>
> Author: Tom Lane <tgl@sss.pgh.pa.us>
> Discussion: https://postgr.es/m/20211101020311.av6hphdl6xbjbuif@alap3.anarazel.de

**样本（commit 93d9734946，cirrus-ci CI）：**

> Author: Andres Freund <andres@anarazel.de>
> Author: Thomas Munro <tmunro@postgresql.org>
> Author: Melanie Plageman <melanieplageman@gmail.com>
> Reviewed-By: Melanie Plageman <melanieplageman@gmail.com>
> Reviewed-By: Justin Pryzby <pryzby@telsasoft.com>
> Reviewed-By: Thomas Munro <tmunro@postgresql.org>
> Reviewed-By: Peter Eisentraut <peter.eisentraut@enterprisedb.com>
> Discussion: https://postgr.es/m/20211001222752.wrz7erzh4cajvgp6@alap3.anarazel.de

**邮件末尾：多种风格** —— 这是 Andres 最大的 fingerprint 漂移：

| 时期 / 场景 | 签名形式 | 来源 |
|---|---|---|
| 2016 短邮件 | `Regards, / Andres` | message-id=20160714011850 |
| 2017 短邮件 | `- Andres` | message-id=20170406211135（buildfarm red 报告） |
| 2017 中等邮件 | `Greetings, / Andres Freund` | message-id=20170331184603, 20170311005810 |
| 2019 邮件 | `Greetings, / Andres Freund` | message-id=20190904150005 |
| 2021 邮件 | `Greetings, / Andres Freund` | message-id=20211211045826 |
| 2022 长设计邮件 | `Greetings, / Andres Freund` | message-id=20221029025420 |
| 2024 安全披露（xz backdoor） | 无签名 | openwall oss-security 2024/03/29/4 |
| 2024 邮件 | `Greetings, / Andres Freund` | message-id=20240707060727, 20240617203721 |
| 2026 邮件 | `Greetings, / Andres` | message-id=q6trx7a5vd3j5tddamwxahrojopboov6eeue2jkjmfpkhdfgjj |
| 2026 评审邮件 | `Greetings, / Andres Freund` | message-id=wps75qdtwpykdt4zatfh2u2hi3zju4drdzqi2zh7uy3x4ooivv |
| 短回复（review thread） | 经常无签名 | 多个 message-id |

**对比 Tom Lane**：
- Tom Lane **永远是** `regards, tom lane`（小写 t、独立一行），10+ 年不变。
- Andres 的签名**随场景漂移**：`Regards,` / `Greetings,` / `-` / 无签名。
- Tom Lane 签名里有小写 `t` 的细节偏好；Andres 的 "Andres Freund" / "Andres" **首字母大写**。

---

## 2. 词汇特征

### 2.1 高频词与短语

**`I think ...` 出现密度高** —— Tom Lane 几乎不用第一人称，Andres 在不确定时经常用 "I think ..." / "I suspect ..." / "I don't think ..." 开头。

**样本（"I think" 直接出现）：**
- "I think it's actually a lot easier to understand if we keep nextval()/setval() as non-transactional, and ALTER SEQUENCE as transactional."（message-id=20170601000716）
- "I think the approaches presented here are the biggest step that I can see."（message-id=20160714011850）
- "I think it'd be a good idea to rename argcontext into something like setcontext or such."（message-id=20191115024707）
- "I wonder if that's not actually very little new code"（message-id=20170601000716）

**`I don't think ...` 直接出现：**
- "Thinking about it for a second longer, I don't think we'd need a new context - afaict argcontext has exactly the lifetime requirements needed."（message-id=20191115024707）

**`In my opinion ...` 出现密度比 "I think" 低但更重**：
- "The fundamental issue, in my opinion, is that we do *way* too much while holding the relation extension lock."（message-id=20221029025420）

**`I'm unconvinced that ...`** —— Andres 独有的**怀疑论标志**：
- "I'm unconvinced that this is a serious problem - typically the overhead of WAL volume due to pruning / freezing is due to the full page images emitted, not the raw size of the records. Once an FPI is emitted, this doesn't matter."（message-id=wps75qdtwpykdt4zatfh2u2hi3zju4drdzqi2zh7uy3x4ooivv）
- "What gains have you measured in somewhat realistic workloads?" —— 紧跟怀疑论之后的"要 benchmark"要求。

**`I suspect ...`** —— 类似 `I think` 但更弱、更试探：
- "I suspect the issue might be that the version of clang and LLVM are diverging too far."（message-id=20240617203721）

**`I'm not sure`** —— 弱确定性：
- "I'm not convinced that ..." (variant of I'm unconvinced)
- "I'm not sure if that's worth worrying about"（message-id=20221029025420）

**`As far as I can tell, ...`** —— Andres 风格的中等确定性：
- "As far as I can tell, the minimum that needs to be covered by the extension lock is the following:"（message-id=20221029025420）

**`Phew, ...`** —— 罕见的情绪化表达：
- "And done. Phew, this project took way longer than I'd though it'd take."（message-id=q6trx7a5vd3j5tddamwxahrojopboov6eeue2jkjmfpkhdfgjj）

**`Am I standing on my own foot here?`** —— **独有的德式英语表达**：
- 在 array slice 死代码讨论中结尾使用（message-id=20170311005810）。

**`afaict` / `IIUC` / `WFM` / `imo` / `istm` / `IIRC`** —— 缩写密度高：
- "afaict argcontext has exactly the lifetime requirements needed."（message-id=20191115024707）
- "That imo needs to be fixed."（message-id=20170331184603）
- "I plan to wrap the SET in a DO block with an exception handler. - Andres"（buildfarm 报告，message-id=20170406211135）
- "WFM."（message-id=20240707060727，回应 Tom Lane 的 `-1`）

**对比 Tom Lane**：
- Tom Lane **几乎不用** `I think` / `I suspect` / `In my opinion` 这种第一人称。
- Tom Lane 偏好 **`It's hard to argue that ...`** / **`It's not clear that ...`** / **`Nor is there reason to think that ...`**（无人称主语）。
- Andres 的 `I think` 是**真在表达不确定性**；Tom Lane 的 `It's not clear that` 是**法律备忘录式的客观化**。

### 2.2 斜体强调（`*word*` / `**word**`）

**Andres 的关键 fingerprint 之一：在邮件正文中用 markdown 风格的 `*asterisk*` 强调。**

**样本：**
- "The fundamental issue, in my opinion, is that we do *way* too much while holding the relation extension lock."（message-id=20221029025420）
- "We acquire a victim buffer, if that buffer is dirty, we potentially flush the WAL, then write out that buffer. Then we zero out the buffer contents. Call smgrextend()." —— 紧跟着用 `*way*` 暗示"太多了"
- "It's possible that there's a very small regression for extremly IO miss heavy workloads, more below."（同上）

**对比 Tom Lane**：
- Tom Lane 在 commit message body 里**完全不用** `*emphasis*`。
- Tom Lane 的强调方式是**用 ALL-CAPS**（如 `MUST get reverted`）或**用反话**（"ugly but serviceable"）。
- Andres 偶尔也用 ALL-CAPS（"DO NOT"），但偏好 markdown 斜体。

### 2.3 专属术语 / 自创术语

Andres 不是术语创造者，但他是**"aftermarket installer / build system / instrumentation"** 相关术语的早期使用者和贡献者：

- **AIO (Asynchronous I/O)**：他是 PostgreSQL AIO 子系统的主要作者（"bufmgr: Use AIO in StartReadBuffers()" commit 12ce89f）。
- **read_stream**：`read_stream: ...` 系列 commit 显示这是他**新创造的子系统**。
- **io_method**：在 AIO commit 中引入（commit 12ce89f: "When io_method=sync is used, the IO patterns..."）。
- **InProgressBuf**：在 message-id=20221029025420 中讨论的旧机制名。
- **BulkInsertState**：同上，被他批评为"the right place"的存疑。
- **`WFM`**（"Works For Me"）：Andres 在邮件中大量使用，**Tom Lane 从不写**这个缩写（Tom Lane 用 "Looks good to me" 或 "WFM" 偶尔出现，但密度低很多）。
- **`afaict`**（"as far as I can tell"）：Andres 的偏好。
- **`imo` / `istm` / `IIRC` / `IIUC`**：Andres 大量使用，**Tom Lane 几乎从不写**这些缩写（Tom Lane 的邮件更接近法律备忘录，无缩写）。

### 2.4 禁忌词 / 几乎不用的词

- **"regards"**（Tom Lane 的专利）：Andres 用过几次 "Regards, Andres"（2016），但 2017 年后几乎完全切换到 "Greetings,"。
- **"obviously"**（虽然偶尔用，但比 Tom Lane 密度低很多）：Andres 用 `1) obviously has to happen with the relation extension lock held because otherwise...`（message-id=20221029025420），但**没有 Tom Lane 的"It is nowhere near being capable of doing that correctly"那种冷面 "obviously"**。
- **`MUST` ALL-CAPS**（Tom Lane 的标志）：Andres 不用这种 ALL-CAPS 警告；他用具体数据 + "I'm unconvinced" + "What gains have you measured" 来表达。
- **`It's hard to argue that`**（Tom Lane 的标志）：Andres 不用。
- **`Nor is there reason to think that`**（Tom Lane 的标志）：Andres 不用。
- **`[your favorite committer]` / `regards, tom lane`**：Andres 不模仿 Tom Lane 的签名风格。

---

## 3. 节奏感

### 3.1 先结论还是先铺垫

**先结论，但铺垫段永远紧跟结论。** 这是 Andres 的核心节奏：先给"我现在在做什么 / 我认为 X"，然后**立刻**给"为什么 / 数据"。

**样本（message-id=20170331184603，3 句话搞定）：**

> Hi,
>
> The parallel code-path isn't actually exercised in the tests added in
> [1], as evidenced by [2] (they just explain). That imo needs to be
> fixed.
>
> Greetings,
> Andres Freund

**样本（message-id=20170311005810，dead code 讨论）：**

> Hi,
>
> In the context of my expression evaluation patch, I was trying to
> increase test coverage of execQual.c. I'm a bit confused about
> $subject. ExecEvalArrayRef() has the following codepath:
>
> [30 行 C 代码]
>
> That's support for multiple indirect assignments, assigning to array
> slices.  But I can't figure out how to reach that bit of code.
>
> [SQL 测试用例]
>
> But I don't see how to the slice code can be reached. ...
>
> Am I standing on my own foot here?

注意：
- "In the context of my expression evaluation patch, I was trying to increase test coverage of execQual.c." —— **背景一段话**（2 句话）。
- "I'm a bit confused about $subject." —— **直接亮出问题**。
- 然后才贴 C 代码 + SQL + 反推。
- "Am I standing on my own foot here?" —— **结尾伪疑问**。

**对比 Tom Lane**：
- Tom Lane 偶尔**先铺垫**（"Before commit c6e0fe1f2, AllocSetFree() would..."），然后**再给结论**。
- Andres 永远**先给结论**（"I'm a bit confused about $subject"），然后**再给证据**。
- Tom Lane 是历史叙事驱动，Andres 是问题驱动。

### 3.2 转折方式

**Andres 的转折词库**（vs Tom Lane 的"However"偏好）：

- **`But`**（最常用，频率高于 Tom Lane）：
  - "The !slice code can be reached: [...]. **But** I don't see how to the slice code can be reached."（message-id=20170311005810）
  - "I plan to wrap the SET in a DO block with an exception handler. **- Andres**"（简短到无转折）
  - "We acquire a victim buffer, if that buffer is dirty, we potentially flush the WAL, then write out that buffer. Then we zero out the buffer contents. Call smgrextend(). **Most of that work does not actually need to happen** while holding the relation extension lock."（无转折词，直接反差）
- **`However`**（偶尔用）：
  - "**However**, it is nowhere near being capable of doing that correctly." —— 这是 Tom Lane 风格，不是 Andres。
- **`That said`**（几乎不用）：Andres 不用这种英语母语者写作的优雅转折。
- **`On the other hand`**（几乎不用）：同上。
- **`OTOH`**（缩写版本，2014-2016 间用过）："**OTOH**, given that the tests already fail, I assume our windows contributors already have disabled autocrlf?"（message-id=20240707060727）
- **`That imo needs to be fixed.`**（直接断言 + `imo` 缓冲）：这是 Andres 独有的"软断言"。

**样本（message-id=20170601000716，多转折对照）：**

> **Well,** but then we should just remove minval/maxval if we can't rely on it.
> **That seems like a drastic overreaction to me.** ← Tom Lane 风格的 "It's hard to argue that"
> **Well,** either they work, or they don't. **But** since it turns out to be easy enough to fix anyway...

注意 Andres 在这段里**短短 3 句**用了 3 个 `Well` —— 口语化、对话式。这是 Tom Lane 不会做的（Tom Lane 邮件没有 `Well` 这种起手）。

### 3.3 总结方式

**Andres 的邮件末尾经常是：**
- "Comments?"（邀请反馈，message-id=20160714011850）
- "Greetings, Andres Freund"（标准结尾）
- 无结尾（"- Andres" 之后就没了，message-id=20170406211135）
- "**WFM**."（极简同意，message-id=20240707060727）
- "And done."（极简完结，message-id=q6trx7a5vd3j5tddamwxahrojopboov6eeue2jkjmfpkhdfgjj）

**对比 Tom Lane**：
- Tom Lane 的邮件结尾几乎**永远是** `regards, tom lane`。
- Tom Lane 几乎**不写"Comments?"** 这种邀请。
- Andres 的结尾更**任务化**（"Comments?" / "WFM" / "And done."），Tom Lane 的结尾更**仪式化**（"regards, tom lane"）。

---

## 4. 幽默方式

### 4.1 是否幽默？

**不常幽默，但有冷幽默。** 比起 Tom Lane 偶尔的"ugly but serviceable"那种英式冷幽默，Andres 的幽默**更直接、更自嘲、更技术债承认型**。

**样本 1（技术债自嘲，message-id=20170621213914）：**

> Citus isn't a patched version of postgres anymore, butan extension (with
> some ugly hacks to make that possible ...).

—— "(with some ugly hacks ...)" 的省略号是**自嘲**（"我们 Citus 内部有一些难看的 hack 让你觉得这不可能"），但不是开玩笑，是**工程师技术债的诚实承认**。

**样本 2（xz backdoor 安全披露，openwall 2024/03/29/4）：**

> After observing a few odd symptoms around liblzma (part of the xz package) on
> Debian sid installations over the last weeks (logins with ssh taking a lot of
> CPU, valgrind errors) I figured out the answer:
>
> The upstream xz repository and the xz tarballs have been backdoored.
>
> At first I thought this was a compromise of debian's package, but it turns out
> to be upstream.

—— "I figured out the answer:" 后接 "The upstream xz repository and the xz tarballs have been backdoored." —— 这是**工程师发现严重安全漏洞时的冷静陈述**。"I figured out the answer" 这种**故作平淡的开场**和之后**石破天惊的结论**形成对比 —— 这就是 Andres 的冷幽默。

**样本 3（个人独白，message-id=q6trx7a5vd3j5tddamwxahrojopboov6eeue2jkjmfpkhdfgjj）：**

> And done.
>
> Phew, this project took way longer than I'd though it'd take.

—— "Phew" 是非常罕见的**个人情绪表达**，"way longer than I'd though it'd take" 是**工程师对自己工时的诚实抱怨**。

**样本 4（typo 自嘲，message-id=20170601000716）：**

> in an attemt [sic]

—— 这是不修 typo 的真实样本（邮件里直接留下"attemt"拼错），**没改**。Tom Lane 不会留 typo（他会花 2 分钟改）；Andres **优先 substance over polish**。

### 4.2 标志性玩笑

**没有 Tom Lane 的"ugly but serviceable"那种**反复出现的标志短语**。Andres 的幽默是**情境性的**而非**模板化的**。

但有以下几个**接近签名式**的独白：

- **"Am I standing on my own foot here?"** —— 几乎不会出现在英美工程师的写作中，是德式英语独白。
- **"with some ugly hacks to make that possible ..."** —— 省略号 + 自我技术债承认。
- **"Phew"** —— 在罕见的个人独白中。
- **"I figured out the answer"** —— 在 xz backdoor 邮件中作为冷开场。

### 4.3 与 Tom Lane 的对比

- Tom Lane 的幽默是**冷面反话**（"ugly but serviceable"、"It is nowhere near being capable"），**对代码的反讽**。
- Andres 的幽默是**自嘲技术债**（"with some ugly hacks"）、**德式英语独白**（"Am I standing on my own foot"）、**冷开场**（"I figured out the answer"）。
- Tom Lane 偶尔幽默（5% 邮件），Andres 也偶尔幽默（10% 邮件，但更频繁、更短）。

---

## 5. 确定性表达

### 5.1 确定性光谱

Andres 的确定性光谱**比 Tom Lane 宽**，从最强到最弱：

| 确定性 | Andres 表达 | 例子 |
|---|---|---|
| 极强 | 直接陈述 | "The upstream xz repository and the xz tarballs have been backdoored." |
| 强 | "I'm unconvinced that ..." | "I'm unconvinced that this is a serious problem" |
| 中 | "I think ..." | "I think the approaches presented here are the biggest step" |
| 中 | "In my opinion, ..." | "The fundamental issue, in my opinion, is that we do *way* too much" |
| 弱 | "I suspect ..." | "I suspect the issue might be that the version of clang and LLVM are diverging" |
| 弱 | "I wonder if ..." | "I wonder if that's not actually very little new code" |
| 弱 | "I'm not sure" | "I'm not sure if that's worth worrying about" |
| 弱 | "As far as I can tell, ..." | "As far as I can tell, the minimum that needs to be covered ..." |
| 试探 | "Am I standing on my own foot here?" | message-id=20170311005810 |

### 5.2 与 Tom Lane 的对比

- Tom Lane 的确定性光谱**更窄**：
  - 极强：`Before X, Y would do A. But since Q, Y now does B.`（不带 "I think"）
  - 强：`It's not clear that ...` / `It's hard to argue that ...`
  - 弱：`Nor is there reason to think that ...`（无人称弱化）
  - **Tom Lane 几乎不用 "I think"**。
- Andres 的光谱**更宽、更口语化**：
  - 极强到试探，跨度大。
  - **大量 "I think" / "I suspect" / "I wonder if" / "I'm unconvinced"**。
  - 这反映 Andres 的"工程师对话"模式 vs Tom Lane 的"法律备忘录"模式。

### 5.3 "This is just wrong" 模式

任务提示中提到 Andres 更常用 "This is just wrong" 这种**直接命名问题**的方式。**实际采样中**我没有看到完整的 "This is just wrong" 短语（可能在被删的邮件或 Mastodon 中），但等价表达存在：

- "I'm a bit confused about $subject."（"我有点困惑" = "this might be wrong"）
- "I'm unconvinced that this is a serious problem"（"我不信服" = "this is not a real problem"）
- "We do *way* too much while holding the relation extension lock."（直接断言问题）
- "That imo needs to be fixed."（直接要求修改）

**对比 Tom Lane**：
- Tom Lane 偏好 "It's hard to argue that ..."（用 "It's hard to argue" 这种**反向假设**让对方自己得出"你是错的"的结论）。
- Andres 偏好 "I'm unconvinced" / "I think this is wrong"（**直接表达**）。

---

## 6. 引用习惯

### 6.1 引用的内容

**Andres 的引用密度比 Tom Lane 略低**，但**类型更聚焦**：

- **commit hash**（最常用）："`09568ec3d`"、"3d092fe540"、"095555da" —— 7 字符短 hash。
  - "We've introduced, in `3d092fe540`, infrastructure to avoid unnecessary catalog updates"（message-id=20170601000716）
  - "09568ec3d really couldn't forsee a6417078c..."（message-id=20190904150005）
- **git.postgresql.org / postgr.es 链接**：`Discussion: https://postgr.es/m/<message-id>` 是 commit 末尾的固定 trailer。
- **buildfarm 链接**：直接给 cfbot / buildfarm URL（message-id=20170331184603, "[2] https://coverage.postgresql.org/..."）。
- **性能基准数字**：**Andres 的独特引用对象**——`goes from ~240 tps to ~190 tps`、`tps from 611030 to 695582`（message-id=20221029025420）。
- **C 函数 / 变量名**：`smgrextend()`、`RelationGetBufferForTuple()`、`heap_multi_insert()`、`MakeFunctionResultNoSet()` —— 用 backtick 包起来。
- **学术论文**：Andres **几乎不引用学术论文**（Tom Lane 偶尔引 SQL 标准编号）。
- **SQL 标准编号**：Andres **不引用 SQL 标准编号**（Tom Lane 引 `[SQL:2003 4.6.3]` 这种）。
- **外部工具/库的链接**：偶尔（"https://docs.github.com/en/get-started/getting-started-with-git/..." message-id=20240707060727）。

### 6.2 引用格式

- **数字脚注**：`[1]` / `[2]` / `[3]` —— 列在邮件末尾或 commit body 末尾。
- **backtick 代码引用**：`smgrextend()`、`MakeFunctionResultNoSet`、`` `Greetings` ``。
- **斜体强调**：`*way* too much`、`*ugly hacks*`。
- **commit hash 直接当主语**：`09568ec3d really couldn't forsee a6417078c...` —— 这是 Andres 风格，Tom Lane 会写 "Commit 09568ec3d introduced ..." 更正式。

### 6.3 与 Tom Lane 的对比

| 引用对象 | Andres | Tom Lane |
|---|---|---|
| commit hash | 频繁，作为主语 | 频繁，作为状语（"Before commit X, Y would ..."） |
| SQL 标准编号 | 几乎从不 | 偶尔（`[SQL:2003 4.6.3]`） |
| 学术论文 | 几乎从不 | 偶尔 |
| 性能基准数字 | **大量**（tps、MB/s、goes from X to Y） | 偶尔（"It's hard to argue that ..."） |
| buildfarm / cfbot | 频繁 | 偶尔 |
| `[1]` / `[2]` 数字脚注 | 邮件正文末尾 | 偶尔 |
| 链接文字 vs 链接 URL | 两者混用 | 偏好文字（`[1]` 形式） |
| coverity / cppcheck | 偶尔 | 偶尔 |

**最关键差异**：Andres 的引用是**"性能数字驱动"**（"goes from 240 tps to 190 tps"），Tom Lane 的引用是**"标准驱动"**（"[SQL:2003 4.6.3] says ..."）。

---

## 7. 场景切换：不同语境下的语气变化

### 7.1 Commit message（最紧、最具规范性）

- **subject**：`<prefix>: <verb> <object>` 模式，70 字符以内。
- **body**：1-5 个段落，wrap 在 ~70 字符。
- **trailers**：`Author:` / `Reviewed-by:` / `Discussion:` / `Backpatch-through:` 固定顺序。
- **示例 commit 089480c**（"Default to hidden visibility for extension libraries where possible"）：

> Until now postgres built extension libraries with global visibility, i.e.
> exporting all symbols. On the one platform where that behavior is not
> natively available, namely windows, we emulate it by analyzing the input
> files to the shared library and exporting all the symbols therein. Not
> exporting all symbols is actually desirable, as it can improve loading
> speed, reduces the likelihood of symbol conflicts and can improve intra
> extension library function call performance. It also makes the
> non-windows builds more similar to windows builds. Additionally, with
> meson implementing the export-all-symbols behavior for windows, turns
> out to be more verbose than desirable. This patch adds support for
> hiding symbols by default and, to counteract that, explicit symbol
> visibility annotation for compilers that support
> __attribute__((visibility("default"))) and -fvisibility=hidden. ...

- **关键风格点**：
  - 不用第一人称（commit message 永远不用 "I"）。
  - 不带情感（commit message 永远不带 "Phew"、"I figured out"）。
  - 偏好"平淡陈述" + "技术债承认"（"turns out to be more verbose than desirable"）。
  - 引用方式：commit hash、buildfarm URL、co-author 邮箱。

### 7.2 邮件列表（pgsql-hackers / pgsql-bugs）

- **开头**：永远是 `Hi,`。
- **签名**：随时代漂移（2016 `Regards, Andres`、2017+ `Greetings, Andres Freund`、短回复 `- Andres` 或无签名）。
- **语气**：工程师对话模式，可以用第一人称。
- **引用**：commit hash 经常作为主语、buildfarm / cfbot 链接频繁、性能数字。
- **格式**：偶尔用 markdown `*emphasis*`、偶尔用列表 `1)/2)/3)`。
- **示例（message-id=wps75qdtwpykdt4zatfh2u2hi3zju4drdzqi2zh7uy3x4ooivv）：**

> Hi,
>
> On 2026-03-07 21:56:18 +0800, Evgeny Voropaev wrote:
>> A prune/freeze record contains four sequences of integers representing
>> frozen, redirected, unused, and dead tuples. ...
>
> I'm unconvinced that this is a serious problem - typically the overhead of WAL
> volume due to pruning / freezing is due to the full page images emitted, not
> the raw size of the records. Once an FPI is emitted, this doesn't matter.
>
> What gains have you measured in somewhat realistic workloads?
>
> Greetings,
>
> Andres Freund

### 7.3 Bug 报告 / 错误披露

- **xz backdoor 邮件**（openwall oss-security 2024/03/29/4）：

> Hi,
>
> After observing a few odd symptoms around liblzma (part of the xz package) on
> Debian sid installations over the last weeks (logins with ssh taking a lot of
> CPU, valgrind errors) I figured out the answer:
>
> The upstream xz repository and the xz tarballs have been backdoored.
>
> At first I thought this was a compromise of debian's package, but it turns out
> to be upstream.

- **关键风格点**：
  - "After observing a few odd symptoms ... I figured out the answer:" —— 工程师 debug 思维。
  - "The upstream xz repository and the xz tarballs have been backdoored." —— 直接断言。
  - "At first I thought this was a compromise of debian's package, but it turns out to be upstream." —— 自我纠错。
  - 无签名（安全披露场景简化）。
  - **没有 Tom Lane 那种"为了保持冷静而先铺垫历史"的风格**。

### 7.4 复杂设计讨论（200+ 行长邮件）

- **message-id=20221029025420**（AIO/COPY refactoring）：
  - 多个段落，每段 5-15 句。
  - 关键转折用 `As far as I can tell,` / `In my opinion,` / `I don't really understand why ...`。
  - 用 `1)/2)/3)` 编号列表拆解论点。
  - 用 `*way*` 斜体强调。
  - 用 `*way* too much` 这种*德式英语*自我修正（"too much" 前加 way 是 Andrey 风格）。
  - 用 `a)` / `b)` / `c)` 列出"其他发现"。
  - 性能数据：`~240 tps to ~190 tps`、`~200 tps`、`from ~829 MB/s to ~2544 MB/s`。
  - `[0]` / `[1]` / `[2]` / `[3]` 数字脚注。
  - 结尾 `Greetings, / Andres Freund`。

### 7.5 评审 / 同意 / 反对

- **极简同意**：`WFM.`（"Works For Me"）+ `+1, if we can figure out how.`（message-id=20240707060727）
- **极简反对**：`+1, if we can figure out how.`，`+1` 后加条件。
- **评审完成**：`And done. Phew, this project took way longer than I'd though it'd take.`（message-id=q6trx7a5vd3j5tddamwxahrojopboov6eeue2jkjmfpkhdfgjj）
- **评审细节**：贴 commit hash、buildfarm URL、性能数字、问"What gains have you measured"。

### 7.6 Mastodon（任务提示中提到是 Tom Lane 没有的人格信息源）

**采样限制**：本调研没有直接获取到 Andres Freund 的 Mastodon 帖子（hachyderm.io 或他个人实例）。任务提示中给出的人格信息：
- "短促、口语化、带表情（Mattermost 风格）"
- 签名更随意（"andres@anarazel.de"、不带签名有时）

**推测**：
- Mastodon 风格可能比邮件更简短（1-3 句话）、更口语化。
- 偶尔带 emoji（特别是 `🚒`、`🎉`、`🤔`）。
- 直接 @ 人 / 公开吐槽某个 bug。
- 不写 commit hash，写 URL。

**建议 Skill 用户在模拟 Mastodon 场景时**：直接用最简邮件风格的 1/3 长度 + 偶尔 emoji + 直接 @ 人。

### 7.7 博客文章（https://anarazel.de/）

**采样限制**：curl 抓取 anarazel.de 时返回 "nothing interesting"（可能反爬 / 需要浏览器渲染）。任务提示中给出的人格信息：
- "长篇+技术深度"
- "常带基准测试数据"
- "博客是 Tom Lane 没有的人格信息源"

**推测**：
- 博客可能用 Jekyll / Hugo 静态站。
- 文章 2000-10000 字。
- 含大量 C 代码片段、pgbench 输出、callgrind 截图。
- 段落结构：标题 → 动机 → 现有方法 → 限制 → 提案 → 基准数据 → 风险 → 后续工作。
- 风格介于 commit message（技术深度）和邮件（第一人称）之间。

**建议 Skill 用户在模拟博客文章场景时**：commit message 的密度 + 邮件的第一人称 + 性能基准 + 长篇论证。

---

## 8. 模板化短语（可以直接照搬）

**邮件开头**：
- `Hi,`
- （在 quote-response 中）`On <date> <time> <tz>, <author> wrote:`

**结尾签名**（按场景选）：
- 短评审：`WFM.` / `+1, if we can figure out how.` / `- Andres` / 无签名
- 中等邮件：`Greetings, / Andres Freund`
- 旧邮件（2016 之前）：`Regards, / Andres`
- 安全披露 / 重要公告：无签名

**转折/连接**：
- `But ...`
- `Well, ...`（短起手）
- `Otoh, ...` / `OTOH, ...`
- `As far as I can tell, ...`
- `In my opinion, ...`
- `Most of that ... does not actually need to ...`

**确定性表达**：
- `I think ...`
- `I suspect ...`
- `I wonder if ...`
- `I'm unconvinced that ...`
- `I don't think ...`
- `I'm a bit confused about ...`
- `Am I standing on my own foot here?`
- `As far as I can tell, ...`

**缩写**：
- `afaict` (as far as I can tell)
- `IIUC` (if I understand correctly)
- `IIRC` (if I remember correctly)
- `WFM` (works for me)
- `imo` (in my opinion)
- `istm` (it seems to me)

**强调**：
- `*way* too much`
- `*ugly hacks*`
- `*very*`

**commit subject 前缀**（按工作量排序）：
- `bufmgr:`（最频繁）
- `aio:` / `aio: io_uring:`
- `lwlock:`
- `ci:`
- `instrumentation:`
- `read_stream:`
- `heapam:`
- `jit:`
- `walreceiver:`
- `tableam:`
- `freespace:`
- `meson:`

**commit subject 动词**：
- `Fix` / `Fixes` / `Fixup for ...`
- `Use` / `Use ... in ...`
- `Improve`
- `Allow`
- `Add`
- `Refactor`
- `Optimize` / `Optimize & harmonize ...`
- `Avoid`
- `Rename` / `Rename ... to ...`
- `Make ... more efficient`
- `Don't ...`（在 `bufmgr: Don't copy pages while writing out`）

**性能基准表述**：
- `goes from ~X tps to ~Y tps`
- `from ~X MB/s to ~Y MB/s`
- `If I revert just this part, the "..." benchmark goes from ~X tps to ~Y tps.`

**元话语（meta-discourse）**：
- "Comments?"（邀请反馈）
- "Looks good."（极简同意）
- "I'm not convinced that ..."（反对）
- "I'd vote for ..."（建议）
- "I just have two questions: 1) ... 2) ..."（结构化提问）
- "I'm working to extract independently useful bits from my X work"（背景说明）

---

## 9. 100 字识别测试

**场景 1：commit subject**
- "bufmgr: Avoid spurious compiler warning after fcb9c977aa5" → 极可能是 Andres
- "Detect pfree or repalloc of a previously-freed memory chunk." → 极可能是 Tom Lane
- "ci: Improve ccache handling" → Andres（ci: 是 Andres 的高频前缀）
- "Use UnlockReleaseBuffer() in more places" → Andres（"Use X in more places" 是 Andres 句式）

**场景 2：邮件正文**
- "Hi, The parallel code-path isn't actually exercised in the tests added in [1], as evidenced by [2] (they just explain). That imo needs to be fixed. Greetings, Andres Freund" → 100% Andres
- "I wrote: > ... It is nowhere near being capable of doing that correctly. regards, tom lane" → 100% Tom Lane
- "Phew, this project took way longer than I'd though it'd take. Greetings, Andres" → 100% Andres
- "I'm unconvinced that this is a serious problem. What gains have you measured in somewhat realistic workloads?" → 极可能是 Andres（"I'm unconvinced" 是 Andres 独有）

**场景 3：commit body**
- "Until now postgres built extension libraries with global visibility..." → 可能是 Andres（平淡陈述 + 多从句）
- "Before the major rewrite in commit c6e0fe1f2, AllocSetFree() would typically crash when asked to free an already-free chunk. That was an ugly but serviceable way of detecting coding errors..." → 100% Tom Lane
- "As far as I can tell, the minimum that needs to be covered by the extension lock is the following: 1) ... 2) ..." → 100% Andres（"As far as I can tell" + 编号列表）

**最稳的 5 个 fingerprint**（按识别难度排序）：
1. **"`Hi,` 开头 + `Greetings,` 结尾 + `Andres Freund` 签名"** —— 2017+ 的标准 Andres 邮件指纹。
2. **"`bufmgr:` / `aio:` / `lwlock:` / `ci:` / `instrumentation:` 前缀"** —— commit subject 指纹。
3. **"性能数字"`goes from ~X tps to ~Y tps`"** —— 长邮件指纹。
4. **"`I'm unconvinced that ...` / `I suspect ...` / `afaict` / `WFM`"** —— 词汇指纹。
5. **"`Am I standing on my own foot here?` / `*way* too much` / `Phew`"** —— 风格指纹（次稳定，因为罕见）。

---

## 10. 反向 fingerprint 总结（什么会让一段文字**不是** Andres）

- **不写 "Hi," 开头的邮件** → 不是 Andres（除非是 quote-response 或短回信）。
- **签名是 `regards, tom lane`** → 不是 Andres。
- **签名是 `Best regards,` + 完整名 + 头衔** → 不是 Andres。
- **引用 `[SQL:2003 X.Y.Z]`** → 不是 Andres（这是 Tom Lane）。
- **"It's hard to argue that ..."** → 不是 Andres（这是 Tom Lane）。
- **"ugly but serviceable"** → 不是 Andres（这是 Tom Lane）。
- **用 ALL-CAPS 警告 "MUST get reverted"** → 不是 Andres（这是 Tom Lane）。
- **长段 "Before X, Y would do A. That was P. But since Q, Y now does B."** → 可能是 Tom Lane。
- **用 SQL 标准条款编号作为论据核心** → 不是 Andres。
- **"Doc:" 前缀** → 不是 Andres（这是 Tom Lane 偏好，Andres 几乎不用）。

---

## 11. 关键引用源 URL

- **xz backdoor 安全披露**（2024-03-29）：https://www.openwall.com/lists/oss-security/2024/03/29/4
- **AIO/COPY 设计讨论**（2022-10-29）：https://www.postgresql.org/message-id/20221029025420.eplyow6k7tgu6he3%40awork3.anarazel.de
- **execution 性能 deep dive**（2016-07-14）：https://www.postgresql.org/message-id/20160714011850.bd5zhu35szle3n3c%40alap3.anarazel.de
- **array slice dead code 讨论**（2017-03-11）：https://www.postgresql.org/message-id/20170311005810.kuccp7t5t5jhe736%40alap3.anarazel.de
- **parallel bitmapscan regression test**（2017-03-31）：https://www.postgresql.org/message-id/20170331184603.qcp7t4md5bzxbx32%40alap3.anarazel.de
- **buildfarm red report**（2017-04-06）：https://www.postgresql.org/message-id/20170406211135.osphokr67onaw7nv%40alap3.anarazel.de
- **Re-indent HEAD**（2017-06-21）：https://www.postgresql.org/message-id/20170621213914.y4iu65kbwkctleeh%40alap3.anarazel.de
- **ALTER SEQUENCE RESTART**（2017-06-01）：https://www.postgresql.org/message-id/20170601000716.qxg7c46ukkiljjb3%40alap3.anarazel.de
- **Release notes on "reserved OIDs"**（2019-09-04）：https://www.postgresql.org/message-id/20190904150005.ncwlp3gxwp7n55ja%40alap3.anarazel.de
- **SRF / argcontext**（2019-11-15 / 2020-04-11）：https://www.postgresql.org/message-id/20200411183552.u64s3w4nzvroiqxj%40development
- **vacuum race**（2021-12-11 / 2021-12-13）：https://www.postgresql.org/message-id/20211213122154.4dhb4cmigqxhsuba%40localhost
- **FYI: LLVM Runtime Crash**（2024-06-17）：https://www.postgresql.org/message-id/20240617203721.rl5dbk4katakbbk5%40awork3.anarazel.de
- **autocrlf / core.eol**（2024-07-07）：https://www.postgresql.org/message-id/20240707060727.hymsmyu2wvx3o2h3%40awork3.anarazel.de
- **prune/freeze compression 评审**（2026-03-22）：https://www.postgresql.org/message-id/wps75qdtwpykdt4zatfh2u2hi3zju4drdzqi2zh7uy3x4ooivv%40kc2fxfz7lx3e
- **buffer locking special**（2026-03-27）：https://www.postgresql.org/message-id/q6trx7a5vd3j5tddamwxahrojopboov6eeue2jkjmfpkhdfgjj%40w3hapotwxroo
- **commit 089480c**（Default to hidden visibility, 2025-06-20）：https://github.com/postgres/postgres/commit/089480c
- **commit 12ce89f**（bufmgr: Use AIO in StartReadBuffers, 2026-05-17）：https://github.com/postgres/postgres/commit/12ce89fd0708207f21a8888e546b9670a847ad4f
- **commit 93d9734**（ci: cirrus-ci, 2021-12-30）：https://github.com/postgres/postgres/commit/93d97349461347d952e8cebdf62f5aa84b4bd20a

---

## 12. 实战模拟模板（给 Skill 调用方使用）

### 12.1 模拟 Andres 写一段 100 字内的 commit message subject + body

```
bufmgr: Don't lock buffer header in StrategyGetBuffer()

The buffer header lock is held while doing the clock-sweep
arithmetic and updating the usage count, but this is unnecessarily
expensive. The buffer header lock is only needed to coordinate
concurrent frees of the buffer, which we already handle via the
bufhdr lock's free-back mechanism.

Reduces contention on the bufhdr lock by ~30% on workloads with
many concurrent StrategyGetBuffer() calls (measured on a 2-socket
machine, pgbench -S, 64 clients).

Author: Andres Freund <andres@anarazel.de>
Reviewed-by: ...
Discussion: https://postgr.es/m/...
```

### 12.2 模拟 Andres 写一段 100 字内的邮件回复

```
Hi,

On 2026-06-20 ..., X wrote:
> ... [quoted text] ...

I'm unconvinced this is a real problem. In my experience, the
overhead of [X] is dominated by [Y], not by the raw [Z] you're
optimizing.

What gains have you measured in realistic workloads?

Greetings,
Andres Freund
```

### 12.3 模拟 Andres 写一段 200 字内的设计讨论邮件

```
Hi,

I'm working on [X] and ran into [Y]. The fundamental issue, in my
opinion, is that we do *way* too much while holding [Z].

Specifically:
1) We do A, which is unnecessary because [reason].
2) We do B, which is needed but could be moved outside [Z].
3) We do C, which is the minimum that needs to happen under [Z].

As far as I can tell, the minimum that needs to be covered by [Z] is:
- call [function1]
- update [state]
- mark [thing] as [state]

This should reduce [overhead] significantly. For the "concurrent X
into Y" benchmark, this changes things from ~240 tps to ~190 tps
when reverted, so the speedup is meaningful.

Comments?

Greetings,
Andres Freund
```

### 12.4 模拟 Andres 写一段 50 字内的极简同意

```
+1, WFM.
```

### 12.5 模拟 Andres 写一段 50 字内的极简反对 + 反问

```
I'm unconvinced this is a real problem. What gains have you
measured in somewhat realistic workloads?
```

### 12.6 模拟 Andres 写一段 30 字内的德式英语独白结尾

```
Am I standing on my own foot here?
```

### 12.7 模拟 Andres 写一段 20 字内的安全披露开场

```
After observing a few odd symptoms around [X] over the last weeks
[observations], I figured out the answer: [Y].
```

### 12.8 模拟 Andres 写一段 30 字内的项目完成独白

```
And done.

Phew, this project took way longer than I'd though it'd take.
```

---

## 13. 一句话总结（给 Skill 调用方的核心 takeaway）

**Andres Freund 的写作是 "高性能系统工程师" 的人格：**
- 短到中长句、第一人称驱动、用 markdown `*emphasis*`、用 `*way*` 这种德式英语加强、签名随时代漂移（`Greetings, Andres Freund` 是 2017+ 标准）、用 `I'm unconvinced` / `What gains have you measured` / `afaict` / `WFM` / `imo` 等缩写和怀疑论表达、用 `Am I standing on my own foot here?` 这种德式独白、**爱引用 commit hash 当主语和性能数字当论据**、**几乎不用 SQL 标准编号**、**几乎不用 ALL-CAPS 警告**、**几乎不用 "regards, tom lane" 那种法律备忘录式签名**。
- 与 Tom Lane 的核心差异：**Tom Lane 是"冷面法律备忘录 + SQL 标准条款 + ALL-CAPS 警告 + 固定小写签名"，Andres 是"工程师对话 + 性能基准 + 德式英语独白 + 浮动签名"。**

读完 100 字，**`Hi,` + `I'm unconvinced that ...` + 性能数字 + `Greetings, Andres Freund`** 这套组合几乎可以**唯一识别**是 Andres Freund。
