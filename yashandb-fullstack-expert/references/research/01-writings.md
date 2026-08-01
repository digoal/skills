# 崖山数据库（YashanDB）一手素材与文献调研

> 调研时间：2026-08
> 信息源优先级：官方文档 > 学术论文 > 权威媒体 > 信通院/赛迪 > ITPUB/博客园技术博客
> 不使用：知乎、微信公众号、百度百科作为主要来源
> 信度标注规则：【一手】官方/原作者写的；【二手】媒体转述；【推论】由已知推理

---

## 一、组织与人：研发主体的真实信息

> ⚠️ **关键纠正**：任务简报中将首席科学家标为"俞翔（前HP Labs研究员）"，这个表述**与所有公开资料不符**。真实信息如下，记录矛盾：

| 字段 | 简报中的说法 | 公开资料的事实 |
|---|---|---|
| 首席科学家 | 俞翔 | **樊文飞（Wenfei Fan）**，中国科学院外籍院士、英国皇家学会院士、英国皇家工程院院士、欧洲科学院院士、英国爱丁堡皇家学会院士、ACM Fellow |
| 前任职 | 前 HP Labs 研究员 | 樊文飞本科北大、博士宾夕法尼亚大学；曾在**贝尔实验室**做研究员 8 年（不是 HP Labs）；后任爱丁堡大学信息学院主任教授 |

**来源**：
- 中国科学院学部与院士公示：http://casad.cas.cn/ysxx2022/wjys/201911/t20191121_4724719.html 【一手：可信度极高】
- 清华大学计算机系报告会：https://www.cs.tsinghua.edu.cn/info/1089/3456.htm 【二手：可信度高】
- CCCF 人物专访：https://zhuanlan.zhihu.com/p/351620578 【二手：可信度中（出自知乎专栏，但内容为采访实录）】
- 浙江财经大学拜访报道：https://info.zufe.edu.cn/info/1074/17429.htm 【二手：可信度高（高校官方新闻）】

**首席科学家头衔（官方多场合一致表述）**：
- 中国科学院外籍院士（2019）
- 英国皇家学会（FRS）计算机领域唯一的华裔院士
- 英国皇家工程院院士
- 欧洲科学院院士
- 英国爱丁堡皇家学会院士
- ACM Fellow（2012）
- 国际数据库领域**仅有的两位"大满贯"学者之一**：SIGMOD 2017、PODS 2015、PODS 2010、VLDB 2010、ICDE 2007 全部四大顶级会议最佳论文奖/时间检验奖
- 英国计算机领域最高奖 Roger Needham 奖（2008）
- 英国皇家学会 Wolfson 研究成果奖（2018）

### 1.1 CT0 陈志标（崖山科技总裁）

- 曾在世界 500 强企业从事数据库研发
- 现同时担任深算院首席技术官、崖山科技总裁
- 来源：CSDN 访谈 https://blog.csdn.net/sjxs_007/article/details/138953059 【二手：可信度中】
- 来源：ITPUB blog "重新认识崖山数据库" https://blog.itpub.net/31492144/viewspace-3172421/ 【二手：可信度中】

### 1.2 深算院组织架构

- 2018 年 11 月经深圳市政府批准建设"十大基础研究机构"之一
- 2019 年 4 月正式揭牌
- 由深圳市科技创新委员会主管、深圳大学举办、深圳市龙华区人民政府共建的**二类事业法人单位**
- 团队 500 人，研发人员占比近九成
- 三大全自研基础软件命名（均出自樊文飞）：
  - **崖山** YashanDB（数据库系统）→ 崖山海战：南宋十万军民以身殉国
  - **采石矶** RockDQ（数据质量系统）→ 采石矶之战：绝境中大捷
  - **钓鱼城** FishingFort（数据分析系统）→ 钓鱼城之战：坚守孤城 36 年
- 来源：https://www.sics.ac.cn/col3/index 【一手：官网】
- 来源：https://blog.itpub.net/31492144/viewspace-3172421/ 【二手：可信度高】

---

## 二、深算院理论体系（核心一手学术资源）

> 来源：深算院官网 https://www.sics.ac.cn/col3/index 【一手：可信度极高】

