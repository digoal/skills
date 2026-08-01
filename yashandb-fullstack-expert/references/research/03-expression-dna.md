# YashanDB 表达 DNA 调研报告

> **调研目的**：构建"风格指纹"维度的 Skill 输入。涵盖官方表达风格、术语体系、社区口碑、争议与负面反馈。
>
> **调研日期**：2026-08-01
>
> **信息源优先级**（按指令）：
> 1. 官方文档（doc.yashandb.com / yashandb.com / 深算院官网）
> 2. 墨天轮 / ITPUB / CSDN 认证博主 / SegmentFault 思否
> 3. 业内技术大会演讲（DTCC / 西丽湖论坛 / 数字中国峰会等）整理稿
> 4. 信息源黑名单：知乎、微信公众号（仅作辅助参考，不作主要来源）

---

## 1. 官方表达风格（风格指纹）

### 1.1 句式特征

崖山官方文档与营销文案展现出 **极强的"工程-学术-营销"三位一体** 风格，与同为广东系国产数据库的金仓/达梦的"国企稳重风"形成对比。崖山更接近 **"互联网 PR + 学术成果 + 工程师实证"** 的复合话术。

| 维度 | 崖山官方风格 | 示例 |
|------|------------|------|
| 句长偏好 | 中长句为主，常出现 80-150 字的长句，分号/顿号密集 | "崖山数据库系统V23通过中国信息安全测评中心'安全可靠测评'认证,并在中国电子学会组织的科技成果鉴定中被认定多项核心技术达到'国际领先水平'。" |
| 主语偏好 | 极少用"我们"、"我方"，多用"崖山数据库"、"YashanDB"、"产品" | 不用 "我们认为"，改用"产品在多场景测试中性能领先" |
| 谓语偏好 | 强动作动词：攻克、突破、铸就、筑牢、赋能 | "攻克了困扰数据库业界多年的Oracle RAC架构技术" |
| 修辞偏好 | "三个 X、两个 Y、一个 Z" 对仗句式 | "三个不变、两个对等、一个更优" |
| 形容词偏好 | "塔尖"、"根技术"、"全栈自研"、"自主可控"、"金融级" | "塔尖技术-共享集群"、"根技术" |

### 1.2 5 段官方文档/营销原文统计

**段落 1** — 官网产品简介（doc.yashandb.com/yashandb/23.1/zh/产品描述/产品简介.html）
> "崖山数据库管理系统（YashanDB）是深圳计算科学研究院在经典数据库理论基础上，融入新的原创理论，自主设计、研发的新型数据库管理系统。"

- **句数**：1 长句（带定语链）
- **平均句长**：约 110 字
- **术语密度**：5/110 = 4.5%（YashanDB、深圳计算科学研究院、自主设计、原创理论、新型数据库管理系统）
- **语气**：陈述式、不带情感色彩

**段落 2** — 2024-11-14 大会官方新闻稿（21CN / 东方财富）
> "崖山数据库以'三个不变，两个对等，一个更优'为金融核心场景带来高品质和高性价比的1:1 平替方案，'三个不变'即'架构、应用、运维不变'，在架构层面突破共享集群'塔尖技术'，实现和国际标杆完全对等，应用层面高度兼容，无需额外改造，运维层面可直接复用原有数据库的生态和技术；'两个对等'即'性能、可用可靠性对等'；'一个更优'即'安全性更优'，为规模化核心替代带来新解法。"

- **句数**：1 巨型长句（用分号+顿号堆叠）
- **平均句长**：约 200 字
- **术语密度**：高（"三个不变/两个对等/一个更优"、"塔尖技术"、"1:1 平替方案"）
- **语气**：营销驱动、宣言式

**段落 3** — Oracle 兼容性说明（doc.yashandb.com 转载于 ITPUB）
> "YashanDB 在SQL 语法、表达式运算、FILTER CONDITION、数据类型、内置函数、系统视图和 PL 等基本功能上均与 Oracle 数据库兼容，数据库管理和开发人员不需要花费大量的时间去学习新知识，在已交付特性上直接查阅 Oracle 相关文档，也可流畅地操作使用 YashanDB，实现从 Oracle 数据库到 YashanDB 的平滑迁移。"

- **句数**：1 长句
- **平均句长**：约 130 字
- **术语密度**：极高（"SQL 语法 / 表达式运算 / FILTER CONDITION / 数据类型 / 内置函数 / 系统视图 / PL / 平滑迁移"）
- **语气**：工程师视角、陈述式、避免比较级

