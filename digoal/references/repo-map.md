# digoal/blog Knowledge Map

Use this map to locate evidence in a local `digoal/blog` repository. The blog is read-only source material for `digoal`.

## Repository Shape

- Root: a local checkout containing `README.md`, `CLAUDE.md`, and `class/`
- Main index: `README.md`
- Agent/coding guidance: `CLAUDE.md`
- Author profile: `me/readme.md`
- Posts: `YYYYMM/YYYYMMDD_NN.md`, newest first in `README.md`
- Categories: `class/1.md` through `class/36.md`
- Assets: `pic/`, `pdf/`
- Index generation: `generate_readme.sh` scans dated directories and rebuilds monthly/root indexes.

## Portable Location Rules

This skill may run from two layouts:

- Embedded layout: `blog/skills/digoal`. Auto-discovery finds the blog root by walking upward.
- Copied-agent layout: `/path/to/agent/skills/digoal`. Auto-discovery may fail because the blog is elsewhere; set `DIGOAL_BLOG_ROOT=/path/to/blog` or pass `--blog /path/to/blog` to helper scripts.

If no blog root is available, use only bundled references for high-level orientation and explicitly ask for the user's local blog checkout path before answering with specific blog evidence.

DeepWiki overview: the repository is a large technical knowledge base with 4000-5000+ Markdown posts, organized chronologically and by category, focused on PostgreSQL, PolarDB, Greenplum, DuckDB, AI/database integration, vector search, RAG, operations, benchmarking, and community/ecosystem thinking.

## Author Signals

`me/readme.md` positions digoal as:

- PostgreSQL China community initiator and long-term evangelist.
- Former Alibaba Cloud database expert working across RDS PG, PPAS, PolarDB for PG/Oracle, product planning, ecosystem building, customer architecture, POC support, DBA/developer enablement, standards, best practices, and community growth.
- Former SkyMobi database/storage/OS/IDC architect, with hands-on experience in HA, DR, backup, multi-IDC, monitoring, audit, inspection, SLA, standardization, Oracle-to-PG migration, GP, MongoDB, large-scale concurrent systems, and data warehouses.
- Holder of 40+ database patents and operator of blog/video/public-account channels.

Use this background to preserve practical, field-tested judgment. Do not invent private details beyond the blog.

## Category Index

The README category table maps core database work:

- `class/1.md`: 应用开发
- `class/2.md`: 日常维护
- `class/3.md`: 监控
- `class/4.md`: 备份,恢复,容灾
- `class/5.md`: 高可用
- `class/6.md`: 安全与审计
- `class/7.md`: 问题诊断与性能优化
- `class/8.md`: 流式复制
- `class/9.md`: 读写分离
- `class/10.md`: 水平分库
- `class/11.md`: OLAP/MPP
- `class/12.md`: 数据库扩展插件
- `class/13.md`: 版本新特性
- `class/14.md`: 内核原理与开发
- `class/15.md`: 经典案例
- `class/16.md`: HTAP
- `class/17.md`: 流式计算
- `class/18.md`: 时序、时空、对象多维处理
- `class/19.md`: 图式搜索
- `class/20.md`: GIS
- `class/21.md`: Oracle兼容性
- `class/22.md`: 数据库选型
- `class/23.md`: Benchmark
- `class/24.md`: 最佳实践
- `class/25.md`: DaaS
- `class/26.md`: 垂直行业应用
- `class/27.md`: 标准化、规约、制度、流程
- `class/28.md`: 版本升级
- `class/29.md`: 同/异构数据同步
- `class/30.md`: 数据分析
- `class/31.md`: 系列课程
- `class/32.md`: 其他
- `class/33.md`: 招聘与求职信息
- `class/34.md`: 沙龙、会议、培训
- `class/35.md`: 思维精进
- `class/36.md`: 视频回放

## Major Series From README

Prioritize these when a user asks for learning paths, course design, or authoritative summaries:

- `202105/20210526_02.md`: 重新发现PG之美
- `202108/20210823_05.md`: DB吐槽大会
- `202009/20200903_02.md`: PostgreSQL 应用场景最佳实践
- `202001/20200118_02.md`: PostgreSQL+MySQL 联合解决方案
- `201901/20190105_01.md`: PostgreSQL 体系化培训
- `201906/20190615_03.md`: Oracle迁移到PostgreSQL
- `202109/20210928_01.md`: Ask 德哥
- `202112/20211209_02.md`: 每天5分钟, PG聊通透
- `202308/20230822_02.md`: PostgreSQL|PolarDB 学习实验手册
- `202310/20231030_02.md`: 开源PolarDB|PostgreSQL 公开课
- `202409/20240914_01.md`: 数据库筑基课
- `202502/20250218_03.md`: AI辅助学PolarDB/PostgreSQL数据库内核源码
- `202510/20251016_11.md`: OceanBase 源码入门学习
- `202510/20251021_13.md`: LangChain 源码入门学习
- `202510/20251024_17.md`: DuckDB 源码入门学习
- `202510/20251029_08.md`: Milvus 源码入门学习
- `202511/20251103_17.md`: VectorChord 源码入门学习
- `202511/20251105_17.md`: pgvector 源码入门学习
- `202511/20251108_14.md`: DuckPGQ 源码入门学习
- `202511/20251112_20.md`: pgvectorscale/StreamingDiskANN 源码入门学习
- `202511/20251121_18.md`: pg_tokenizer 源码入门学习
- `202511/20251126_18.md`: VectorChord-bm25 源码入门学习
- `202512/20251202_10.md`: 大模型及Dify体验+AI搜索实践

## Frequently Useful Learning Materials

- `201804/20180425_01.md`: Oracle DBA 转型 PostgreSQL 学习方法
- `201706/20170601_02.md`: PostgreSQL/Greenplum 108个场景最佳实践
- `201506/20150601_01.md`: PostgreSQL 数据库安全指南
- `201902/20190219_02.md`: PostgreSQL 持续稳定使用小技巧、规约、规范
- `202005/20200509_02.md`: PostgreSQL DBA最常用SQL
- `201609/20160926_01.md`: PostgreSQL 数据库开发规范
- `197001/20190214_01.md`: 企业数据库选型规则
- `201709/20170921_01.md`: PostgreSQL 规格评估
- `201702/20170209_01.md`: 数据库选型之大象十八摸
- `201704/20170411_01.md` through `201704/20170412_04.md`: 快速入门PostgreSQL应用开发与管理

## AI, Agents, and Skill Distillation

Use these posts when asked to design digital employees, skills, or AI work systems:

- `202603/20260324_06.md`: 如何用 Codex 写 SKILL
- `202603/20260317_03.md`: 未来交易的不是知识，而是可交付的能力
- `202603/20260319_05.md`: 如何让AI进入稳定的、可验收、可进化的工作输出状态
- `202604/20260408_10.md`: 我如何用 AI 写 PG 代码解读和公众号爆款
- `202603/20260327_04.md`: prompt 到 context 到 harness engineering
- `202603/20260330_07.md`: MiniMax 接入 Claude/TradingAgents

Core idea: valuable AI work is not a static knowledge base; it is a repeatable ability unit with input contract, decision path, tool calls, validation loop, fallback, output template, and responsibility boundary.

## Search Hints

Use exact Chinese and English keywords. Examples:

- Performance: `性能优化`, `TOP SQL`, `EXPLAIN`, `vacuum`, `work_mem`, `索引`, `锁`, `OOM`
- HA/DR: `高可用`, `流式复制`, `备份`, `恢复`, `PITR`, `容灾`, `RPO`, `RTO`
- Migration: `Oracle迁移`, `兼容性`, `orafce`, `pg_hint_plan`
- AI/vector: `RAG`, `向量`, `pgvector`, `HNSW`, `IVFFlat`, `VectorChord`, `BM25`, `混合搜索`
- Source code: `源码入门`, `PostgreSQL 19 preview`, `commit`, `内核`
- Community/strategy: `五看三定`, `社区建设`, `德说`, `开源`, `生态`
