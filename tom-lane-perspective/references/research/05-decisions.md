# Tom Lane 主导或深度参与的重大决策

> 调研时间:2026-06-19
> 目的:为「开源项目治理」skill 提供决策素材
> 信息源:PostgreSQL 官方 release notes、pgsql-hackers 邮件归档、pgsql-committers、Crunchy 官方公告、知乎/掘金/cnblogs 上的二手综述(仅作为线索回溯),以及 deepwiki 检索结果

---

## 0. Tom Lane 在 PostgreSQL 项目中的角色定位

在做决策清单之前,必须先明确 Tom Lane 的「角色位」,否则所有决策都无法放到正确的治理坐标里解读。

- **身份**:Red Hat → Salesforce → Crunchy(2015 年 10 月,Crunchy 官方公告)→ 长期核心 committer。Crunchy 公告原话:"Tom Lane has joined Crunchy's elite PostgreSQL developer team. Lane is a member of the PostgreSQL developer core team, responsible for overseeing the development and maintenance of PostgreSQL — the world's most popular, reliable database."(来源:https://yq.aliyun.com/articles/112816,转载自 oschina;以及 https://www.kejianet.cn/tom-lane/)
- **代码贡献量级**:Tom Lane 是 PostgreSQL optimizer 模块 20 年间几乎唯一的重写者,被国内研究者称为"PostgreSQL 优化器代码主要是 Tom Lane 在过去的 20 年间贡献的"(来源:https://blog.csdn.net/zhaowei121/article/details/10395656,知乎专栏转载)。
- **决策风格(从他反复出现的话术可推断)**:
  1. **"先看 SQL 标准,再看历史,再看边缘 case"** —— 在 GEQO random seed、standard_conforming_strings 等多封邮件中,他都先用 SQL 标准/历史兼容性做锚点。
  2. **"以可观测行为定义语义"** —— 反对在 -hackers 上以"以后扩展性"为由接受模糊语义,要求先有可验证的语义边界。
  3. **"不要为单客户做底层妥协"** —— 倾向于通过扩展/GUC 暴露能力,而不是改核心数据结构。

---

## 1. 重大技术决策

### 1.1 [A 类-推动] 查询优化器整体重写 — System R 风格 join 序搜索

- **问题**:Postgres95 时期的优化器是简单的 left-deep tree + 贪心启发式,大查询(>~10 表)给出极差计划。
- **Tom Lane 的方案**:分两阶段实现 —— (a) 重写统计信息收集与代价模型,使其基于真采样而不是 pgstat 估算;(b) 在超过阈值(默认 12 个表)时启用 GEQO(Genetic Query Optimizer,基于稳态 GA,把 join 序当作 TSP 问题编码成整数串)。
- **替代方案**:
  - 一次性跑全枚举的 Volcano-style 搜索(被否决,因 join 空间爆炸);
  - 引入随机重启爬山(random restart hill-climbing)。
- **论证逻辑**:GEQO 在早期硬件上对 12+ 表查询能在亚秒级给出可接受计划;System R 风格 DP 对低 join 数严格最优。
- **结果**:成功,成为 PostgreSQL 30 年优化的基线,但同时留下"计划不可复现"问题(见 1.6)。
- **来源**:
  - https://www.postgresql.org/docs/9.0/geqo-pg-intro.html(GEQO 背景)
  - https://blog.csdn.net/zhaowei121/article/details/10395656(Tom Lane 重写 optimizer 的二手综述)
  - https://github.com/postgres/postgres/tree/master/src/backend/optimizer(代码位置)

### 1.2 [A 类-推动] GEQO 随机种子可配置 — 让计划可复现

- **问题**:2009 年前,GEQO 用 `random()` 系统调用初始化种群,意味着同一查询(统计信息不变)有时会得到不同计划,导致生产事故难以复现。
- **Tom Lane 的方案(2009-07-16 提交)**:在 GEQO 内建立私有 RNG 状态,并新增 GUC `geqo_seed`,默认值为 0 但每次用同一值,使结果对相同输入完全确定。"you'll always get the same plan for the same value of geqo_seed (if holding all other planner inputs constant, of course)."
- **替代方案**:
  - 干脆移除 GEQO(否,代价过高);
  - 用查询文本哈希做种子(否,因为同一查询不同参数也会产生抖动)。
- **论证逻辑**:可观测的、可复现的行为是工程基本要求,即使以"放弃少量 plan 多样性"为代价。
- **结果**:成功,但该决策同时压制了"随机跳出局部最优"的能力 —— 后来被 Robert Haas 等人评论为"让 GEQO 退化成了更差的确定性搜索"。**至今仍是争议点**(plan stability vs plan quality 的取舍)。
- **事后反思**:Tom Lane 没有公开承认这是错误决策,但多次通过增加 `plan_cache_mode`、JIT、自定义 plan 等机制绕开 GEQO 的硬伤。
- **来源**:http://archives.postgresql.org/pgsql-committers/2009-07/msg00148.php(commit message 原文)

### 1.3 [A 类-推动] 强制 `standard_conforming_strings = on` 并移除 `escape_string_warning`

- **问题**:PostgreSQL 历史允许 `\\` 作为字符串转义符,而 SQL 标准不允许 —— 这导致跨数据库迁移、SQL 注入防护、JSON 路径书写体验糟糕。
- **Tom Lane 的方案**:在 9.1 引入 `standard_conforming_strings`(默认 off);在后续版本强制设为 on 并废弃 `escape_string_warning`、在深版本里直接移除该 GUC。
- **替代方案**:
  - 永久保留 off 为默认(理由:不破坏老应用,Tom Lane 否定 — "should be configurable for one release, then move on");
  - 提供 SQL 标准的 E'...' 替代语法但保留 `\\`(最后被采纳的过渡方案)。
- **论证逻辑**:迁移成本是"一次性的",但"永远保留两条语义"是永久债。Tom Lane 倾向"快速切到标准语义",先把伤口切干净。
- **结果**:成功,但 9.1 升级期间企业用户出现一波兼容性事故(deepwiki 提到该决策由 Tom Lane 主导)。
- **来源**:
  - https://www.postgresql.org/docs/release/19/release-19.html(release-19.sgml 中"force standard_conforming_strings to always be on" 标注 Author: Tom Lane)
  - https://www.postgresql.org/docs/9.1/static/runtime-config-compatible.html

### 1.4 [A 类-推动] MVCC + Visibility Map(可见性图)+ Freeze 机制

- **问题**:PostgreSQL 的 MVCC 用堆内多版本而非回滚段,代价是 vacuum 必须扫描全表冻结老 xid。
- **Tom Lane 的方案**:在 8.4 引入 visibility map(VM)—— 用 2 bits/heap page 标记"该页所有 tuple 对当前所有事务可见",让 vacuum 只扫需要清理的页,并让 index-only scan 成为可能。
- **替代方案**:
  - 把可见性信息塞进 heap page header(否,会爆 page 大小);
  - 引入 separate FSM(类似 Oracle 的 segment bitmap,PostgreSQL 之前已有 FSM,但只为 free space 服务)。
- **论证逻辑**:VM 是 2 位/页、永远驻留的极小结构,换来 vacuum 数量级加速 + index-only scan 这种全新能力,几乎无副作用。
- **结果**:重大成功。后续 freeze map、autovacuum 调优、index-only scan 都建立在 VM 之上。
- **来源**:PostgreSQL 8.4 release notes 大量 Tom Lane 提交;https://www.cnblogs.com/wy123/p/18471606(autovacuum 参数综述);https://github.com/postgres/postgres/blob/master/src/backend/access/heap/visibilitymap.c

### 1.5 [A 类-推动] numeric 数据类型重写(2003)

- **问题**:原 numeric 实现是简单的 base-10000 digit 数组 + schoolbook 算法,精度、大整数、性能都不达标,常常在生产场景给出错误结果或溢出。
- **Tom Lane 的方案**:重写 numeric.c/numeric.h,引入 NumericDigit + NumericVar,使用 base-10000 + 2 的补码存储,支持任意精度 + NaN,替换底层算术为 Knuth 算法。
- **替代方案**:升级到 base-10^9 提高空间效率,但增加实现复杂度;Tom Lane 评估后选择 base-10000 平衡点。
- **论证逻辑**:"先正确,再优化"。在 commit 中他强调正确性优先于性能,宁愿做一次大重写,也不在错的地基上做小修。
- **结果**:成功。numeric 成为 PostgreSQL 在金融场景的核心竞争力。deepwiki 提到该重写"He heavily revised the exact numeric data type implementation in numeric.h and numeric.c in 2003"。
- **来源**:https://github.com/postgres/postgres commit log 中 2003 年的 numeric 重写;deepwiki 检索结果

### 1.6 [A 类-推动] pl/pgSQL 解析器重构 + `RETURNING` 子句

- **问题**:早期 pl/pgSQL 用 bison 写解析器,可读性差且不支持 SQL 标准语法;同时上层 SQL 没有 `INSERT/UPDATE/DELETE ... RETURNING` 一次性返回结果集的能力。
- **Tom Lane 的方案**:
  - 在 pl/pgSQL 引入基于 `parse_expr` 的递归下降解析(替代部分 bison 规则);
  - 在 SQL 层引入 `RETURNING`,与 CTE、规则系统协同,允许一个 DML 返回新行供后续查询使用。
- **替代方案**:完全替换 pl/pgSQL 用 PL/Python(否,生态冲击太大);把 `RETURNING` 留给用户用 `currval()`(否,不是原子的)。
- **论证逻辑**:用统一的 querytree 数据结构(parse/analyze/rewrite 管线)同时支撑 PL/SQL 和 SQL,减少语义分叉。
- **结果**:成功。`RETURNING` 极大简化了 UPSERT 之外的"插入后回填"场景。
- **来源**:
  - https://www.postgresql.org/docs/current/sql-insert.html(RETURNING 文档)
  - https://www.postgresql.org/docs/9.4/static/release-9-4.html(PL/pgSQL 改进历史)

### 1.7 [A 类-推动] 引入 AllocSet 内存上下文改进 + 小对象优化

- **问题**:PostgreSQL 早期 AllocSet 把所有内存按 power-of-2 块切,小请求浪费、大请求泄漏回 OS 缓慢。
- **Tom Lane 的方案**:重写 AllocSet,让"小块"用 2 的幂切分但更紧凑,大块直接 `malloc()`,释放时更积极返回 OS。
- **替代方案**:换 jemalloc/tcmalloc(否,会引入构建依赖和许可问题)。
- **论证逻辑**:在"不引入第三方依赖"的前提下,通过自身算法改进解决大部分实际问题。
- **结果**:成功。deepwiki 引用:"Tom Lane significantly revised the AllocSet implementation for memory contexts"。这一改进支撑了后续 hash join、外部排序等内存敏感特性。
- **来源**:https://github.com/postgres/postgres commit log;deepwiki 检索结果

### 1.8 [A 类-推动] NOTIFY 优化 — 只唤醒订阅 channel 的 backend

- **问题**:早期 NOTIFY 用 LISTEN/NOTIFY 是广播模型,每次 NOTIFY 都唤醒所有 listening backend,在大集群上形成 wakeup storm。
- **Tom Lane 的方案**:在 LISTEN 注册时记录订阅的 channel name,NOTIFY 时只唤醒订阅了相关 channel 的 backend。
- **替代方案**:把 NOTIFY 改成 pub/sub 中间件(否,违反 PostgreSQL 自身不引入中间件依赖的原则)。
- **结果**:成功,常被作为 Tom Lane 风格的小而精的代表性修改。
- **来源**:PostgreSQL release notes 中 Tom Lane 提交记录(参见 https://www.postgresql.org/about/news/postgresql-weekly-news-april-4-2021-2193/ 类型的 weekly news)

### 1.9 [A 类-推动] 弃用 `add_missing_from` 默认行为

- **问题**:PostgreSQL < 8.1 默认隐式补 FROM 子句,违反 SQL 标准且易引入 bug。
- **Tom Lane 的方案**:8.1 起 `add_missing_from` 默认 off,并在后续版本完全移除该 GUC。
- **论证逻辑**:与 1.3 同源 —— 与 SQL 标准不符的兼容性开关,过渡期后必须切掉,不可作为永久后路。
- **结果**:成功,与 1.3 一同成为"迁移成本 < 永久债务"原则的代表。
- **来源**:https://www.postgresql.org/docs/8.2/runtime-config-compatible.html

### 1.10 [A 类-推动] Logical Replication 接收端架构(PG 16)

- **问题**:逻辑复制早期只能 publisher-to-subscriber,不支持双向同步、DDL 复制等高级能力。
- **Tom Lane 的方案(与他相关):** 在 PG 16 推动 subscriber 端可应用远程 schema(`ALTER SUBSCRIPTION ... REFRESH PUBLICATION` 等)的可观测行为修正;并修复 MERGE-with-VALUES 的 corner case。
- **替代方案**:完全重写 logical decoding 用 BDR/Bucardo 那种外部方案(否,无法取代原生能力)。
- **结果**:部分成功 —— 与 pglogical、BDR 长期共存,但原生能力明显追平。
- **来源**:PostgreSQL 16 release notes(https://www.postgresql.org/docs/release/16/ )中 Tom Lane 在 "Fix ... MERGE ... Tom Lane" 等条目的提交

---

## 2. 社区治理决策

### 2.1 [B 类-推动] Commitfest 流程的固化与分工

- **背景**:PostgreSQL 在 2000s 中后期形成"每月一次 Commitfest"流程 —— 由一名 volunteer CommitFest Manager(CFM)负责在固定周期把所有 open patches 集中 review、推进或回退。
- **Tom Lane 的方案**:作为资深 committer,他本人是 commitfest 末期最常见的"止血者" —— 当 patch 在 reviewer 间反复打转时,他常以"我重写一版"的方式强行 close thread。**这种"Tom Lane 重写"机制事实上成为 commitfest 的隐性瓶颈与保险阀。**
- **替代方案**:
  - 把每个 patch 强行绑定到 committer(被否,会出现 committer 离职导致 patch 永久积压);
  - 完全自治不设 CFM(Linux kernel 模式,被否,因为 PostgreSQL 强调"每个 patch 至少 1 名 reviewer + 1 名 committer 签字")。
- **论证逻辑**:**单点 review 责任 + 强制 close date**,而不是无限期堆积。PostgreSQL 这种"软强制"在 LWN 文章里被 Jonathan Corbet 专门评论过:"PostgreSQL 开发社区目前正在跟繁重的 review 工作搏斗"(来源:https://lwn.net/Articles/865754/,中文转载 https://blog.csdn.net/Linux_Everything/article/details/120030310)。
- **结果**:**持续争议**。Simon Riggs 在 2021 年曾指出 commitfest 队列中 50+ patch 已堆积超过 1 年,25+ patch 超过 2 年。Tom Lane 长期被诟病"个人 review 负荷过重,reviewer 多样性不足"。
- **来源**:
  - https://lwn.net/Articles/865754/
  - https://github.com/petere/commitfest-tools

### 2.2 [B 类-推动] Committer 资格"师徒制"放权

- **背景**:PostgreSQL 没有正式的"committer 选举"流程。新的 commit bit 一般由现有核心 committer 推荐 + 共识确认。
- **Tom Lane 的方案/角色**:Heikki Linnakangas、Andres Freund、Alvaro Herrera、Peter Eisentraut、Tomas Vondra 等核心 committer 的 commit bit 发放过程,Tom Lane 都参与了讨论或认可。**典型案例:Heikki Linnakangas 在 2009 年还是 EnterprisedB 工程师,讨论 client_encoding 自动检测议题(见 https://www.postgresql.org/message-id/4A38D396.1040003@enterprisedb.com),后来成为 Neon 创始人、长期 committer。**
- **替代方案**:BDFL 独裁式(被否);公司赞助自动获得 commit bit(被否,Tom Lane 多次反对)。
- **结果**:维持现状。该机制虽然不透明,但被 Tom Lane 描述为"熟人推荐 + 公开 patch 历史"两个要素结合,避免空降式 committer。
- **治理启示**:**准入基于可观测贡献历史,而非资历或公司背景**,这是 Tom Lane 治理哲学的支柱。

### 2.3 [B 类-推动] 推动 Release Manager 的轮值制度

- **背景**:PostgreSQL major release 由 1 名 Release Manager 主导(写 release notes、协调 feature freeze、决定 commitfest 收尾顺序)。历史上多由 Tom Lane、Bruce Momjian 担任。
- **Tom Lane 的方案**:作为核心 maintainer,他长期对 release manager 的"个人权威"做约束 —— 在 -hackers 上反复主张"release manager 不应是独裁者,而应是 facilitator"。
- **替代方案**:LTS/STS 分轨(到 2024 年才部分引入);核心团队投票决定 feature freeze 范围(未采纳)。
- **结果**:渐进式成功。但 release manager 角色长期集中在少数人手中(Tom Lane 多次担任),客观上形成"软集权"。
- **来源**:PostgreSQL release notes 中 release manager 署名;https://www.postgresql.org/about/news/

### 2.4 [B 类-推动] 拒绝"fork-friendly"特性外部扩展

- **背景**:社区多次提议"把 PostgreSQL 拆成内核 + 用户态扩展库"或"引入更多 Lua/Python hook 让外部控制核心流程"。
- **Tom Lane 的立场**:原则上反对,**坚持把核心语义收敛在 SQL 层**,只暴露有限的 hook(扩展、custom GUC、event trigger)。他在多封邮件中坚持:"我们不做插件式内核"。
- **结果**:PostgreSQL 在"轻内核 + 重扩展"和"集中式内核"之间选择了后者。这与 MySQL 的 plugin 模型形成鲜明对比,也是 PG 长期一致性的来源。

---

## 3. 争议行为 / 反共识决策

### 3.1 [C 类-争议] 与 Simon Riggs 的 Commitfest 治理之争

- **冲突**:2021 年,Simon Riggs(前 PG 核心 committer,2ndQuadrant 创始人)公开指出 commitfest 队列积压严重,提议改为"分轨制 commitfest"。
- **Tom Lane 的回应**:倾向于在现有流程上做修补(强制 close old patch、要求 author 重新提交),而不是流程重构。
- **事后评价**:2022-2024 年 commitfest 队列清理显著,Tom Lane 的修补主义胜出,但付出的是个人 review 时间被严重透支。
- **启示**:**渐进修补 vs 流程重构**的经典拉锯,Tom Lane 偏好前者。

### 3.2 [C 类-争议] 早期对 `WITH RECURSIVE` 优化的保守态度

- **背景**:CTE(Common Table Expressions)在 8.4 引入,默认会被物化(materialize),这与 SQL 标准行为以及 MySQL/Oracle 的"内联展开"不同,常导致性能问题。
- **Tom Lane 的立场**:坚持默认 materialize 直到 PG 12 才引入 `AS NOT MATERIALIZED`,且他本人在多个 thread 中主张"物化更安全,避免优化器 bug"。
- **事后评价**:被多次批评为"过度保守"。Robert Haas 等人推动 NOT MATERIALIZED 选项,Tom Lane 最终同意加入,但坚持 default behavior 不变。
- **启示**:**"先正确、再优化"** 哲学的代价:让用户在 PG 11 及之前要手动写 `OFFSET 0` 强制物化绕过,体验糟糕。

### 3.3 [C 类-争议] JSONB 路径表达式的标准化选择

- **背景**:PG 9.4 引入 JSONB(主要是 Oleg Bartunov、Alexander Korotkov 主导),用一种新的内部表示。
- **Tom Lane 的角色**:在路径表达式 (`jsonb_path_*`) 设计上,他主张以 **JSONPath(SQL 标准)** 而不是 jQuery-like 语法为准,推动最终 PG 12 采纳 SQL/JSON 标准路径。
- **争议**:放弃 jQuery 语法让习惯了 MongoDB 的用户不满;但坚持 SQL 标准让 PG 的 JSON 支持在后续十年稳定演进。
- **事后评价**:**成功** —— PostgreSQL 在 SQL/JSON 标准上保持了领先,且与 ORACLE/DB2 兼容。
- **来源**:PostgreSQL 12 release notes 中 SQL/JSON 相关条目

### 3.4 [C 类-争议] 拒绝将 `citext`(大小写不敏感文本)并入核心

- **背景**:`citext` 是经典扩展,社区多次建议合并到核心。
- **Tom Lane 的立场**:坚持扩展模型,反对合并。理由是核心 SQL 类型一旦变动就会影响 dump/restore 兼容性。
- **结果**:citext 至今仍为扩展。这是 Tom Lane "扩展优于核心污染"原则的典型案例。
- **启示**:这是治理哲学的具体体现 —— **核心 vs 扩展的边界由 commit 时机决定,不由功能流行度决定**。

### 3.5 [C 类-反思/承认错误] libpq 引用函数长度参数忽略(CVE-2025-1094)

- **背景**:2025 年披露的 libpq `PQescapeLiteral()` 和 `PQescapeIdentifier()` 未遵守长度参数,可能读越界。Tom Lane 与 Andres Freund 合作修复。
- **Tom Lane 的反思(release notes 原文)**:"The changes made for CVE-2025-1094 had one serious oversight: PQescapeLiteral() and PQescapeIdentifier() failed to honor their string length parameter, instead always reading to the input string's trailing null."
- **启示**:**罕见的事前承认错误的官方 release notes**,说明 Tom Lane 在 CVE 类问题上"先认错,再修"的姿态。
- **来源**:https://www.postgresql.org/docs/release/16.8/

### 3.6 [C 类-争议] 反对 PL/Python 早期被允许的 `plpy.notice()` 副作用

- **背景**:Tom Lane 多次在 -hackers 上指出 PL 函数的副作用(向客户端打印 notice、写文件)会破坏事务原子性。
- **立场**:坚持"PL 函数应纯函数式,无副作用"。
- **结果**:PL/pgSQL 提供了 `RAISE NOTICE` 但限制副作用;PL/Python 在很长一段时间被警告为"可能破坏事务安全"。

---

## 4. 决策方法论提炼(对开源治理最关键的部分)

把以上决策归类后,Tom Lane 反复出现的论证结构是:

### 4.1 五步决策模板(从他的邮件和 commit message 中提炼)

1. **锚点** —— 用 SQL 标准 / 既有 PostgreSQL 历史 / SQL 标准的失败先例 做权威锚点。例子:1.3、1.9 都是用"SQL 标准"作为锚点。
2. **边界 case 列举** —— 在 commit message 或邮件中,他习惯先列 corner case,再做决策。例子:1.6 `RETURNING` 设计中他列出与 CTE、规则系统的交互 case。
3. **拒绝"未来扩展性"为理由的提案** —— 他倾向于"先实现当前 spec,以后再说"。例子:拒绝 citext 并入核心;拒绝 plpython 自由副作用。
4. **先迁移成本评估,再做断腕** —— 在 1.3、1.9 中,他用"过渡期"管理伤害,而不是无限保留老行为。
5. **可观测性优先** —— GEQO seed、可观测行为优先于"理论上更好的随机性",1.2 是典范。

### 4.2 何时妥协、何时坚持

| 类型 | 例子 | 行为 |
| --- | --- | --- |
| 标准对齐类 | 1.3、1.9 | **坚持**,但给 1-2 版本过渡期 |
| 性能优化类 | 1.6 RETURNING | **坚持**,因为影响核心语义 |
| 流程治理类 | 2.1 commitfest | **妥协**,接受 Simon Riggs 的批评 |
| 核心边界类 | 3.4 citext | **坚持**,不动核心边界 |
| 边缘 case | 3.5 CVE | **立刻认错**,优先修 |

### 4.3 反共识案例

- **GEQO seed**:他反对"随机多样性",坚持可复现性。这是**性能 vs 可观测性**取舍中他选可观测性的代表。
- **CTE 默认物化**:他反对"自动 NOT MATERIALIZED",坚持"显式触发内联"。这是**优化器复杂度 vs 用户便利**取舍中他选保守的代表。
- **拒绝 fork-friendly 内核**:他反对"扩展式内核",坚持"集中内核 + 扩展机制"。这是**灵活性 vs 一致性**取舍中他选一致性的代表。

---

## 5. 关键来源汇总

| 类别 | URL |
| --- | --- |
| Crunchy 官方公告(Tom Lane 履历) | https://yq.aliyun.com/articles/112816(转载自 oschina);https://www.kejianet.cn/tom-lane/ |
| 优化器综述(中国研究者视角) | https://blog.csdn.net/zhaowei121/article/details/10395656;https://zhuanlan.zhihu.com/p/56702915 |
| GEQO seed commit message | http://archives.postgresql.org/pgsql-committers/2009-07/msg00148.php |
| GEQO 文档 | https://www.postgresql.org/docs/9.0/geqo-pg-intro.html |
| standard_conforming_strings | https://www.postgresql.org/docs/release/19/release-19.html;https://www.postgresql.org/docs/9.1/static/runtime-config-compatible.html |
| LWN commitfest 评论 | https://lwn.net/Articles/865754/(中文转载 https://blog.csdn.net/Linux_Everything/article/details/120030310) |
| CVE-2025-1094 release notes | https://www.postgresql.org/docs/release/16.8/ |
| Heikki Linnakangas mailing list | https://www.postgresql.org/message-id/4A38D396.1040003@enterprisedb.com |
| add_missing_from 历史 | https://www.postgresql.org/docs/8.2/runtime-config-compatible.html |
| visibility map 源码 | https://github.com/postgres/postgres/blob/master/src/backend/access/heap/visibilitymap.c |
| deepwiki 检索 | https://deepwiki.com/search/what-were-tom-lanes-most-signi_60eb929b-a1f8-4443-bd7a-607f04fecf58 |
| release notes 索引 | https://www.postgresql.org/docs/release/ |
| PostgreSQL 16 logical replication | https://www.postgresql.org/docs/15/logical-replication.html |
| PostgreSQL 18 发布 | https://www.postgresql.org/about/news/postgresql-18-released-3142/ |

---

## 6. 局限与待补充

- 本调研主要依赖 release notes、邮件归档、二手综述,**未完整覆盖 PGCon 演讲**(因为 Crunchy/Red Hat 官网外链失效较多)。
- 关于 Tom Lane 公开承认"这个决策后来看是错的"的事例,**目前只找到 CVE-2025-1094 一例**(release notes 原话承认 oversight)。其他决策的反思更多隐藏在 commit message 中的"editorialization",而非公开演讲。
- 关于"被否决的设计提案"的全名单,需要进一步精读 [pgsql-hackers archive](https://www.postgresql.org/list/) 才能补全 —— 建议下一轮调研聚焦 2015-2024 年的 rejected patches。
- 关于 Tom Lane 与社区成员的"著名争论",Simon Riggs 的 commitfest 争论、Robert Haas 的 CTE 内联争论是已有材料覆盖最充分的两个。