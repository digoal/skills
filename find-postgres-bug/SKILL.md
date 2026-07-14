---
name: find-postgres-bug
description: "在给定的 PostgreSQL 源码目录中系统化挖掘尚未被社区报告的未知 bug（内存错误、并发/锁问题、优化器逻辑错误、边界溢出等），产出可复现、可提交给 PostgreSQL 官方安全邮件列表或 bug 表单的中文诊断报告。触发条件：用户提供了 PostgreSQL 源码目录路径，并提到\u201c找 PostgreSQL bug\u201d、\u201c挖掘数据库漏洞\u201d、\u201c找未知 bug\u201d、\u201cfuzz postgres\u201d、\u201c内核 bug 猎手\u201d、\u201c帮我审查这段 PG 源码有没有问题\u201d、\u201c这个提交安全吗\u201d、\u201c我要给社区提 bug\u201d、\u201cfind postgres bug\u201d、\u201cPG 源码找 bug\u201d，或希望对 PostgreSQL 源码做 sanitizer 构建、模糊测试、差分测试、并发压力测试、历史提交模式挖掘、新提交审查等任一环节。即使用户只说\u201c帮我看看这份 PG 代码有没有隐藏问题\u201d或\u201c我想给 PostgreSQL 社区贡献一个 bug 报告\u201d，只要涉及源码目录 + 挖掘未知缺陷，也应使用本 skill。本 skill 仅用于合法的开源安全研究与负责任披露，绝不用于攻击生产环境或未获授权的系统。"
---

# PostgreSQL 未知 Bug 猎手 (find-postgres-bug)

给定一个 PostgreSQL 源码目录，综合运用「历史提交模式挖掘 + 静态模式扫描 + sanitizer 构建 + 模糊测试 + 差分测试 + 并发压力测试 + 新提交审查」七个维度，系统化挖掘**尚未被社区报告**的潜在 bug，并输出结构化中文报告，指向 PostgreSQL 官方负责任披露渠道。

本 skill 只做**发现与复现**，不做利用（exploit）开发，不做拒绝服务式的攻击性使用；所有测试只针对用户本地/隔离的开发实例，绝不针对生产库或未获授权系统。

## 前置要求

在开始前，确认以下工具链已安装（缺失时给出安装命令，不要静默跳过）：

```bash
# 编译工具链
gcc --version || sudo yum install -y gcc gcc-c++ make readline-devel zlib-devel
clang --version   # 用于 sanitizer 构建，推荐优先使用 clang

# 可选但强烈建议的分析工具
which valgrind      || sudo yum install -y valgrind
which coccinelle    || pip install --user coccinelle 2>/dev/null || echo "需手动安装 spatch"
which semgrep       || pip3 install --break-system-packages semgrep
which git           || sudo yum install -y git
python3 --version
```

Fuzzing 相关工具按需安装（在第 4 阶段之前提醒用户）：SQLsmith、AFL++、libFuzzer。这些不是每次都需要，先完成前 3 个阶段更划算。

**输入确认**（向用户确认，缺一则用默认值/最佳猜测并说明假设）：
1. PostgreSQL 源码目录绝对路径（必需，如 `/data/postgresql`）
2. 目标分支/版本（默认：当前 checkout 的分支，通常是 `master` 或某个 `REL_xx_STABLE`）
3. 是否已有可用于 fuzz 的测试实例，还是需要现场 `initdb` 一个（默认现场建一个一次性实例）
4. 本次挖掘的重点方向（可选，如"重点看并发索引构建"或"不限"，默认不限，走全流程）
5. 时间预算（模糊测试/压力测试是耗时任务，务必确认用户能接受的时长，默认单轮 30 分钟）

## 工作流程总览

七个阶段按顺序推进，但**不是每次都要跑满七个阶段** —— 根据用户的时间预算和重点方向裁剪。默认策略：阶段 1-3（静态、低成本）必跑；阶段 4-7（动态、高成本）按时间预算选择性跑，并在开始前明确告知用户预计耗时。

```
阶段1 带刺环境构建 → 阶段2 历史模式挖掘 → 阶段3 模式扫描狩猎
   → 阶段4 模糊测试 → 阶段5 差分测试 → 阶段6 并发压力测试 → 阶段7 新提交审查
                                  ↓
                          汇总为结构化报告
```

### 阶段 1：构建带检测器的调试环境

执行 `scripts/01_setup_sanitizer_build.sh <源码目录>`。该脚本会：
- 用 `--enable-cassert --enable-debug` + ASan/UBSan 配置并编译（`-O1` 保留栈追踪能力）
- 编译产物放在源码目录下的独立 `build-sanitizer/` 子目录，不污染用户原有构建
- 编译完成后跑一次 `make check`，确认基础回归测试通过（否则后续发现的"bug"可能只是环境问题）
- 记录编译日志到 `find-bug-artifacts/build.log`，出现警告不要忽略，摘要给用户看