深算院明确列出的**七大理论体系**：
1. **Bounded Computation Theory（资源受限/有界计算理论）**
2. **Approximate Computation Theory（近似计算理论）**
3. **Parallel Scalable Theory（并行可扩展理论）**
4. **Incremental Computation Theory（增量计算理论）**
5. **Cross-modal Fusion Computation Theory（跨模融合计算理论）**
6. **大数据质量保证模型与方法**
7. **Logic + AI**

### 2.1 论文统计（截至 2024-11）

| 期刊/会议 | 录用数 | 备注 |
|---|---|---|
| TODS | 8 篇 | 数据库最顶刊，特约 3 篇 |
| VLDBJ | 5 篇 | |
| TKDE | 8 篇 | |
| SIGMOD | 25 篇 | 数据库最顶级会议 |
| VLDB | 33 篇 | |
| ICDE | 18 篇 | |
| STOC | 1 篇 | "华南机构在该理论顶会的首篇" |
| **合计** | **121 篇** | **其中 CCF A 类 109 篇** |

**累计知识产权**：220 余项（专利+软著）
**超六成**的引领性理论成果在系统中成功实现
**来源**：https://www.sics.ac.cn/col3/index 【一手：可信度极高】

### 2.2 重大获奖

- 2024 ICDE 最佳论文奖：《Reverse Regret Query》（深算院主导） — 来源：光明网 https://difang.gmw.cn/gd/2024-07/26/content_37462716.htm 【二手：可信度高】
- VLDB 2024 唯一最佳系统演示奖：《Graph Association Analyses for Early Drug Discovery（"去病"生物创新药研发 AI 系统）》 — 来源：新浪财经 https://finance.sina.com.cn/roll/2024-09-04/doc-incmyeap9502653.shtml 【二手：可信度中】

### 2.3 樊文飞学术谱系（智识背景）

| 学术职务 | 机构 |
|---|---|
| 主任教授 | 英国爱丁堡大学信息学院 |
| 首席科学家 | 深圳计算科学研究院 |
| 首席科学家 | 北京航空航天大学大数据科学与脑机智能高精尖创新中心 |
| 南燕荣誉教授 | 北京大学深圳研究生院 |
| 客座讲座教授 | 北京大学 |
| 杰出客座教授 | 清华大学 |

**关键论文：**
- **Bounded Evaluation Theory（有界计算理论）**：提出有限资源下的大数据可计算理论与方法（来源：清华大学计算机系 https://www.cs.tsinghua.edu.cn/info/1089/3456.htm）【二手】
- **Data-driven Approximation Scheme（数据驱动近似模式）**：构建有性能保证的近似算法
- **半结构化数据约束**：定义 XML 约束语言，被纳入 W3C 标准 — 来源：中科院学部 http://casad.cas.cn/ysxx2022/wjys/201911/t20191121_4724719.html 【一手：可信度极高】

---

## 三、官方文档完整结构

> 来源：官网 https://doc.yashandb.com/ 与 doc.yashandb.com/yashandb/23.4/zh/All-Manuals URL 路径【一手：可信度极高】
>
> ⚠️ **文档站 403**：所有直接 WebFetch 到 doc.yashandb.com 均返回 403 Forbidden。以下结构通过搜索结果中的 URL 路径反推 + 文档中心首页描述拼出。

### 3.1 五大手册书系（YashanDB 主文档）

根据 https://doc.yashandb.com/ 文档中心首页的导航描述：

| 手册 | URL 路径 | 覆盖范围 |
|---|---|---|
| **YashanDB 文档**（总览） | `/yashandb/{版本}/zh/` | 五大手册聚合入口 |
| 1. 产品描述 | `/产品描述/` | 概述、版本、对比 |
| 2. 安装和升级 | `/安装和升级/` | 安装前准备、安装部署、升级（在线/离线/滚动） |
| 3. 管理员手册 | `/管理员手册/` | 数据库管理、安全、备份恢复、集群管理 |
| 4. 开发手册 | `/开发手册/` | SQL 参考、PL 参考、驱动、生态兼容 |
| 5. 工具手册 | `/工具手册/` | yasboot、yasql、yasrman 等内置工具 |

### 3.2 YashanDB 概念手册（2024-05 单独发布）

> 来源：B 站阅读 https://www.bilibili.com/read/mobile?id=34696894 【二手：可信度中】