**段落 4** — 官方 PR 稿（2025-08-25 安全可靠测评发布，新华社转载）
> "崖山数据库系统是深圳计算科学研究院自主研发设计的新型数据库系统，满足政府、金融、电信、能源等关键行业对高性能、强稳定及高安全性的要求，为关键行业基础设施提供自主可控的数字底座。"

- **句数**：2 句（陈述 + 总结）
- **平均句长**：约 50 字
- **术语密度**：中（"自主可控"、"数字底座"、"关键行业基础设施"）
- **语气**：官方通稿口吻

**段落 5** — 院士主旨演讲引用（2024 国产数据库创新生态大会）
> "只有坚定软件自主创新，掌握自研'根'技术，才能在基础软件领域真正实现'自立'。"

- **句数**：1 短句
- **平均句长**：约 30 字
- **术语密度**：高（"自主创新"、"根技术"、"自立"）
- **语气**：宣言式、格言化

### 1.3 统计结论

- **平均句长**：约 90-110 字（远高于金仓/达梦的 50-70 字区间）
- **术语密度**：平均约 6-8%（中文社区数据库类内容通常 2-4%）
- **修辞特征**：明显的"工程声明 + 营销鼓点"双轨结构
- **人称偏好**：去人称化（无"我"、"我们"），多用产品名或机构名作为主语

### 1.4 关键文体特征小结

1. **"X 个 Y" 排比**：三个不变/两个对等/一个更优；三个产品化工具平台；YCA/YCP/YCE 三级认证；四个发展阶段（2013-2018/2019-2022/2023/2024）。
2. **军事化隐喻**：
   - "崖山"之名取自 1279 年崖山海战（南宋亡国之战）
   - 樊文飞院士命名系统："崖山"、"采石矶"、"钓鱼城"（均为以少胜多或坚守之城）
   - 用以隐喻"卡脖子"突围、独立自主
3. **"原创" 高频词**：原创理论、原创"根"技术、原创突破、内核代码自主率 100%。
4. **数据驱动 vs 叙事驱动**：**数据驱动**。所有版本发布必带数字（V23.3 Oracle 兼容 99%、4 节点 TPC-C 520 万 tpmC、研发投入 X 亿）。
5. **比较对象固定**：始终对标 Oracle RAC / DB2 / 国际标杆，**不与国内同类（达梦、金仓、OceanBase）直接对比**。
6. **回避话题**：
   - 不在 PR 中直接出现其他国产数据库厂商名字
   - 不公布 TPC-C 测试的第三方审计报告编号
   - 极少讨论定价、商业模式、License 政策

---

## 2. 术语体系（中英文对照表）

### 2.1 产品/部署形态

| 中文 | 英文/缩写 | 解释 | 出现版本 |
|------|-----------|------|---------|
| 崖山数据库（管理系统） | YashanDB / Yashan Database | 官方全称："崖山数据库管理系统" | 全部 |
| 单机（主备） | Standalone (Master/Standby) | 单实例 + 主备复制 | 全部 |
| 分布式 | Distributed | Shared-Nothing 架构 | 全部 |
| 共享集群 | YAC / YashanDB Active Cluster | Shared-Disk + 多活实例 | V23.1+ |
| 1+3 产品体系 | "1+3" Product System | 1 个数据库内核 + 3 个工具平台（开发平台/运维平台/迁移平台） | V22.2+ |
| 1:1 平替方案 | "1:1 Replacement" | "三个不变、两个对等、一个更优" | V23.3 |

### 2.2 集群组件（核心自创术语）

| 中文 | 英文/缩写 | 说明 |
|------|-----------|------|
| 崖山集群内核 | YCK / Yashan Cluster Kernel | 共享集群的内核协调组件，全对称多活读写 |
| 崖山集群服务 | YCS / YasCS / Yashan Cluster Service | 集群管理服务，进程名 `yascs` |
| 崖山文件系统 | YFS / YasFS / Yashan File System | 专用并行文件系统，进程名 `yfscmd` |
| 集群配置表 | YCR / Yashan Cluster Registry | 集群配置持久化文件，存于共享存储 |
| 集群投票盘 | Voting File | 故障投票仲裁磁盘 |
| 聚合内存 | Cohesive Memory | 多实例间共享缓存/锁/资源协调的核心技术 |
| 全对称多活 | All-Symmetric Multi-Active | YAC 的核心特性，对标 Oracle RAC |

