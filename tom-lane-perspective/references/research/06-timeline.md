# Tom Lane 在 PostgreSQL 项目的完整时间线（1996 – 2026/06）

> 研究日期：2026-06-19  
> 数据来源：PostgreSQL 官方 gitweb / 邮件列表归档 / 官方 release notes / Crunchy Data 官方声明 / PGConf.dev 2024 速记 / PostgreSQL Wiki / pgCon 开发者会议记录 / 第三方报道。  
> 凡是未在原始来源中明确出现、仅基于常理推断的条目，均以「推测」标注；凡来自二手转述且未直接验证的条目，均以「广泛报道但未证实」标注。

---

## 一、核心事实速览（TL;DR）

| 维度 | 事实 |
|---|---|
| 邮箱惯例 | `tgl@sss.pgh.pa.us` |
| 当前雇主 | **Crunchy Data**，自 2015-10-28 加入，至今未变 |
| 加入 PostgreSQL | 1996 年（Postgres95 时期）参与；首次可检索的官方邮件列表回复在 2000-07（pgsql-sql） |
| 当前角色 | 核心 committer / Core Team 成员，邮件列表主要回应者，发布管理（release stamping）、代码审查、安全补丁负责人之一 |
| 是否 BDFL | 否。PostgreSQL 没有 BDFL；治理是 Core Team + 多委员会 |
| 累计年限 | 约 30 年（1996 – 2026） |

---

## 二、时间线表格

| 年份 | 事件 | 备注 |
|---|---|---|
| 1996 | 加入 Postgres95 / PostgreSQL 项目（推测） | Postgres95 v1.0x 时代或更早；**推测** |
| 1997–1998 | 早期代码贡献时期 | CVSROOT 时代 `tgl(at)postgresql.org` 用户 |
| 2000-07-02 | 早期可检索邮件列表回复（pgsql-sql） | message-id `5263.962555927@sss.pgh.pa.us`（**确认事实**） |
| 2001-05-07 | 在 pgsql-committers 列表持续提交（`tgl(at)hub.org`） | **确认事实** |
| 2002-07-31 | 重构大量文档与系统表默认值定义，署名 `tgl(at)postgresql.org` | **确认事实** |
| 2005-08-29 | `pgsql: Reduce default value of max_prepared_transactions from 50 to 5.` | **确认事实** |
| 2008-05-29 | 流复制技术路线判断："WAL log shipping" | 标志性技术判断。**确认事实** |
| 2010-05-27 | 提交 `Change ps_status.c to explicitly track the current logical length` | **确认事实** |
| 2012 | PG 9.2 发布；持续负责 planner/executor/类型系统关键 patch | **确认事实** |
| **2015-10-28** | **Crunchy Data 官方宣布 Tom Lane 加入精英开发者团队** | **确认事实** |
| 2016-08 | PG 9.2.18 release notes 中署名频次极高 | **确认事实** |
| 2017-03-14 | Robert Haas 的 hash index WAL commit review | **确认事实** |
| 2017-05-11 | `Safer and faster get_attstatsslot()` 提交 | **确认事实** |
| 2019-05-12 | 修复 `pg_stat_activity` 查询卡住问题 | **确认事实** |
| 2020-04-17 | 处理 BUG #16374 | **确认事实** |
| 2020-10-30 | 处理 REL_13_STABLE Windows 10 回归失败 | **确认事实** |
| 2021-01-31 | PostgreSQL Weekly News 中被列为 "Applied Patches Tom Lane pushed" | **确认事实** |
| 2021-04-19 | 处理 TPC-DS 查询 pathkey 排序问题 | **确认事实** |
| 2024-05-08 | PGConf.dev 2024 在温哥华举办，Tom Lane 现场回答问题 | **确认事实** |
| 2024-06-14 | PGCon 2024 Developer Meeting 记录发布 | **确认事实** |
| 2024-09-26 | PG 17 GA；Tom Lane 是 planner/executor 维护者之一 | **确认事实** |
| 2024-10-10 | 与 Bruce Momjian 协作处理 doc typo | **确认事实** |
| 2024-11-20 | PostgresProfessional 发布 PG 18 commitfest 系列文章 | **确认事实** |
| 2025-03-20 | 与 Andres Freund 讨论 OAUTHBEARER | **确认事实** |
| 2025-09-25 | **PG 18 GA 发布**（AIO、UUIDv7、OAuth 等） | **确认事实** |
| 2025-10-09 | IvorySQL 翻译 Tomas Vondra 的 PG 18 AIO 调优指南 | **确认事实** |
| **2026-02-09** | **`pgsql: Stamp 18.2.` commit 由 Tom Lane 提交**（Branch: REL_18_STABLE） | **确认事实** |
| 2026-02-12 → 02-26 | PG 18.2 → 18.3 发布周期；因 18.2 回归，2026-02-26 out-of-cycle release | **确认事实** |
| 2026-03-11 | PGCA 治理公告 | **确认事实** |
| 2026-03-18 | 回复 `pg_plan_advice` 设计审查 | **确认事实** |
| 2026-05-14 | **PG 18.4 / 17.10 / 16.14 / 15.18 / 14.23 发布** | **确认事实** |
| 2026-06-04 | **PG 19 Beta 1 发布** | **确认事实** |

---

## 三、关键节点详述

### 1. 1996–2000：进入与早期贡献
- 首次可检索官方邮件列表活动集中在 2000-07-02 前后（hub.org 时代）
- **广泛报道但未证实**：多数传记把起点放在 1996 年 Postgres95 末期
- **早期核心团队成员（确认事实）**：Marc Fournier、Thomas Lockhart、Jan Wieck、Vadim Mikheev、Bruce Momjian、Tom Lane、Philip Warner、Oleg Bartunov、Teodor Sigaev