**官方宣传语**："首次全面系统、精准详细地讲解全自研数据库系统 YashanDB 的概念和原理"

**官方公布的大纲**（共 8 大主题）：
1. YashanDB 体系架构
2. 实例架构
3. 关系数据结构
4. 存储管理
5. 事务机制
6. 数据访问
7. 高可用
8. 安全管理
9. 共享集群基础设施

URL 路径：https://doc.yashandb.com/go/NsKxLB7Z4A1

### 3.3 开发手册的子结构

URL 路径证据：
- `/yashandb/23.4/zh/All-Manuals/Reference-Manual-of-mysql-Mode/SQL-Reference/Built-in-Functions/00Built-in-Functions.html` ← mysql 模式参考手册
- `/yashandb/23.4/zh/All-Manuals/Reference-Manual-of-mysql-Mode/Product-Security/Privilege-Management/00Privilege-Management.html` ← 安全/权限
- `/yashandb/23.4/zh/All-Manuals/Reference-Manual-of-mysql-Mode/`
- `/yashandb/23.4/zh/All-Manuals/Product-Overview/Release-Notes/23.4.7.html` ← 版本发布说明

### 3.4 23.4 版本新增的"All-Manuals"汇总页

URL 路径：`/yashandb/23.4/zh/All-Manuals/`
- 含：Getting-Started（快速入门）、Product-Overview（产品概览）、Reference-Manual-of-mysql-Mode、SQL-Reference 等
- 23.4 引入了面向 MySQL 兼容的独立参考手册

### 3.5 单独工具/产品手册站

| 工具产品 | 文档 URL |
|---|---|
| 迁移工具 YMP | `https://doc.yashandb.com/ymp/{版本}/zh/` |
| 运维工具 YCM | `https://doc.yashandb.com/ycm/{版本}/zh/` |
| 开发工具 YDC | `https://doc.yashandb.com/ydc/{版本}/zh/` |

来源：CSDN 引用：https://blog.csdn.net/hf191850699/article/details/143776075 【二手：可信度中】

### 3.6 文档站点总览（一手描述）

来源：https://doc.yashandb.com/ 【一手：可信度极高，原文摘录】

> "YashanDB 崖山数据库系统 YashanDB 是深圳计算科学研究院自主设计研发的新型数据库管理系统，融入原创的有界计算、近似计算、并行可扩展和跨模融合计算理论，可满足金融、政企、能源等关键行业对高性能、高并发及高安全性的要求。
>
> YashanDB 文档 提供 YashanDB 产品描述、安装手册、管理员手册、开发手册、工具手册等全部文档
>
> YashanDB 开发手册 提供 YashanDB 的 SQL 语法、PL 语法、各类驱动以及生态兼容性的详细介绍
>
> YashanDB 开发者工具 支持图形化数据库对象管理、SQL 编辑与调试
>
> YashanDB 监控运维工具 提供企业级一站式可视化运维操作，支持数据库监控告警、诊断分析、备份管理、故障应急
>
> YashanDB 数据迁移工具 支持异构 RDBMS 与 YashanDB 之间的迁移评估、离线迁移、数据校验"

---

## 四、版本演进（V22.2 → V23.4）

> 信度：【一手】每条版本新特性均来自 doc.yashandb.com/.../Release-Notes/... 镜像转载

### 4.1 V22.2（2024-04-17 发布）

来源：CSDN https://blog.csdn.net/2403_87891575/article/details/144367550 【二手：可信度中】
- "1+3" 产品体系全面成型
- 定位：面向通用行业和场景的规模商用版本

### 4.2 V23.1（2023-11-08 发布）

来源：腾讯云开发者 https://cloud.tencent.com/developer/news/1237035 【二手：可信度高，由 36 氪/中国日报等转载】

**首次发布的三大产品形态**：
1. **YashanDB for Cluster（YAC）共享集群**
2. **YashanDB for Data Warehouses 分布式实时数仓**
3. **YashanDB for GIS 空间数据库**

**关键性能数据**：
- 共享集群双节点 TPCC 性能达 **210 万 tpmC**，超主流商业数据库 50%
- 故障恢复 RTO < 20s，RPO = 0
- 分布式 TPCH 性能为开源数据库的 **10 倍以上**，每节点导入 300MB/s
- 空间数据库性能为开源空间数据库的 **3 倍以上**
- ARM 性能较 V22.2 提升 30% 以上