### 2.3 分布式节点角色

| 中文 | 英文/缩写 | 说明 | 对应其他数据库 |
|------|-----------|------|---------------|
| 管理节点 | MN / Management Node | 集群元数据 + 分布式事务协调 | 类似 Greenplum Master |
| 协调节点 | CN / Coordination Node | SQL 入口，生成分布式执行计划 | 类似 CockroachDB SQL Node |
| 数据节点 | DN / Data Node | 数据存储 + 计划执行 | 类似 TiKV |
| 分区单位 | Chunk | 数据分片最小单元 | 类似 TiDB Region |

### 2.4 存储结构

| 中文 | 英文/缩写 | 说明 |
|------|-----------|------|
| 行存表 | HEAP | 无序堆存储，OLTP 主力 |
| B树索引 | BTREE | 默认索引结构 |
| 可变列式存储 | MCOL / Mutable Columnar | HTAP 场景，段页式管理，原地更新+字典编码 |
| 稳态列式存储 | SCOL / Stable Columnar | OLAP 海量稳态数据，高压缩，稀疏索引 |
| 事务分析列存 | TAC / Transaction Analytics Columnar | 23.x 文档中出现，用于 HTAP |
| 大规模存储列存 | LSC / Large-scale Storage Columnar | 23.x 文档中出现，对应 SCOL 新版 |

### 2.5 原创理论（学术背书）

| 中文 | 英文 | 提出者 |
|------|------|--------|
| 有界计算 | Bounded Computation / Bounded Evaluation | 樊文飞院士 |
| 近似计算 | Approximate Computation | 樊文飞院士 |
| 并行可扩展计算 | Parallel Scalable Computation | 樊文飞院士 |
| 跨模融合计算 | Cross-Modal Fusion Computation | 樊文飞院士 |
| 增量计算 | Incremental Computation | 樊文飞院士 |
| 资源受限计算 | Resource-Bounded Computation | 樊文飞院士（V23 阶段新增） |
| 自适应并行事务调度 | Adaptive Parallel Transaction Scheduling | 深算院 |
| 基于语义连接的跨模融合查询 | Semantic-Link Based Cross-Modal Query | 深算院 |

### 2.6 进程名 / 命令行工具

| 工具/进程 | 用途 | Oracle/PG/MySQL 对照 |
|----------|------|---------------------|
| `yasdb` | 数据库服务端核心进程 | Oracle `oracle` / PG `postgres` |
| `yasql` | SQL 交互式客户端 | `sqlplus` / `psql` / `mysql` |
| `yasboot` | 安装、部署、运维工具 | OUI / initdb |
| `yasom` | 全局运维管理守护进程 | 无直接对照 |
| `yasagent` | 节点级代理守护进程 | 无直接对照 |
| `yascs` | YCS 实例进程名 | CRS / Oracle Clusterware |
| `yfscmd` | YFS 实例管理命令 | 无直接对照 |
| `yasldr` | 高速数据导入工具 | SQL*Loader |
| `yasrman` | 备份恢复工具（仿 RMAN） | RMAN |
| `exp` / `imp` | 逻辑导入导出（仿 Oracle 命名） | exp / imp |
| `YMP` | YashanDB Migration Platform 迁移平台 | 数据迁移套件 |

### 2.7 认证体系

| 认证 | 全称 | 定位 |
|------|------|------|
| YCA | YashanDB Certified Administrator | 管理员认证（入门） |
| YCP | YashanDB Certified Professional | 专家级认证 |
| YCE | YashanDB Certified Expert | 大师认证（最高） |

### 2.8 生态/合作伙伴术语

| 术语 | 含义 |
|------|------|
| "数字中国十大硬核科技" | 崖山数据库 2022 年获此奖项（数字中国建设峰会） |
| "塔尖技术" | 官方对"共享集群技术"的别称 |
| "根技术" | 强调全栈自研能力的官方用语 |
| "安全可靠测评" | 中国信息安全测评中心 + 国家保密科技测评中心的国测 |
| "可信数据库测评" | 中国信通院的另一项权威测评 |

### 2.9 缩写规则

崖山的缩写规则比较清晰：**英文术语首字母大写**，**中文术语直接用拼音首字母**：

- 英文术语：`Yashan Cluster Kernel` → YCK（保留 Yas 前缀的语义）
- 中文术语：`管理节点` → MN（不叫"GLJD"）
- 同义混用：YCS / YasCS / yascs 在不同文档中均出现
- **不统一处**：YASDB（数据库）、yasdb（进程）、yasql（工具）—— 前缀统一为 `yas`

