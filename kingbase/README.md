KingbaseES 数据库 SKILLs:  
  
kingbase-fullstack-expert : Kingbase 全栈专家, 可回答任何 Kingbase 问题.  
  
以下 SKILL 适用于 KingbaseES PG 兼容模式, 使用时需要提前配置好这些环境变量: `PGHOST PGPORT PGDBNAME PGUSER PGPASSWORD` 或 明确告知 sys_log 目录的位置.  
  
kingbase-awr-report : 生成 AWR 报告  
```
给定 KingbaseES 连接串和用户密码, 生成 KingbaseES 健康报告, 类似 Oracle AWR 报告.
```
  
kingbase-find-bloat : 分析膨胀表、索引  
```
分析每个数据库中表、索引膨胀情况, 给出后续观察或操作建议.

给定一个 KingbaseES 实例的连接串和用户密码, 先列出所有数据库, 进入并分析每个数据库中表、索引膨胀情况, 根据危害经验给出一个合适的大小及比例阈值, 按膨胀大小、比例进行倒序排序, 按数据库名分组, 列出膨胀大小或膨胀比例大于阈值的表和索引; 输出库名、表名或索引名、记录数、实际大小、膨胀大小、膨胀比例、危害程度、建议; 最后总结并给出后续观察或操作建议;
```
  
kingbase-find-unused-index : 分析未使用索引  
```
找出 KingbaseES 实例每个数据库中未使用的索引.

给定一个 KingbaseES 实例的连接串和用户密码, 先列出所有数据库, 再找出每个数据库中未被使用的索引, 按索引大小倒序列出索引名、索引大小、表大小、影响评估; 给出后续观察或操作建议;
```
  
kingbase-load-spike-forensics : 对给定的一段可疑时间窗口做数据库负载飙升的多维取证分析  
```
分析过去某时间段 KingbaseES 异常负载的原因:
给定一个时间段, 分析这个时间段内数据库服务器的负载情况, 如果出现负载飙升, 则需要陈述负载飙升的精确时间段、在每个维度(包括但不限于数据库日志、数据库统计信息视图、数据库相关插件信息、服务器日志)的表现、溯源原因和影响面、并给出规避建议;
```
  
kingbase-parameter-tuning-advisor : 分析数据库工作负载和环境, 给出参数优化建议  
```
识别工作负载, 并给出 KingbaseES 实例 kingbase.conf 参数优化建议.

给定一个 KingbaseES 实例的连接串和用户密码, 并向用户询问其他额外的环境配置信息, 或者也可自动通过连接分析这个实例的 workload, 给出适合的 KingbaseES kingbase.conf 参数调整建议, 包括每一项参数优化调整前后的值, 调整它的原因, 以及调整后带来的好处.
```
  
kingbase-security-audit : 数据库安全评估, 给出建议  
```
对 KingbaseES 实例进行安全风险评估.

给定一个 KingbaseES 实例的连接串和用户密码, 对 KingbaseES 实例进行安全风险评估(包括但不限于: sys_hba.conf, 用户权限, 字段敏感信息是否加密, 来源地址是否有来自非内网, 超级用户是否被用于应用端连接, 超级用户的来源限制是否过于松懈, 异常进程CPU开销).
```
  
kingbase-sql-tuning-advisor : 分析数据库工作负载和环境, 对指定 SQL 给出优化建议  
```
给出 SQL 优化建议.

给定一条 SQL 以及 KingbaseES 实例的连接串和用户密码, 分析执行计划, 并综合相关的数据库参数、相关的数据库表、索引等对象定义, 给出 SQL 优化建议.

如需深度优化, 可采用 explain analyze ... 但如果是DML语句(执行之前注意加语句超时参数, 防止雪崩), 务必在事务中执行并在得到 explain analyze ... 结果后回滚, 如果是带 $ 变量的 SQL, 在版本支持的情况下可得到执行计划, 想办法模拟参数、或与我沟通必要信息后再执行取得执行计划;
```
  
kingbase-log-analyzer : 分析数据库给定时间段内的日志, 给出分析建议  
```
给定 KingbaseES 实例的日志目录路径, 以及需要分析的时间段, 分析这个 KingbaseES 实例在这个时间段的 stdout/csv 日志文件, 生成分析报告;
```
  