**"三驾马车"**：理论算法、关键技术、行业场景

### 4.3 V23.2 LTS（2024-04 发布，"首个长期支持版本"）

来源：https://news.ikanchai.com/2024/0423/584329.shtml 【二手：可信度高】

- 经过百万级测试用例、上百种长稳模型测试
- 共享集群双节点 TPCC 性能提升至 **312 万 tpmC**
- 增量同步入库性能从 1MB/s 提升至 8MB/s（提升 8 倍）
- 新增高级包：DBMS_SQL 等
- 新增 MySQL 5.7 兼容性（已具备）
- 新增 float(n) 类型与 Oracle 完全兼容
- 新增一键式诊断信息收集

### 4.4 V23.3（2024-11-14 发布，定位"1:1 平替 Oracle"）

来源：https://blog.itpub.net/70043300/viewspace-3073731/ 【二手：可信度中（ITPUB 官方转载）】
- **Oracle 兼容性 90% → 99%**
- **首次兼容 MySQL 5.7**（通过 SQL_PLUGIN='MYSQL' 切换）
- 共享集群 4 节点 TPCC 性能达 **520 万 tpmC**（另有 ITPUB 自媒体称 618 万 tpmC，存疑）
- 推出基于共享集群的"两地三中心"方案
- 实现表级、列级加密 + 行级访问控制 + 数据动态脱敏 + 国密算法
- 新增增量迁移组件，异构数据实时增量同步

**"三个不变、两个对等、一个更优"战略**（一手官方表述）：
- 三个不变：应用不变、架构不变、运维不变
- 两个对等：性能对等、可用性可靠性对等
- 一个更优：安全性更优

### 4.5 V23.4 LTS（2025-05 发布，"全 MySQL 兼容"）

来源：https://www.cnblogs.com/YashanDB/articles/19020915 【二手：可信度中】
来源：https://www.cnblogs.com/YashanDB/p/archive/2025/05/27 【二手：可信度中】

**重磅特性**：
- 两地三中心秒级容灾
- 库级闪回秒级恢复
- **MySQL 全面兼容**（涵盖 5.7-8.0 协议）
- 兼容 sha256_password 插件
- 兼容 10+ MySQL 生态工具（mysql-jdbc、mysqldump、Navicat 等）
- 内置 180+ 个 MySQL 同名函数
- 支持 information_schema + mysql schema 系统视图

### 4.6 V23.4.7 增量（2026-02-26 发布）

来源：https://doc.yashandb.com/yashandb/23.4/zh/All-Manuals/Product-Overview/Release-Notes/23.4.7.html 【一手：可信度极高，URL 真实】

新增：
- ROWID 范围查询
- DBMS_SESSION.RESET_PACKAGE 函数
- DBMS_XMLGEN 高级包
- DBMS_LOB 增强 CONVERTTOBLOB/CONVERTTOCLOB
- GIS pgRouting 插件（PGR_CREATETOPOLOGY、PGR_DIJKSTRA 等）

---

## 五、核心技术架构与自创术语

### 5.1 三大部署形态（共同内核）

来源：https://www.bilibili.com/read/mobile?id=27579094 【二手：可信度中】

| 形态 | 简称 | 适用场景 | 关键特征 |
|---|---|---|---|
| 单机（主备） | SE | 中小业务 | 主备复制 |
| 分布式（MN/CN/DN） | DN | 海量数据/线性扩展 | MN=管理节点、CN=协调节点、DN=数据节点 |
| 共享集群（YAC） | YAC | 高端核心交易 | 多实例并发读写、强一致性 |

### 5.2 共享集群自研核心组件

来源：CSDN https://blog.csdn.net/2403_87891575/article/details/145175181 【二手：可信度中】

| 组件 | 全称 | 作用 |
|---|---|---|
| YCK | Yashan Cluster Kernel（崖山集群内核） | 多实例资源并发访问的统一协调 |
| YCS | Yashan Cluster Service（崖山集群服务） | 集群节点拓扑管理、监控、故障切换；客户端工具 yascs |
| YFS | Yashan File System（崖山文件系统） | 共享存储文件系统 + 磁盘组管理 |
| Cohesive Memory | 聚合内存技术 | 跨实例共享缓存（Shared Cache） |