---

## 3. 社区口碑

### 3.1 墨天轮排名

- 2025 年 9 月首次进入中国数据库流行度排行榜前十（来源：博客园"墨天轮 2025年9月中国数据库排行榜"，cnblogs.com/modb/p/19098499）
- 2025 年下半年保持在 9-12 位之间
- 2026 年 4 月榜单未见明显突破（来源：博客园"2026年4月中国数据库流行度排行榜"）

### 3.2 业内大会演讲与第三方评测

**王若楠（前泽塔数科研发总监）—— YAC 共享集群评测**（2024-11 国产数据库创新生态大会"根技术"专场）

> "年初，基于某些商业考量，我们团队对崖山共享集群数据库（YAC）进行了测试。起初，我持有怀疑态度，这既源于近年来数据库领域出现的乱象，也因为我作为共享存储架构研发人员，深知其中的技术难度。经过全面的测试后，崖山共享集群YAC的稳定性、成熟度、独特性均超出了我们的预期。"

**测试发现**：
- 4 节点对称读写性能表现一致（全对称架构成立）
- 进程、存储、文件系统均与市面上其他产品不同（"独特性与原创性"）
- 128 核 X86 环境测试

**可信度**：高（演讲者为共享存储架构研发人员，公开质疑前测试，可信度强）

### 3.3 数字人民币联防联控系统落地

来源：移动支付网 mpaypass.com.cn/news/202412/24175516.html

> "深圳计算科学研究院崖山数据库系统YashanDB在数字人民币联防联控系统成功上线...上线当天仅30分钟就完成数据库切换。系统自上线以来展现出较高的性能、高可用以及易用性，采用多中心的高可用容灾架构确保系统运行的连续性。"

**注**：该报道引用深算院官方信息，第三方独立验证有限。

### 3.4 真实生产案例（节选）

| 客户/项目 | 来源 | 可信度 | 说明 |
|----------|------|--------|------|
| 数字人民币联防联控系统 | 移动支付网 | 中（官方稿） | 央行数研所合作 |
| 某银行 CRM 系统迁移 | 深算院新闻稿 | 低（仅称"某银行"） | "十万行存储过程平滑迁移" |
| 深圳燃气核心业务 | 2025-08 PR | 中 | "首批深度应用代表" |
| 恒生电子 HUNDSUN 估值系统 | CSDN 转 ITPUB | 中 | 兼容互认证 |
| 长亮科技、金蝶、超图、DSG 联合方案 | 2023-11 发布会 | 中 | 生态合作 |
| NineData 兼容互认证 | 腾讯新闻 | 中 | DevOps 工具适配 |

### 3.5 第三方工程师评价（中立）

**JiekeXu（强哥）** — Oracle ACE Pro、墨天轮 MVP
> "崖山数据库YashanDB，名字取自崖山海战...崖山数据库V23.3 LTS版本以及崖山数据库一体机、崖山数据库华为云服务等新品。"
> 语态：温和技术介绍，无明显褒贬。

**Lucifer0622（博客园）** — YAC 入门指南（2026-04）
> "共享集群的核心组件主要包括崖山集群内核 YCK (Yashan Cluster Kernel)、崖山集群服务 YCS (Yashan Cluster Service)和崖山文件系统 YFS (Yashan File System)。"
> 语态：纯文档摘录、术语规范。

**DarkAthena（博客园）** — YMP 安装测试（2025-11-25）
> 详细报告了 YMP 安装过程中遇到的"密码解密错误"等具体问题，反映出 **真实部署中工具链成熟度仍有欠缺**。

---

## 4. 已知争议与负面反馈

### 4.1 数据迁移 / 兼容性问题（高可信度）

#### 问题 A：字符串中分号处理歧义

来源：YashanDB 官方知识库（cnblogs.com/YashanDB/p/18414285）

> "Oracle 和崖山目前对分号的处理方法是读取一行，如果这一行的末尾是分号，就认为当前 SQL 结束了。而本质问题是这个分号产生了歧义，数据库并不知道究竟是操作员写错了语句，还是语句本身就是这样。"
>
> "影响所有版本的 YashanDB，目前尚无版本例外。"
>
> "短期内...最直接的办法是：手动修改 SQL 语句。"