kingbase-design-audit : 分析数据库元数据和采样, 根据设计规范给出审查指引建议  
```
对 KingbaseES 实例进行数据库设计质量和潜在风险审查.

给定一个 KingbaseES 实例的连接串和用户密码, 对实例中所有数据库进行全面扫描，找出设计不规范或存在潜在使用风险的对象和模式(包括但不限于:无意义的表、字段、索引等对象命名、字段类型选择不恰当、comment 缺失、特大表未分区等等...)。
```
  
kingbase-top-sql-analyze : 分析数据库最近时间段各个维度的 TOP SQL, 给出优化建议  
```
分析 KingbaseES 实例最近时间段的 TOP SQL, 并给出优化建议.

给定一个 KingbaseES 实例的连接串和用户密码, 根据 sys_stat_statements 的信息, 找出最近时间段各个维度的 TOP SQL, 注意要收集2个快照信息后进行分析, 因为 sys_stat_statements 可能有很长历史以来的所有统计, 而我要知道当前的. 收集到 TOP SQL 后, 给出优化建议;
```
  
kingbase-bloat-root-cause : 分析数据库存在的潜在膨胀风险, 给出建议  
```
分析 KingbaseES 实例的表和索引膨胀隐患, 并给出优化建议.

给定一个 KingbaseES 实例的连接串和用户密码, 连接 KingbaseES 后, 分析数据库表和索引膨胀隐患, 例如是否有长事务、长时间未结束的2PC事务、long query、从库上是否开启了hot standby feedback相关的参数并且有长事务或long query存在(从库的信息你可以问我要). 结合收集到的信息, 以及实际的膨胀情况, 给出分析报告和优化建议;
```
  
kingbase-large-table-optimize : 分析数据库大表, 以及大表的工作负载风格, 根据工作负载风格给出优化建议  
```
分析 KingbaseES 大表和对应的工作负载, 根据大表相关工作负载, 给出优化建议.

给定一个 KingbaseES 实例的连接串和用户密码, 连接 KingbaseES 后, 分析数据库中的大表情况(对于膨胀严重的表, 要看排除膨胀水分之后还是不是大表), 分析大表的统计信息来区分大表的工作负载, 根据工作负载给出大表优化建议;
```
  
kingbase-stat-snapshot : 给 KingbaseES 的统计信息打快照并保存  
```
给 KingbaseES 的统计信息打快照并保存, 目的是收集当前重要的统计信息视图信息, 未来根据指定时间段, 从覆盖指定时间段两个最接近的快照中, 做快照差值得到这两个快照区间的统计信息累加值, 为分析提供数据支撑. 

给定一个 KingbaseES 实例的连接串和用户密码, 连接 KingbaseES 后, 给 KingbaseES 的统计信息打快照, 保存到专门的存储快照信息的 schema 下. 
```
  
kingbase-perf-insight : KingbaseES 性能洞察  
````
性能洞察. 根据 KingbaseES 实例统计信息快照, 分析在用户给定时间段内的性能瓶颈或资源使用情况, 给出深度的 performance insight 报告. 

用户指定时间段, 给定一个 KingbaseES 实例的连接串和用户密码, 以及独立的统计信息快照 schema, 从覆盖指定时间段两个最接近的统计信息快照中, 做快照差值得到这两个快照区间的统计信息累加值, 基于该数据进行分析.  

统计信息至少已包含如下 2 个视图的快照: 
```
sys_stat_statements
pg_stat_activity
```

每个数据库定义了一套存储统计信息快照历史的模板表, 每个统计信息表对应一个历史表, 额外的几个字段: 快照唯一ID、快照的时间戳、原始统计信息表被 reset 的时间戳等. 

注意: 不能用不同 reset 时间戳的两个快照进行差值分析. 因为累计数据不正确会导致分析结果错误. 如果用户给的时间区间刚好遇到统计信息快照处于不同 reset 时间戳, 则建议用户更改时间段. 

结合快照差异分析, 给出 performance insight 分析报告;
````
  
kingbase-runtime-risk : KingbaseES 数据库运行时潜在风险评估  
```
KingbaseES 数据库运行时潜在风险评估.  
  
事务回卷, 序列回卷, 冻结风暴, 复制延迟, 逻辑复制槽推进延迟, 逻辑复制槽未激活, 归档日志异常, WAL堆积, 大对象垃圾, 单点故障风险等.  
```
  