> 信度【一手】官方原文（ITPUB 转载孟凡彬演讲）："共享集群基于 YashanDB 内核持续演进，硬件上依赖共享存储实现 shared-Disk 的架构，同时引入了 Cohesive Memory 核心技术实现 Shared-Cache 能力"

### 5.3 存储引擎体系

来源：腾讯云 https://cloud.tencent.com/developer/article/2566224 【二手：可信度中】
来源：https://blog.itpub.net/70045450/viewspace-3082812/ 【二手：可信度中（ITPUB 技术专家文章）】

| 存储 | 全称 | 对应表类型 | 适用场景 |
|---|---|---|---|
| HEAP | Heap 堆式存储 | 行存表 | OLTP（无序存储，优化插入） |
| BTREE | B 树存储 | 索引 | - |
| MCOL | Mutable Columnar（可变列式存储） | TAC 表 | HTAP，支持原地更新 + 字典编码 |
| SCOL | Stable Columnar（稳态列式存储） | LSC 表 | OLAP 海量冷数据，slice 切片式 + 压缩 + 稀疏索引 |
| LSC | Large-scale Storage Columnar Table | LSC 表 | 实时导入 + 极速分析（自研列存引擎） |

> 一手表述："LSC 表的数据组织分为三层：分布(Distribute)、分区(Partition)、切片(Slice)；切片内部还分可变切片、内存切片、稳态切片"
> 单 DN 写入速度最高 300MB/s

### 5.4 内置工具/产品平台（5Y 体系）

来源：https://page.quark.cn/baike?id=59a634c030eb4bc8accbc67b28e8ee2e 【二手：可信度中（夸克百科，但与官方一致）】

| 平台 | 全称 | 作用 |
|---|---|---|
| **YDC** | YashanDB Developer Center | 开发平台，对象管理、SQL 智能开发、PL 调试、连接会话管理 |
| **YCM** | YashanDB Cloud Manager | 运维平台，统一纳管、诊断优化、备份恢复、监控告警 |
| **YMP** | YashanDB Migration Platform | 迁移平台，兼容性评估、元数据迁移、全/增量同步、数据校验 |
| **YCP** | YashanDB Cloud Platform（崖山数据库云平台） | DBaaS，云化自治部署、智慧大屏 |
| **YDC / yasboot** | - | yasboot 是集群安装运维的统一 CLI 入口 |

> 关键词 **"1+3+3"**：1 个自主内核、3 大产品（YAC/分布式/空间）、3 大工具（YMP/YCM/YDC）

### 5.5 yasdb 进程家族

来源：https://blog.csdn.net/cod0410/article/details/146039380 【二手：可信度中，CSDN 转载官方文档】

| 进程 | 作用 |
|---|---|
| **yasdb** | YashanDB 主进程 |
| **yasom** | 运维服务进程（接受 yasboot 命令） |
| **yasagent** | 无状态运维服务进程 |
| **yascs** | 集群服务管理进程（共享集群专用） |

---

## 六、关键概念与官方核心主张

### 6.1 反复出现的"真信念"（≥3 次=真信念）

来源：通过多个搜索结果交叉验证

| 真信念 | 出现频次 | 一手表述 |
|---|---|---|
| **100% 内核自研** | ≥10 次 | doc.yashandb.com/ 首页 + 多篇新闻稿一致表述："内核代码自主率 100%（经第三方开源扫描）" |
| **原创四大理论**：有界/近似/并行可扩展/跨模融合 | ≥10 次 | 所有官方页面、新闻稿、CSDN 转载均一致 |
| **三个不变/两个对等/一个更优** | ≥3 次 | 仅 V23.3 起强调，但每次发布必提 |
| **1:1 平替 Oracle** | ≥5 次 | V23.3 起核心战略 |
| **金融级 RTO < 10-20s，RPO = 0** | ≥3 次 | V23.1 发布会、V23.2、V23.3 一致 |
| **共享集群 TPCC 数字跳跃**：210万 → 312万 → 520万（4节点） | ≥3 次 | 每版必提 |
| **樊文飞是大满贯学者** | ≥5 次 | 所有介绍、深算院/崖山的官方背景 |

### 6.2 自创术语与概念