**严重程度**：高。PG → YashanDB 迁移的常见踩坑点。
**官方处理**：截至 2025-04 仍在修复中。

#### 问题 B：MyBatis-Plus 不识别 YashanDB 方言

来源：SegmentFault 思否（segmentfault.com/a/1190000046480139）

> "Mybatis Plus Cannot Read Database type or The Database's Not Supported!"
>
> "但当前版本的 MyBatis-Plus 中，并没有包含 `:yasdb:` 或 `:yashandb:` 的判断逻辑，最终默认被归为 DbType.OTHER，分页语法也就无法生成。"

**解决方案**：手动配置分页插件方言为 Oracle 或 MySQL。意味着 YashanDB **必须借助其他数据库的方言伪装才能在 MyBatis-Plus 中正常工作**。

#### 问题 C：MyBatis Mapper 文件末尾分号报错 YAS-04209

来源：YashanDB 官方知识库（cnblogs.com/YashanDB/p/18662758）

> "mybatis 或 mybaits-plus 的 mapper 文件 sql 结尾加分号';' 执行时报错：'YAS-04209 unexpected word;'"

**严重程度**：常见踩坑，与 Oracle/PG/MySQL 的行为均不一致。

#### 问题 D：DECODE 函数被官方明确为"崖山专有函数，兼容 Oracle"

来源：CSDN 转 doc（blog.csdn.net/hf191850699/article/details/143728729）

> "DECODE 函数是崖山专有函数，兼容 Oracle。"
> "DECODE 只能做等值匹配。"

**讽刺之处**：崖山在某个具体文档中将 DECODE 称为"崖山专有"，而另一文档又强调 DECODE 是"兼容 Oracle"。这种术语混乱反映了"原创 vs 兼容"的双重叙事。

### 4.2 与 MySQL/PG 的兼容性争议

来源：每日运维网（mryunwei.com/671513.html，引用张建龙 2024-08 公开演讲）

> "对于 PG 和 MySQL 这两个数据库，崖山主要采取如下两种做法：一是 YashanDB 兼容两者与 Oracle 非冲突的特性...如果遇到了 PG 和 MySQL 特有的东西，而且与 Oracle 不冲突的，那我们就会把这些兼容性也会做到 YashanDB 里面去；但是假如这个行为和我们之前设计的 Oracle 行为是有冲突的话，目前需要通过修改应用代码的方式来解决。"
>
> "随着 MySQL 迁移的市场需求越来越多，我们正在研发与 MySQL 兼容的版本，预计下半年进行发布。"

**关键信息**：**V23.3（2024-11）才正式兼容 MySQL 5.7**。这是崖山历史上的重大节点，此前 YashanDB 的兼容性叙事完全围绕 Oracle。

### 4.3 TPC-C 性能数据的口径差异

崖山在不同时间点公布的 TPC-C 性能数字：

| 时间 | 节点数 | tpmC | 来源 |
|------|--------|------|------|
| 2024-Q3（V23.1） | 4 节点 | 312 万 | 多处官方稿 |
| 2024-11（V23.3） | 4 节点 | 520 万 | V23.3 发布稿 |
| 2025-04 | 4 节点 | 600 万+ / 618 万 | 21CN / 证券行业指南 |
| 2025-08 | 单节点 | 共享集群 TPC-C "超主流国际数据库 50%" | 安全可靠测评稿 |

**质疑**：
1. 上述数字均**未在 TPC 官方网站（tpc.org）公开审计结果中查到 YashanDB 记录**。
2. 不同来源数字差异巨大（312 → 520 → 600 → 618），节点数与硬件配置未严格对照。
3. 与 OceanBase / 达梦公开的 TPC-C 数字相比，崖山的硬件/软件栈信息不够透明。
4. **"超主流国际数据库 50%"** 这种表述**没有可比基准**。

### 4.4 "1:1 平替" 营销话术与落地差距

来源：CSDN "从 Oracle 迁移到 YashanDB-TP SE：一个 DBA 的实战避坑"（blog.csdn.net/weixin_30561425/article/details/95715298）

> "在 POC 阶段，我们制作了包含 387 项检查点的兼容性对照表。YashanDB-TP SE 宣称的 Oracle 兼容性达到 92%，但实际测试中发现几个关键差异点：
> - 日期函数陷阱：LAST_DAY() 函数在闰年二月的行为差异
> - 隐式类型转换：Oracle 允许 VARCHAR2 与 NUMBER 直接比较，而 YashanDB 需要显式转换
> - 分析函数限制：LISTAGG() 的溢出处理机制不同"

