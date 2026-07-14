---
name: pg-deploy-cluster
description: "自动化部署 PostgreSQL 高可用集群：给定服务器清单、SSH/认证信息与集群要求（版本、插件、Patroni/repmgr、VIP/HAProxy、归档备份），完成安装、initdb、流复制配置、HA 软件部署，并在沙盒中执行 switchover/failover 切换测试，最终产出含连接信息、切换测试结果、已知风险的部署报告。触发场景包括：'部署 PG 集群'、'搭建 PostgreSQL 主从'、'帮我上 Patroni'、'帮我配 repmgr 高可用'、'搭建流复制'、'一键部署数据库高可用集群'、'做个 PG 故障切换测试'。即使用户只给了几台服务器 IP 说'帮我搭个 PG 高可用'，也应触发本技能并主动追问缺失信息。"
tags: [PostgreSQL, 集群部署]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
license: GNU General Public License v2.0
homepage: https://github.com/digoal/skills
---

# PostgreSQL 高可用集群自动化部署

给定多台服务器的连接方式与集群要求，端到端完成 PostgreSQL 物理流复制高可用集群的部署、Patroni/repmgr 配置、沙盒切换测试，并输出结构化 Markdown 部署报告。**这是一项高风险、破坏性的运维操作技能**——它会执行 initdb、pg_basebackup、服务启停等不可逆动作，因此本技能的核心不是"跑得快"，而是"跑得稳、可回滚、可审计"。

## 前置要求

- 控制端（执行本技能的机器）能够以 SSH 方式免密或凭密码/密钥连接到所有目标节点（root 或有 sudo 权限的用户）。
- 目标节点操作系统为主流 Linux 发行版（Anolis OS 8/23、RHEL/CentOS、Ubuntu/Debian），本技能自动识别 `dnf`/`yum`/`apt` 并选择对应包管理器。
- 目标节点已开放或允许配置以下端口：PostgreSQL（默认 5432）、Patroni REST API（默认 8008）、etcd（2379/2380，若选择 Patroni）、HAProxy（若需要）。
- 所有密码类信息（数据库超级用户、复制用户、SSH 密码/私钥口令）**只能**通过环境变量或一次性交互输入传递，禁止写入脚本、命令行明文参数或版本控制文件；执行结束后立即从 shell 历史/环境中清理。
- 本技能不内置任何第三方下载源；所有软件均通过用户所在系统的官方/发行版仓库安装，不 curl/wget 未声明的 URL。

## 输入信息收集（Step 1）

在开始任何操作前，必须从用户处收集齐以下信息；缺失项主动追问，不得假设默认值直接执行破坏性操作（非破坏性的默认值，如目录路径，可以给出建议并请用户确认）：

| 类别 | 必需信息 | 缺失时的处理 |
|---|---|---|
| 服务器清单 | 至少 2 台：IP/主机名、OS、SSH 端口、登录方式（密钥路径 或 密码环境变量名） | 必须追问，不可虚构 IP |
| 角色规划 | 哪台是初始主库、哪台是从库、是否有独立 etcd/witness 节点 | 追问，或建议默认（2 节点：主+从） |
| 数据库密码 | postgres 超级用户密码、replicator 复制用户密码 | 提示用户通过环境变量 `PGSUPERPW` / `PGREPLPW` 提供，绝不用明文入参 |
| 版本与插件 | PostgreSQL 主版本号；插件清单及版本 | 追问；给出该版本官方仓库是否支持所需插件的检查结果 |
| HA 方案 | Patroni 或 repmgr（二选一，需用户明确） | 追问，不擅自选择 |
| DCS/接入层 | Patroni 场景：etcd 单节点还是外部集群；是否需要 VIP/HAProxy | 追问；若只给 2 台又选 Patroni，必须明确提示"无第三方仲裁，脑裂风险"并要求用户确认接受 |
| 归档与备份 | WAL 归档目录、备份策略 | 若不提供，给出默认建议（本地 `/pgwal/<ver>/archive` + 每日 base backup）并请用户确认，而非静默采用 |
| 沙盒测试环境 | 用于 switchover/failover 测试的环境（可与生产相同或独立） | 追问；生产环境直接做 failover 测试前必须二次确认 |

信息收集完成后，**必须先输出一份文字版部署计划**（架构图 + 关键参数表），等待用户明确确认（"确认部署"/"go"/同等表述）后才能进入 Step 2。这是本技能中第一个、也是最重要的破坏性操作确认点。

## 工作流程

### Step 2：环境探测

对所有目标节点执行 `scripts/00_probe_env.sh <host> <ssh_user> <ssh_port>`（通过 SSH 免密或密钥执行，不接受明文密码作为参数）。该脚本检查：OS 版本/架构、CPU/内存/磁盘、NTP/chrony 时间同步状态、防火墙（firewalld/ufw/iptables）与 SELinux 状态、目标端口是否被占用。