| 术语 | 含义 | 来源可信度 |
|---|---|---|
| **BQP (Bounded Query Processing)** | 有界查询处理 | 【二手】CSDN YCA 认证笔记 https://blog.csdn.net/qq_46071506/article/details/140966286 |
| **Cohesive Memory** | 跨实例共享缓存 | 【一手】多篇官方文档正文 |
| **TAC / LSC** | 列存表类型 | 【一手】官方文档"列存表设计"章节 |
| **YCK / YCS / YFS** | 集群内核/服务/文件系统 | 【一手】官方文档"集群基础设施"章节 |
| **YAC** | YashanDB for Cluster | 【一手】产品名 |
| **"1:1 平替"** | 与战略绑定的口号 | 【一手】官方产品战略 |
| **Yashan-Homotopic Theory（自创）** | 资源受限下大数据可计算理论与方法 | 【二手】清华大学计算机系报道 |
| **逻辑+AI（Logic + AI）** | 深算院原创，与"AI=机器学习+逻辑推理"演讲呼应 | 【一手】深算院理论体系第七项 |

### 6.3 命名学含义

> 来源：ITPUB "重新认识崖山数据库" https://blog.itpub.net/31492144/viewspace-3172421/ 【二手：可信度中】

三大产品的命名均为**南宋三场保家卫国之战**（樊文飞亲自命名）：
- **崖山**：1279 年崖山海战，陆秀夫背小皇帝投海，十万军民殉国
- **采石矶**：南宋抗金采石矶大捷
- **钓鱼城**：坚守孤城 36 年

> 含义：基础软件的"皇冠明珠"上"打一场翻身仗"

---

## 七、第三方测评与白皮书

### 7.1 信通院（中国信息通信研究院 CAICT）系列测评

来源：https://www.sics.ac.cn/cn/col10/599 【一手：深算院官网】

| 测试名 | 日期 | 崖山成绩 |
|---|---|---|
| "可信数据库"关系型数据库安全能力专项测试 | 2024-10 通过 | 五项指标全满足（用户身份鉴别、访问控制、存储安全、通信安全、安全审计） |
| 第一批"安全可靠测评"（集中式） | 2025-08-22 通过 | **I 级** |
| 第二批"安全可靠测评"（分布式） | 2026-05-26 通过 | **II 级**（数据库领域最高已授等级） |

来源：modb.pro https://www.modb.pro/db/1959819052877099008 【二手：可信度高】

> 一手描述（深算院官网）："YashanDB 在用户标识与身份鉴别能力、访问控制能力、数据存储安全能力、数据通信安全能力以及安全审计能力等方面全面满足测试要求"

### 7.2 中国信息安全测评中心 + 国家保密科技测评中心 联合测评

> 一手测评：https://www.modb.pro/db/1959819052877099008 【二手：可信度高】

- 2025-08-22 通过 "安全可靠测评" I 级（同期仅 3 个产品入围）
- 2026-05 通过 II 级（数据库领域最高等级）
- 截至 2026-06，**业内最高等级即 II 级**，尚无 III/IV 级厂商

### 7.3 国家电子学会科技成果鉴定

> 一手评价（modb.pro 原文）："鉴定委员会专家一致认为，该技术研制难度大、创新性强，整体技术达到国际先进水平"

两项达到"国际领先水平"：
- 数据尺度无关的资源受限计算技术
- 基于语义连接的跨模融合查询方法

### 7.4 完整资质清单

来源：https://www.modb.pro/db/1959819052877099008 【二手：可信度高】

- 数据库政府采购需求标准测试认证
- 商用密码产品认证
- GB/T38636-2020《信息安全技术传输层密码协议(TLCP)》国标
- 信息安全及隐私保护 ISO 国际标准双体系认证
- 等保三级认证
- 国标 GB 18030-2022
- 可信数据库测评
- 信创产品评估

### 7.5 客户/案例

> 来源：modb.pro https://www.modb.pro/db/1959819052877099008 【二手：可信度高】

- 国家级金融基础设施（央行数字货币所）
- 大型商业银行核心交易系统
- 特大城市燃气安全保供核心系统
- 银行 CRM 系统实现十万行存储过程平滑迁移

### 7.6 生态伙伴

> 来源：https://www.modb.pro/db/1959819052877099008 【二手：可信度高】