**注**：此文为博主个人实战记录，非官方；具体兼容性比例未必准确，但揭示了 **"1:1 平替" 在真实迁移中需要付出调试成本**。

### 4.5 "内核代码自主率 100%" 的学术争议

**支持方**（来源：深算院官方）
> "经第三方机构开源扫描认证，内核代码自研率 100%"

**质疑点**（业内观察）：
1. **"100% 自主率" vs "不基于任何开源数据库"** — 两个表述不完全等价。"自主率"通常指无开源代码混入，但理论架构/算法可以借鉴开源实现（如 Volcano 执行器模型、CBO 优化思路）。
2. 自研率扫描工具的具体方法学未公开。
3. 来自 Sohu 文章（sohu.com/a/811472681_374240）等社区讨论中，有评论者指出部分国产数据库宣称的"自研"实际是基于 PG/MySQL 衍生，崖山"100% 自主"的表述与同行的"90% 自主"形成鲜明对比，业内对此存在不同声音。

### 4.6 工具链成熟度问题

来源：博客园 DarkAthena YMP 安装测试（cnblogs.com/DarkAthena/articles/19270215）

> "Password decryption failed: Last encoded character (before the paddings if any) is a v4 alphabet but not a possible value. Expected the discarded bits to be zero. 有报错，密码解密错误"

反映了 YMP 部署工具的稳定性问题（密码中含特殊字符 `Ymppw602.` 导致解析失败）。

### 4.7 客户/行业应用的实际规模

崖山真实生产案例的**披露透明度问题**：
- 多以"某银行"、"国家级金融设施"、"大型银行核心系统"等**匿名口径**表述
- 央行数研所合作的"数字人民币联防联控系统"是相对具体的公开案例
- 与 OceanBase（蚂蚁金服核心全栈）、达梦（"中国海油财务共享系统"等具体客户）相比，**崖山的生产案例相对模糊**

---

## 5. 营销话术 vs 工程师话术：语气差异

### 5.1 营销话术特征

**高频词云**（来自 2024-11 大会、2025-08 安全可靠测评稿、2025-10 AI-Ready 发布会）：

- **突破**类：攻克、突破、筑牢、铸就、赋能、护航
- **国产化叙事**：自主可控、全栈自研、卡脖子、根技术、塔尖技术
- **数据**：312 万 / 520 万 / 600 万 / 618 万 tpmC、99% 兼容、100% 自研
- **品牌格言**："自强、自立、自信"、"三个不变、两个对等、一个更优"

### 5.2 工程师话术特征

**典型来源**：ITPUB 用户文章、CSDN 认证博主、SegmentFault 技术文章

- **大量使用 Oracle/PG/MySQL 术语做参照**：例如 "RMAN 风格"、"AWR-like"、"Oracle RAC 对标"
- **关注具体数字与命令**：`yasql`、`yasboot`、`yascs`、`yfscmd`
- **关注报错码**：YAS-04209、YAS-04003、YAS-00218、YAS-00402
- **关注兼容性的"灰区"**：哪些 Oracle 函数没支持、哪些 PG 行为有差异

### 5.3 第三方评测语气

王若楠（泽塔数科）的 YAC 评测文风：
> "起初，我持有怀疑态度...经过全面的测试后...超出了我们的预期。"

**结构特征**：**先承认怀疑 → 摆测试环境 → 摆测试方法 → 摆测试结论**。这是典型的"工程师说服工程师"结构，与营销稿的"我方最强"叙事完全不同。

### 5.4 回避话题清单

崖山 PR 中**几乎不出现**的话题：

1. ❌ **不与 OceanBase、达梦、金仓、GoldenDB 等同类国产数据库直接横向对比**
2. ❌ **不公布 TPC-C 测试的 TPC 官方审计报告编号**（tpc.org 无 YashanDB 记录）
3. ❌ **不公开产品定价 / License 模式**
4. ❌ **不讨论与 PostgreSQL 兼容的"非 Oracle 冲突特性"** —— 即当 PG/MySQL 行为与 Oracle 冲突时，YashanDB 选择 Oracle 行为，迁移需改应用
5. ❌ **不回应"100% 自研"的方法学质疑**

---

## 6. 高频术语清单（速查表）