kingbase-sql-audit : 在开发提交 SQL 变更时, 审查这些 SQL 是否合规、上线后会不会对目标数据库带来风险?  
````
提供数据库连接串和用户密码, 需要变更的 SQL, 如果有必要你可以问我 SQL 的调用频率, 识别哪些是高频调用的 SQL 以全面评估风险.

连接到数据库后, 开始审查, 至少应该包含如下:
```
从执行计划看是否有明显的缺少索引而全表扫描的情况? 但不一定要加, 如果是高频访问的 SQL 须加索引进行优化. 如果只是单次请求可考虑不加, 但要提醒我.

如果有 DDL 语句应该要评估是否会 rewrite table? 是否在执行之前加了锁超时 和 语句超时, 防止在高频访问的表上执行导致的雪崩效应.

所有的语句是否符合常规的开发者规范?

是否有回退机制, 没有的话给出建议.

SQL 注入风险审查, 此处可能作为提示提醒用户自查, 因给出的SQL可能并不包含应用侧的原始SQL. 也可以询问用户应用程序端是否使用 prepared statement , 又或者是否采用 存储过程 中的变量方式 避免注入;

触发器(如果有的话), 审查是否安全;
```
````
  
  
-----
  
本地 KingbaseES 测试实例部署方法:
  
我的是 Apple M 系列芯片 macOS 
  
从 https://www.kingbase.com.cn/download.html 选择 飞腾(Aarch64)_Linux 下载 Docker image tar 包
  
导入镜像
```
docker load -i ~/Downloads/KingbaseES_V009R001C010B0004_aarch64_Docker.tar 
```
  
查看镜像名
```
docker images|grep -i kingbase
kingbase_v009r001c010b0004_single_arm:v1                                    6cb9dd8112e4       1.68GB          827MB   U 
```
  
启动 kingbaseES 实例子
```
mkdir ~/kbdata

docker run -tid --privileged \
-p 5432:54321 \
-v ~/kbdata:/home/kingbase/userdata/ \
-e NEED_START=yes  \
-e DB_USER=kingbase  \
-e DB_PASSWORD=123456 \
-e DB_MODE=pg  \
--name kingbase \
kingbase_v009r001c010b0004_single_arm:v1 \
/usr/sbin/init
```
  
如果宿主机安装过 PostgreSQL, 可直接使用 psql 连接 Kingbase:
```
PGHOST=127.0.0.1 PGPORT=5432 PGDBNAME=kingbase PGUSER=kingbase PGPASSWORD=123456 psql
```
  
或进入容器后使用 ksql 连接
```
docker exec -ti kingbase bash
ksql
```
  
-----
  
SKILL 复刻自我在龙蜥社区提交的 PostgreSQL SKILLs 
```
/skill-creator 
参考 ~/.claude/skills/pg-top-sql-analyze 这个 postgresql skill 编写对应的 kingbase skill , skill 名字中的 pg 替换为 kingbase. 
必要时参考 kingbase 官方文档, 入口地址 : https://docs.kingbase.com.cn/cn/KES-V9R1C10/introduction 注意这个 URL 只是入口, 你需要自行获得真正需要的 URL. 
优先使用 `curl -sL --noproxy '*' --max-time 30` 获取网页内容. 
目前 kingbase 实例已启动, 连接串为 PGHOST=127.0.0.1 PGPORT=5432 PGDBNAME=kingbase PGUSER=kingbase PGPASSWORD=123456 ; 在 kingbase 手册中这些环境变量可能被描述为 KINGBASE 开头例如 KINGBASEHOST 或 KINGBASE_HOST, 你别管, 请继续使用 PG 的环境变量. 
如果验证涉及日志, 验证时查看 ~/kbdata/data/sys_log 目录, 实际场景请用户提供目录路径. 
SKILL 必须用 kingbase 实例进行验证, 验证通过才算完成. 
SKILL 其他通用要求 :  
默认假设 kingbase 采用了兼容 pg 的模式 ;
连接串相关的环境变量 PGHOST PGPORT PGDBNAME PGUSER PGPASSWORD 优先采用用户提供的 ;
如果用户没有提供, 则读取环境变量 ;
如果没有环境变量, 则采用默认的 PGHOST=127.0.0.1 PGPORT=5432 PGDBNAME=kingbase PGUSER=kingbase PGPASSWORD=123456 ;
skill 的 script 应该兼容 python sdk 和 psql shell command 连接数据库 ; 
```
  