如果用户机器资源紧张（CPU/内存不足以支撑 ASan 构建），如实告知构建会明显变慢/占用更多内存，并询问是否继续。

### 阶段 2：把提交历史变成"错误模式教科书"

执行 `scripts/02_mine_historical_bugs.sh <源码目录> [起始版本] [结束版本]`。该脚本：
- 拉取全部分支/标签
- 按关键词（fix/bug/crash/leak/overflow/race/deadlock/corrupt 等，见 `references/bug_pattern_catalog.md` 的关键词表）扫描历史提交
- 对每个命中提交抓取 diff，按 `references/bug_pattern_catalog.md` 中的六大类（内存管理/并发锁/边界溢出/逻辑错误/资源泄漏/类型转换）打标签
- 输出 `find-bug-artifacts/historical_patterns.md`：每条记录包含 commit hash、修复日期、bug 类别、关键 diff 片段、可泛化的"不安全模式"描述

**这一步的产出是后续阶段 3 和阶段 7 的输入** —— 不要跳过，即使用户赶时间也建议至少跑一次（增量运行很快，脚本支持 `--since` 参数只看最近的历史）。

阅读 `references/bug_pattern_catalog.md` 了解每个类别的判断标准和历史真实案例，用它来指导你人工复核脚本产出的候选模式，去掉明显误报（比如注释里提到"fix"但代码逻辑与 bug 无关的提交）。

### 阶段 3：静态模式扫描狩猎

基于阶段 2 提炼出的模式，选择 1-3 个当前会话最值得深挖的模式（例如"错误路径遗漏 pfree"、"CHECK_FOR_INTERRUPTS 缺失导致的死锁窗口"），执行：

```bash
python3 scripts/03_pattern_scan.py --source-dir <源码目录> --pattern <模式名>
```

支持的内置模式见 `references/bug_pattern_catalog.md` 的"内置扫描模式"表（脚本 `--list-patterns` 可查看）。每个模式对应一段 semgrep 规则或简化的 AST 遍历逻辑，找到候选点后：
- **不要**直接下结论"这是 bug"，候选点只是需要人工复核的嫌疑对象
- 对每个候选点，结合上下文判断是否真的会触发（很多 `palloc` 后没有立即 `pfree` 是因为走到了内存上下文自动回收，这是正常模式，不是 bug）
- 把通过复核、确实可疑的点记录到 `find-bug-artifacts/candidates.md`，标注文件、行号、可疑原因、初步置信度（低/中/高）

如果用户环境装了 `coccinelle`（`spatch`），也可以直接用 `references/coccinelle_patterns.cocci` 里的语义补丁做全库扫描；没装则用 Python/semgrep 版本兜底。

### 阶段 4：多维度模糊测试（可选，视时间预算）

告知用户预计耗时后再开始。执行 `scripts/04_run_fuzzing.sh <build-sanitizer 目录> [时长秒数]`：
- 用 `initdb` 拉起一个一次性测试实例（数据目录放在临时目录，退出后清理）
- 连接凭据只用 `PGPASSWORD` 环境变量传递，绝不写入脚本或日志明文
- 如果检测到 SQLsmith 已安装，跑 SQL 层随机语法 fuzz；否则提示安装命令并跳过
- 如果检测到 AFL++/libFuzzer 环境，可选跑内部函数级 fuzz（日期解析器、WAL 记录解码等），这一项复杂度高，默认跳过，除非用户明确要求
- 监控 ASan/UBSan 输出与 postgres 日志中的 `PANIC`/`FATAL`/sanitizer 报错，一旦出现立刻停止 fuzzer 并保存现场（core dump、日志、触发用的 SQL/输入）到 `find-bug-artifacts/crash_<时间戳>/`

### 阶段 5：差分测试

执行 `scripts/05_differential_test.py`，支持两种模式：
- **跨版本对比**：同时起两个不同版本/分支的实例，灌相同的随机 SQL（复用阶段 4 的 SQLsmith 语料），对比结果和错误码，任何非预期不一致都要记录
- **同版本变换优化器参数对比**：固定版本，切换 `enable_hashjoin`/`enable_indexscan`/`enable_seqscan` 等参数组合，跑同一复杂查询，用哈希对比结果集是否一致

差异记录到 `find-bug-artifacts/diff_findings.md`，注意排除已知的、文档化的行为差异（如不同版本对未定义排序的处理），只保留真正矛盾的结果。