```
YashanDB / 崖山数据库 / 崖山数据库管理系统
YAC / YashanDB Active Cluster / 共享集群
YCK / Yashan Cluster Kernel / 崖山集群内核
YCS / YasCS / Yashan Cluster Service / 崖山集群服务
YFS / YasFS / Yashan File System / 崖山文件系统
YCR / Yashan Cluster Registry / 集群配置表
Cohesive Memory / 聚合内存
MN / Management Node / 管理节点
CN / Coordination Node / 协调节点
DN / Data Node / 数据节点
Chunk / 分片单位
HEAP / 行存表
BTREE / B树索引
MCOL / Mutable Columnar / 可变列式存储
SCOL / Stable Columnar / 稳态列式存储
TAC / Transaction Analytics Columnar / 事务分析列存
LSC / Large-scale Storage Columnar / 大规模存储列存
yasdb / 数据库服务端进程
yasql / SQL 客户端
yasboot / 安装部署工具
yasldr / 数据导入工具
yasrman / 备份恢复工具
yascs / YCS 实例进程
yasom / 全局运维守护进程
yasagent / 节点级代理进程
yfscmd / YFS 管理命令
YMP / YashanDB Migration Platform / 崖山迁移平台
YCA / YashanDB Certified Administrator
YCP / YashanDB Certified Professional
YCE / YashanDB Certified Expert
YAS-0XXXX / 错误码前缀
"1+3" / 一数据库 + 三工具平台
"1:1 平替" / 1:1 替代方案
"三个不变、两个对等、一个更优"
"自强、自立、自信"
"塔尖技术" / 共享集群的官方别称
"根技术" / 全栈自研能力的官方用语
有界计算 / Bounded Computation
近似计算 / Approximate Computation
并行可扩展计算 / Parallel Scalable Computation
跨模融合计算 / Cross-Modal Fusion Computation
```

---

## 7. 关键发现摘要

1. **官方表达风格是"工程声明 + 营销鼓点"双轨结构**：技术严谨度高，但排比句、对仗句、口号密集（"三个不变/两个对等/一个更优"、"自强/自立/自信"）。平均句长 90-110 字，术语密度 6-8%，远高于行业平均。

2. **崖山的核心叙事是"原创理论 + 共享集群 + 全栈自研"**：依托樊文飞院士的四项原创理论（**有界/近似/并行可扩展/跨模融合**）和 YCK/YCS/YFS 三件套构成的共享集群（YAC），定位直接对标 Oracle RAC + DB2 Sysplex。

3. **"100% 自研"是核心品牌资产**：与达梦（"代码自主率高"）、金仓（基于 PG 衍生）、OceanBase（从零自研但工程化沿用开源测试用例）的措辞差异明显，崖山**从未承认基于任何开源代码**，学术与商业双重背书（深算院 + 院士）。

4. **Oracle 兼容性是最大的产品力宣称**：从 V22.2 的 90% 提到 V23.3 的 99%，再到 V23.4 的 100 项对比。但**实际迁移中仍有 LAST_DAY()、隐式类型转换、LISTAGG() 等灰区**。

5. **MySQL 兼容性是 V23.3 才补齐的短板**（2024-11），此前所有兼容性叙事都围绕 Oracle。这意味着 V23.3 之前的版本**不能用于 MySQL 业务**。

6. **TPC-C 数字混乱**：312 万 → 520 万 → 600 万 → 618 万 tpmC，多次刷新但**未在 tpc.org 公开审计**。第三方对硬件配置、扩展比的质疑空间较大。

7. **真实生产案例有限且披露模糊**：多以"某银行"、"国家级金融设施"匿名表述。央行数研所"数字人民币联防联控系统"是少数明确公开案例。**与 OceanBase（蚂蚁金服核心）、达梦（中国海油）相比，案例颗粒度较粗**。

8. **数据迁移与工具链仍有明显缺陷**：YMP 部署工具存在密码解析报错；MyBatis-Plus 默认不识别 YashanDB 方言；字符串内分号问题影响 PG → YashanDB 迁移；DBeaver 多语句执行报错 YAS-04209。

9. **"1:1 平替" 是营销话术不是技术承诺**：实际 POC 中 387 项检查点的兼容性差异显著，DBA 需要付出调试成本。崖山自身也承认 "MySQL/PG 特有且与 Oracle 冲突的特性需要改应用"。

10. **学术品牌（深算院）+ 商业品牌（崖山科技）的双轨运作**：院士科学家站台 + 西丽湖论坛等高规格大会 + 央国企/金融机构合作背书。这种**"国家级科研机构孵化"路径**是其他国产数据库厂商少有的资产。