将探测结果汇总为表格展示给用户；若发现风险项（如时间不同步超过 1 秒、磁盘剩余不足、SELinux enforcing 且未做策略适配），必须在继续前提示并给出处理建议，得到用户确认后再自动执行调整（如放通端口、创建 NTP 同步任务）。

### Step 3：软件安装

调用 `scripts/01_install_pg.sh <pg_version> <plugin_list>`，按目标系统自动选择 `dnf install` / `yum install` / `apt install`，安装 PostgreSQL server/client/contrib 及所需插件。若插件与目标 PG 版本仓库不兼容，立即停止并向用户报告具体冲突（不得自行降级版本或跳过插件）。

若选择 Patroni：额外安装 `patroni`、`python3-etcd`（或对应 DCS 客户端）、`etcd`。
若选择 repmgr：额外安装 `repmgr<version>`。

### Step 4：目录与实例初始化（首个不可逆操作，需二次确认）

调用 `scripts/02_init_cluster.sh` 前必须再次向用户展示："本步骤将在 `<data_dir>` 执行 initdb，若该目录已有数据将被拒绝执行（不会覆盖），确认继续？"

该脚本负责：
- 创建默认目录（数据目录 `/pgdata/<version>/data`、WAL 归档目录 `/pgwal/<version>/archive`、日志目录 `/pglog/<version>`，除非用户已指定其他路径），设置属主为 `postgres`。
- 执行 `initdb`，通过 `PGSUPERPW` 环境变量设置超级用户密码（脚本内部用 `--pwfile` 方式传递，避免密码出现在进程列表中）。
- 创建复制角色 `replicator`（`REPLICATION LOGIN`），密码来自 `PGREPLPW`。

### Step 5：PostgreSQL 基础参数配置

调用 `scripts/03_configure_pg.sh`，依据探测到的内存自动计算并写入 `postgresql.conf` 推荐值（计算公式与依据见 `references/postgresql-conf-tuning.md`），包括：
`listen_addresses='*'`、`max_connections`、`shared_buffers`（总内存 25%）、`effective_cache_size`（总内存 50-75%）、`work_mem`、`maintenance_work_mem`、`wal_level=replica`、`max_wal_senders`、`wal_keep_size` 或复制槽、`archive_mode=on` 及对应 `archive_command`、按插件需求写入 `shared_preload_libraries`。

同时生成 `pg_hba.conf` 增量条目（模板见 `references/pg_hba.conf.template`），仅放通复制用户从从库/管理节点的连接，以及超级用户从管理网段的连接——不做 `0.0.0.0/0` 之类的开放式放通。

所有生成的配置在写入前先以 diff 形式展示给用户。

### Step 6：主从流复制搭建

调用 `scripts/04_setup_streaming_replication.sh <primary_host> <standby_host>`：
1. 启动主库，确认可接受复制连接，若使用复制槽则创建。
2. 在从库执行 `pg_basebackup -h <primary> -D <data_dir> -U replicator -Fp -Xs -P -R`（`-R` 自动生成 `standby.signal` 与 `primary_conninfo`）——**此步骤会清空从库目标目录，执行前必须确认从库目录为空或已按计划清理**。
3. 启动从库，轮询 `pg_stat_replication`（主库侧）与 `pg_stat_wal_receiver`（从库侧）确认复制状态为 streaming，且延迟在可接受范围。

### Step 7：HA 软件部署

- **Patroni**：调用 `scripts/05_deploy_patroni.sh`，基于 `references/patroni.yml.template` 生成每个节点的 `patroni.yml`（scope、name、restapi、etcd 连接串、postgresql 参数段），部署/连接 etcd，两节点启动 Patroni，用 `patronictl -c patroni.yml list` 确认 Leader 选举成功。若只有 2 台机器且未提供独立 etcd，必须再次提示"单点 etcd 存在脑裂与单点故障风险，建议至少 3 节点 DCS 或外部仲裁"，获得用户明确接受后才继续。
- **repmgr**：调用 `scripts/06_deploy_repmgr.sh`，基于 `references/repmgr.conf.template` 生成 `repmgr.conf`，主库执行 `repmgr primary register`，从库执行 `repmgr standby clone` + `repmgr standby register`，若需要自动故障转移则配置并启动 `repmgrd`；若用户未提供 witness 节点，明确告知"当前为手动切换模式，不会自动 failover"并写入最终报告的风险提示中。
- 若用户要求 VIP 或 HAProxy：配置对应的读写/只读端点，确保只指向当前 Leader/Primary。

### Step 8：集群功能验证

在主库创建测试库/表并插入样例数据，在从库查询确认数据已同步；通过 HA 工具（`patronictl list` 或 `repmgr cluster show`）确认所有节点状态健康；检查 `pg_stat_replication` 视图。此步骤为只读验证，无需额外确认。

### Step 9：沙盒切换测试（第二个高风险操作，需二次确认）