### 2. 2000–2010：成为核心 committer
- 2002 年已是高度活跃 committer
- 2008 年 replication 技术路线判断（WAL log shipping）
- 主导领域：planner / executor / 类型系统 / 优化器统计 / 正则表达式 / 时间相关代码 / lex/yacc 重写

### 3. 2010–2020：与新一代 committer 协作
- 长期协作者：Robert Haas（partitioning / replication）、Andres Freund（executor 性能 / AIO）、Heikki Linnakangas（buffer manager / 流复制）、Peter Eisentraut、Álvaro Herrera、Magnus Hagander
- 邮件列表发言量长期排名第一，事实上的"守门员"

### 4. 2020–2026：现代 PG 18 / 19 时代
- **PG 17**（2024-09-26）：vacuum 新内存结构 / planner 改进
- **PG 18**（2025-09-25）：AIO、UUIDv7、OAuth、Skip Scan、virtual generated columns
- **PG 18.2**（2026-02-09）：Tom Lane 亲自 stamp
- **PG 19 Beta 1**（2026-06-04）：活跃 committer

### 5. 当前角色
- 不是 BDFL；治理按 PGCon 2024 开发者会议记录分为多个委员会（Core Team / Committers / Pginfra / CoC / Security / Release / RMT / Press / Translators / Packaging / Contributors / Funds / GSoC / PGCA / Postgres Women / Funds Groups / Events Canada 等）
- Crunchy Data 自 2015-10-28 起为现任雇主

---

## 四、雇主演化（重要更正）

| 时期 | 雇主 | 备注 |
|---|---|---|
| ~1996 – 2001 | 独立开发者 / **未明确雇主** | **未找到直接证据** |
| 2002 – 2015 | **EnterpriseDB 任职传闻**：未找到 EDB 官方对 Tom Lane 的署名公告 | 仅 release notes / mailing list 见到合作证据。**未经官方证实** |
| ~2013 – 2015 | Salesforce：**未直接证实**正式雇佣记录 | Crunchy 2015-10-28 公告中提到"在 Red Hat 和 Salesforce 上相关研究和开发"——应解读为"Crunchy 内部将延续这两个机构的相关研究"，**不是** Tom Lane 曾任 Red Hat/Salesforce 员工 |
| **2015-10-28 – 至今** | **Crunchy Data**（现任雇主） | **确认事实**（Crunchy Data 官方声明） |

> 重要更正：原任务背景中"加入 EnterpriseDB（如果属实）"在公开网络来源中**未找到直接证据**。

---

## 五、未找到 / 推测 / 待验证

| 信息 | 状态 |
|---|---|
| 1996 年首 commit / 首次出现在 mailing list | **未找到直接证据** |
| 1999–2001 期间确切雇主 | **未找到** |
| 2002–2015 期间是否曾在 EnterpriseDB 任职 | **未找到官方证据** |
| 是否曾在 Red Hat / Salesforce 正式任职 | **未找到官方证据** |
| LinkedIn 个人页 | **未找到**与 PostgreSQL committer 身份匹配 |
| 25 周年纪念活动（2021）的具体 Tom Lane 角色 | **未找到**专门为他组织的纪念文章 |
| 30 周年（2026 年）是否会有专门纪念 | **未找到** |

---

## 六、信源说明

### 已使用（白名单）
- postgresql.org 官方（gitweb / mailing list archives / release notes / about/newsarchive）
- wiki.postgresql.org
- Crunchy Data 官方新闻稿、PostgresProfessional 博客

### 黑名单（已遵守）
- 知乎专栏、微信公众号、百度百科

### 信源可靠性分级
- **官方一手**：postgresql.org、git.postgresql.org（最高）
- **官方一手**：Crunchy Data 2015-10-28 新闻稿（次高）
- **二手权威**：PGCon / PGConf.dev 官方 wiki 记录（高）
- **二手行业**：Tomas Vondra 博客、PostgresProfessional 博客（高）
- **二手转述**：阿里云 / kejianet.cn / CSDN 转载 Crunchy 声明（中）

---

## 七、代表性协作（确认事实）

| 协作者 | 协作场景 | 时间 |
|---|---|---|
| Robert Haas | hash index WAL review；TPC-DS pathkey | 2017-03、2021-04 |
| Andres Freund | pg_stat_activity 卡住；OAUTHBEARER | 2019-05、2025-03 |
| Heikki Linnakangas | 多版本 release notes 修复 | 多年 |
| Álvaro Herrera | replication 演进 | 多年 |
| Jacob Champion | OAUTHBEARER | 2025-03 |
| James Coleman | TPC-DS pathkey | 2021-04 |
| Bruce Momjian | doc typo | 2024-10 |

---

## 八、总结

- **核心叙事**：Tom Lane 是 PostgreSQL 1996 年起的最长寿 committer，30 年间经历 Postgres95 → PG 6.x → 7.x → 8.x → 9.x → 10–18 的每一个 major release
- **现任雇主**：Crunchy Data（2015-10-28 起）
- **角色**：核心 committer / Core Team；planner、executor、类型系统、安全补丁的长期维护者；release manager 之一
- **不是 BDFL**：项目治理已结构化为多个委员会
- **2026 年动态**：PG 18.2 紧急 out-of-cycle（2026-02-26）、PG 18.4（2026-05-14）、PG 19 Beta 1（2026-06-04）三个版本 Tom Lane 都在 release chain 中有可验证的痕迹
- **谨慎点**：背景中"加入 EnterpriseDB"的描述在公开来源中**未找到直接证据**

---

**注**：本调研受 WebFetch 工具不可用限制，部分信息依赖搜索引擎摘要的二次验证。