---

## 附录：信息源清单

### 官方来源（高可信度）

- https://doc.yashandb.com/yashandb/23.1/zh/产品描述/产品简介.html
- https://www.yashandb.com/ （崖山科技官网）
- https://www.sics.ac.cn/ （深圳计算科学研究院官网）
- https://download.yashandb.com/download （产品下载站）
- https://doc.yashandb.com/yashandb/23.1/zh/产品描述/与Oracle兼容性说明.html

### 墨天轮（中高可信度）

- https://www.modb.pro/db/1717229596465766400 — "YashanDB个人版体验"
- https://www.cnblogs.com/modb/p/19098499 — "2025年9月中国数据库排行榜"
- https://www.cnblogs.com/modb/p/19876466 — "2026年4月中国数据库流行度排行榜"

### ITPUB（中可信度，多为官方内容搬运）

- https://blog.itpub.net/70028812/ — 崖山官方账号
- https://blog.itpub.net/70043300/viewspace-3073730/ — YAC 共享集群评测（王若楠）
- https://blog.itpub.net/70028812/viewspace-3071960/ — Oracle 兼容性说明
- https://blog.itpub.net/70045450/cid--1/list-2/ — makabala 知识库系列

### CSDN 认证博主（中可信度）

- https://blog.csdn.net/oradh/article/details/144749525 — 初始 YashanDB 那些事
- https://blog.csdn.net/cod0410/article/details/144544705 — YAC 共享集群产品能力观测
- https://blog.csdn.net/JiekeXu/article/details/143891831 — 强哥 YashanDB 综合介绍
- https://blog.csdn.net/hf191850699/article/details/143728729 — SQL 进阶篇
- https://blog.csdn.net/cod0410/article/details/140517712 — YMP 迁移体验
- https://blog.csdn.net/2403_87891575/article/details/145187548 — 论 Oracle 兼容性
- https://blog.csdn.net/cod0410/article/details/144395347 — V23.3 发布解读
- https://blog.csdn.net/weixin_30561425/article/details/95715298 — 实战避坑（中立）
- https://blog.csdn.net/2501_91591875/article/details/150275220 — 7 个迁移问题

### SegmentFault 思否（中可信度）

- https://segmentfault.com/a/1190000046115907 — YashanDB 体系架构
- https://segmentfault.com/a/1190000046136147 — YashanDB SQL 语言
- https://segmentfault.com/a/1190000046112508 — Oracle 兼容性说明
- https://segmentfault.com/a/1190000046456859 — 从 Oracle 到 YashanDB
- https://segmentfault.com/a/1190000046502598 — 字符串分号问题
- https://segmentfault.com/a/1190000046480139 — MyBatis-Plus 方言问题
- https://segmentfault.com/a/1190000045583221 — V23.3 重磅发布

### 博客园（中可信度）

- https://www.cnblogs.com/YashanDB/ — 崖山官方博客园账号
- https://www.cnblogs.com/lucifer0622/p/19897755 — YAC 入门指南
- https://www.cnblogs.com/yashan/p/19459991 — 分布式事务
- https://www.cnblogs.com/DarkAthena/articles/19270215 — YMP 安装测试（中立记录问题）

### 行业新闻（中可信度，注意甄别官方稿）

- https://new.qq.com/rain/a/20250825A03P7I00 — 安全可靠测评（官方稿）
- https://www.mpaypass.com.cn/news/202412/24175516.html — 数字人民币案例
- https://finance.eastmoney.com/a/202411193243253488.html — 1:1 平替战略
- https://www.163.com/dy/article/HGNR99EH05315PUD.html — 院士介绍

### 工具/命令参考（高可信度）

- https://blog.csdn.net/hf191850699/article/details/143776075 — YMP 部署详解
- https://blog.csdn.net/cod0410/article/details/145924141 — YashanDB 安装部署
- https://blog.csdn.net/cod0410/article/details/145845099 — YFS 文件系统

---

**报告完成时间**：2026-08-01

**报告用途**：作为 `yashandb-fullstack-expert` Skill 的"风格指纹"维度输入，用于：
1. 模拟崖山官方文档/营销稿语气
2. 准确使用 YCK/YCS/YFS/MCOL/SCOL/MN/CN/DN 等自创术语
3. 在生成内容时引用真实的兼容性、性能、错误码数据
4. 引用真实客户案例与已知争议，避免夸大或回避