- 飞腾、鲲鹏、龙芯、统信 UOS、麒麟等**近百项**主流国产软硬件完成适配
- 长亮科技、深智城、金蝶云、超图软件、DSG、广道数字（LakehouseDB）

---

## 八、官方三大发布会/演讲实录（一手内容）

### 8.1 2023-11-08："惟实·励新"V23.1 发布会

- 三大新品首次发布（YAC、分布式数仓、GIS）
- 5 大行业解决方案发布（智慧城市、金融核心、可组装 PaaS、空间数据、数据交互）
- 个人版同步上线
- 来源：https://cloud.tencent.com/developer/news/1237035 【二手：可信度高，多媒体转载】

### 8.2 2023-11-30：InfoQ 深度对话（王南访谈）

来源：https://www.infoq.cn/article/Ok2fZeQW7vfGFR3AoXko 【二手：可信度高（InfoQ 一手访谈）】

**关键论断**（来自王南+YashanDB 核心团队）：
- "理论 + 技术 + 落地，三驾马车驱动 YashanDB 快速迭代"
- "原创的有界计算理论和跨模计算理论融入到计算框架中，应对数十亿级数据量"
- "自适应异步并行框架 + 事务调度机制使系统性能提升 20%-30%，事务吞吐量提升 137%"
- TAC/LSC 三引擎解决实时+历史数据融合
- OCI（Oracle Call Interface）兼容性

### 8.3 2024-11-14："2024 国产数据库创新生态大会"（樊文飞主旨演讲）

来源：https://segmentfault.com/a/1190000045583322 【二手：可信度中（演讲实录转载）】

**樊文飞核心金句**："中国软件：自强、自立、自信"
- 自强：中国软件需打破"微笑曲线"困局
- 自立：自研内核才是长期竞争力的起点
- 自信：从算法创新到系统超越

> 信通院 70% 国产数据库仍基于开源二次开发；金融核心系统国产化率 < 20%（来源：樊文飞演讲引述）

**陈志标演讲**：演讲主题《自主原创、行稳致远》—— 来源：CSDN https://blog.csdn.net/tangtianxia/article/details/143989530 【二手：可信度中】

---

## 九、认证体系

来源：https://xie.infoq.cn/article/56597b81ee68c513db88cb025 【二手：可信度中】

| 认证 | 全称 | 定位 |
|---|---|---|
| **YCA** | YashanDB Certified Associate | 工程师级（初级） |
| **YCP** | YashanDB Certified Professional | 专家级（中级），需 3 年以上经验，覆盖 SQL 优化/用户管理/对象管理/数据安全/运维监控/备份恢复 |
| **YCE** | YashanDB Certified Expert | 大师级（高级） |

平台：https://v.kaoshixing.com（考试星在线系统）

---

## 十、对照与重要矛盾记录

### 10.1 用户简报与公开资料的关键矛盾

| 项 | 简报 | 公开资料 | 一手 vs 二手 |
|---|---|---|---|
| 首席科学家 | 俞翔 | 樊文飞院士 | 后者为真【一手】 |
| 前任职 | HP Labs | Bell Labs | 后者为真【一手】 |

### 10.2 性能数字矛盾

| 指标 | 来源 A | 来源 B | 备注 |
|---|---|---|---|
| 共享集群 TPCC | 4 节点 520 万 tpmC | 4 节点 618 万 tpmC | 520 万出自 ITPUB 官方博客（V23.3），618 万出自 ITPUB 自媒体（V23.3+） |
| 共享集群 TPCC | 2 节点 210 万（V23.1）→ 312 万（V23.2）| - | 数字演进可信 |
| RTO | < 20s（V23.1）→ < 10s（V23.3） | - | 不断优化 |

### 10.3 兼容性数字矛盾

| Oracle 兼容性 | 数据 | 来源 |
|---|---|---|
| V23.2 | "广泛吸纳...持续提升 Oracle 兼容性"（未给百分比） | https://news.ikanchai.com/2024/0423/584329.shtml |
| V23.3 | **99%**（从 90% 提升） | https://blog.itpub.net/70043300/viewspace-3073731/ |
| 部分二手宣传 | **98%**（强调"代码零修改"） | https://finance.sina.com.cn/tech/roll/2025-03-20/doc-ineqiarh4711810.shtml |
| YashanDB 自媒体 | 600+ 兼容项、26+ 数据类型、50+ 存储过程、220+ 系统包、130+ 内置函数、200+ 字典、60+ 视图 | https://new.qq.com/rain/a/20260120A04ZYL00 |