### 阶段 6：并发与压力测试

执行 `scripts/06_concurrency_stress.sh`：
- 并行跑 DDL（`CREATE INDEX CONCURRENTLY`、`ALTER TABLE`）+ DML 组合，同时随机杀连接、强制 checkpoint
- 每轮结束后用 `amcheck` 扩展（`bt_index_check`/`bt_index_parent_check`）校验索引完整性，异常立刻记录
- 可选：极端资源限制场景（`shared_buffers` 极小、`max_connections` 极低），观察 OOM/连接风暴处理路径是否优雅

### 阶段 7：新提交的即时审查

如果用户想审查最近一段时间的新提交（而非历史挖掘），执行 `scripts/07_new_commit_review.sh <源码目录> [天数，默认7]`：
- 列出窗口期内的所有提交 diff
- 用阶段 2 沉淀的模式库自动打分（改了哪些函数的调用者、新增内存上下文是否有对应释放路径、共享内存结构改动是否考虑对齐/信号安全）
- 输出 `find-bug-artifacts/recent_commit_review.md`，标注每个提交的风险分与理由

## 汇总输出：结构化 Bug 报告

所有阶段跑完后，读取 `references/report_template.md` 的模板，为每一个**通过人工复核、置信度为中或高**的候选生成一份独立报告，保存到 `find-bug-artifacts/reports/`。绝不要为低置信度、未复现的猜测生成正式报告——那样只会浪费社区审阅者的时间。

每份报告必须包含：
1. 一句话摘要（现象 + 影响面）
2. 复现步骤（编号列表，包含确切的配置、SQL、时序）
3. 预期行为 vs 实际行为
4. 涉及的源码位置（文件:行号 + 函数名）与可能的根因分析
5. 置信度与理由（这是"确认的 bug"还是"需要社区确认的可疑行为"）
6. 建议的披露渠道（见下方"负责任披露"）

## 负责任披露

- 涉嫌安全问题（可能导致崩溃、越权、数据损坏、拒绝服务）→ 建议发送至 **security(at)postgresql(dot)org**，报告中不要包含可直接复制粘贴发出去的完整利用代码，只给出复现所需的最小信息
- 普通功能性 bug（无安全影响的逻辑错误）→ 建议提交至 [PostgreSQL 官方 bug 表单](https://www.postgresql.org/account/submitbug/)
- 在生成报告前，**先检查是否已被报告过**：搜索 [已知问题/邮件列表归档](https://www.postgresql.org/list/) 和 commitfest，避免重复提交
- 详细步骤见 `references/disclosure_guide.md`

## Pitfalls & Solutions

| 坑点 | 解决方案 |
|------|----------|
| ASan 构建下 `make check` 本身就失败 | 先排查是否为已知的 sanitizer 误报（PostgreSQL 有专门的 `--disable-sanitizer-checks` 测试排除列表），不要把已知问题当新发现 |
| 模式扫描误报率高 | 阶段 3 强调"候选点需人工复核"，脚本只做粗筛，最终判断权在人 |
| Fuzzing 长时间无产出 | 正常现象，deep bug 需要数小时到数天。建议先用 SQLsmith 跑通链路，再逐步升级到 AFL++ 内部函数 fuzz |
| 差分测试发现"不一致"实为文档化行为 | 对照发行说明（release notes）核实是否为已知变更，而非真 bug |
| 凭据/密码明文出现在日志 | 所有连接一律通过 `PGPASSWORD` 环境变量传递，脚本内绝不 echo 密码，日志输出前脱敏检查 |
| 用户想直接在生产库上跑 fuzz/压力测试 | **拒绝**，明确告知本 skill 只能用于隔离的开发/测试实例，并解释原因（数据损坏、服务中断风险） |

## 注意事项

- **绝不**在生产环境或未获授权的实例上执行本 skill 的任何动态测试阶段（4/5/6）；如果用户提供的是生产库连接信息，先确认清楚并建议改用一次性实例
- 所有数据库连接凭据只通过 `PGPASSWORD` 环境变量传递，不写入脚本、不写入日志、不硬编码
- 所有临时数据目录、fuzz 语料、crash 现场文件都放在 `find-bug-artifacts/` 下，任务结束后提醒用户是否需要清理
- 模糊测试、差分测试、并发压力测试都是耗时任务，开始前必须和用户确认时间预算，不要无限跑下去
- 输出报告一律使用中文，但涉及提交给 PostgreSQL 官方渠道的内容（邮件正文、bug 表单）应额外提供英文版本，因为上游社区以英文沟通为主
- 本 skill 仅服务于合法的开源安全研究与负责任披露，不协助编写针对目标系统的攻击性利用代码