在执行本步骤前，必须再次确认测试环境是沙盒还是生产，并对生产环境执行 failover 测试给出明确风险提示，获得用户确认。

- 调用 `scripts/07_test_switchover.sh` 执行正常手动切换（`patronictl switchover` 或 `repmgr standby switchover`），验证新主可读写、旧主自动/手动转为从库并正常追增，记录耗时与数据一致性检查结果。
- 调用 `scripts/08_test_failover.sh` 模拟主库宕机（停止 PostgreSQL 服务，而非直接断网，以降低对生产网络的影响面，除非用户明确要求断网测试），观察 HA 软件是否按预期完成故障转移，恢复原主库后验证其能否重新以从库身份加入集群。
- 若配置了 VIP/HAProxy，额外验证应用连接端点在切换前后的漂移是否正确。
- 每一步的命令、时间戳、检查结果、异常都必须记录，供 Step 10 生成报告使用。

### Step 10：生成部署报告

汇总 Step 2-9 的所有记录，按 `references/report-template.md` 的结构生成最终 Markdown 报告，密码等敏感信息按"仅保留首尾各 1-2 字符、中间用 * 遮蔽"的方式脱敏展示，并在报告末尾明确提醒用户"请立即修改初始密码并妥善保存至密钥管理系统"。

## 输出格式

最终交付物为一份 Markdown 报告，必须包含以下章节（模板见 `references/report-template.md`）：
1. 集群架构概述（节点角色、IP、版本、HA 软件、复制模式，配一张简单的 Mermaid 拓扑图）
2. 连接信息（主库/从库直连地址、VIP/HAProxy 地址、脱敏后的用户名密码、应用连接串示例）
3. 安装软件版本清单
4. 关键配置摘要（仅列非默认参数）
5. 切换测试结果（switchover 与 failover 各自的步骤、耗时、结论）
6. 已知局限与建议（异步复制潜在数据丢失、无 witness/单点 DCS 风险、备份策略建议、参数调优建议）
7. 日常运维指引（如何手动切换、如何重建从库、如何升级版本）

## Pitfalls & Solutions

| 坑点 | 现象 | 解决方案 |
|---|---|---|
| 2 节点 Patroni 无独立 etcd | etcd 单点故障即导致整个集群不可写 | 提示用户增加第三方仲裁节点或外部 etcd 集群；若坚持 2 节点，在报告中显著标注风险 |
| pg_basebackup 覆盖非空目录 | 数据丢失 | 执行前检测目录非空则中止并报错，不自动清空 |
| 插件版本与 PG 大版本不匹配 | 安装失败或运行时报错 | 安装前查询仓库中该插件对某 PG 版本的可用性，不匹配则停止并报告 |
| 复制槽未清理导致主库 WAL 堆积磁盘打满 | 主库磁盘写满、服务不可用 | 配置监控告警阈值，或改用 `wal_keep_size` 而非无限增长的复制槽 |
| SELinux enforcing 阻断 PostgreSQL 非默认路径 | 服务无法访问自定义数据目录 | 使用 `semanage fcontext` + `restorecon` 为自定义目录打标签，而非直接关闭 SELinux |
| 防火墙未放通 Patroni REST/etcd 端口 | 节点间无法通信，Leader 选举失败 | Step 2 探测阶段提前发现并按需放通指定端口，而非放通整个网段 |
| failover 测试直接断网 | 影响面扩大到其他服务/监控 | 默认用停止 PostgreSQL 服务模拟故障，仅在用户明确要求时才做断网测试 |
| 密码通过命令行参数传递 | 泄露进程列表 `ps aux` | 一律使用环境变量或临时 pwfile，用后立即删除 pwfile |

## 注意事项

- 本技能涉及的 initdb、pg_basebackup、服务停止、故障切换等操作均**不可逆或影响生产可用性**，每一个此类步骤在文档中均标注了"需二次确认"，执行时必须严格遵守，不得因为用户此前已确认过整体计划就跳过单步确认。
- 所有密码只通过环境变量（如 `PGSUPERPW`、`PGREPLPW`）或交互式一次性输入获取，禁止出现在脚本明文、命令行参数或最终报告的非脱敏位置。
- SSH 访问目标节点仅用于本次部署所需的操作，不读取、不上传目标节点上与部署无关的文件。
- 若任何一步失败，必须停止后续步骤，向用户展示具体错误与可能原因，并询问"重试 / 跳过 / 中止"，不得自行静默重试或跳过失败步骤继续往下执行。
- 需要 root 或 sudo 权限执行系统级操作（安装软件、配置防火墙、创建目录），本技能不会尝试提权绕过，若权限不足需向用户明确报告。
- 对 Anolis OS 8（`yum`）与 Anolis OS 23（`dnf`）的包管理器差异、以及 x86_64/aarch64 架构差异，脚本内部自动探测分支处理，不需要用户手工指定。