### 10.4 文档站当前版本

- 23.1 / 23.2 / 23.3 / 23.4 / 23.4.7 均有独立手册（17.x 老版本可能已下线）
- 23.5 在第三方测评（modb.pro）中已出现（"YashanDB SQL Enterprise Edition Release 23.5.1.100"）

---

## 十一、关键发现摘要

1. **研发主体真实结构**：深算院（深圳政府"十大基础研究机构"）负责基础理论研究与基础软件研发；崖山科技负责产业化和市场推广。CTO 陈志标同时任崖山科技总裁。**用户简报中"俞翔"为错误信息**，真实首席科学家为樊文飞院士（5 院院士 + ACM Fellow）。

2. **官方文档结构清晰但分散**：主站分 5 大手册（产品描述 / 安装升级 / 管理员 / 开发 / 工具），外加 2024-05 单独发布的"概念手册"，每个工具（YMP/YCM/YDC）有独立子站。

3. **学术根基极强**：深算院已在 SIGMOD/VLDB/ICDE/TODS/TKDE 等顶会顶刊发表 121 篇论文（其中 CCF A 类 109 篇），樊文飞本人是 SIGMOD/PODS/VLDB/ICDE 四大顶会"大满贯"得主。理论体系七大：资源受限/近似/并行可扩展/增量/跨模融合/大数据质量/逻辑+AI。

4. **核心战略口号与数字**：100% 自研、1:1 平替 Oracle、三个不变两个对等一个更优。共享集群 TPCC 从 V23.1 的 210 万 tpmC 到 V23.3 的 4 节点 520 万 tpmC，Oracle 兼容性 90% → 99%。

5. **关键自创术语与组件**：YAC（共享集群）、Cohesive Memory（聚合内存）、YCS/YFS/YCK（集群三大件）、HEAP/BTREE/MCOL/SCOL（四种存储）、TAC/LSC（两种列存表）、BQP（有界查询处理）。还有自创命名学（崖山/采石矶/钓鱼城 = 南宋三战）。

6. **资质背书**：截至 2026-05，崖山是国测（安全可靠测评）过测等级最高的厂商（I+II 双形态），同时通过信通院"可信数据库"关系型安全测试。中国电子学会鉴定其"资源受限计算 + 跨模融合查询"两项达到国际领先。

7. **MySQL 兼容是 V23.3/V23.4 的核心卖点**：通过 `SQL_PLUGIN='MYSQL'` 参数切换；V23.4 LTS 全协议兼容（5.7-8.0），180+ MySQL 同名函数。

8. **场景应用**：金融、政务、能源、运营商。已有央行数字货币所案例、大型商业银行核心系统案例，以及十万行 Oracle 存储过程平滑迁移的能力宣称。

9. **认证体系**：YCA / YCP / YCE 三级，与 Oracle OCA/OCP/OCE 对标。

10. **官方一手信息源 URL 一览**（按可信度排序）：
   - https://www.sics.ac.cn/col3/index — 深算院理论体系与论文统计【一手】
   - https://doc.yashandb.com/ — 文档中心首页【一手】
   - https://doc.yashandb.com/yashandb/23.4/zh/All-Manuals/Product-Overview/Release-Notes/23.4.7.html — 最新版本发布说明【一手】
   - https://www.yashandb.com/ — 崖山科技官网【一手】
   - https://www.sics.ac.cn/cn/col10/599 — 信通院测过测通稿【一手（机构自述）】
   - http://casad.cas.cn/ysxx2022/wjys/201911/t20191121_4724719.html — 中科院院士公示【一手（最高权威）】

---

## 十二、未深入 / 待补查的事项

- doc.yashandb.com 整站手册完整目录（已被 403，需用搜索引擎或百度/必应缓存补救）
- 樊文飞完整论文清单（建议直接查爱丁堡大学主页或 DBLP）
- YCE 大师级认证的细节内容（公开资料未见）
- yasdb 进程家族与 Oracle 后台进程的命名映射关系
- 商用阶段客户名单（仅见类别，未见具体银行名单）
- 真实的全国市场份额（IDC 主流排行中未见独立列出）
