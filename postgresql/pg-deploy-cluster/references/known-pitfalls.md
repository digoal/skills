# 已知坑点详解

本文件是 SKILL.md 中"Pitfalls & Solutions"表格的详细展开，供排查具体问题时查阅。

## 1. 2 节点 Patroni 集群的脑裂风险

Patroni 依赖 DCS（etcd/Consul/ZooKeeper）做分布式一致性仲裁。若只部署 1 个 etcd 节点，
该节点故障会导致整个集群失去仲裁能力，Patroni 会将所有 PostgreSQL 实例降级为只读，
而非"自动选出新主"——这是安全设计，但会被误解为"高可用没生效"。

**建议**：至少 3 个 etcd 节点（可与业务节点共置，也可独立部署3台轻量级 etcd），
或使用云厂商托管的 etcd/Consul 服务。若资源受限只能 2 节点，必须在报告中显著提示此限制。

## 2. pg_basebackup 覆盖非空目录

`pg_basebackup -D <dir>` 在目标目录非空时会直接报错退出（这是好的默认行为），
但如果之前的失败尝试留下了部分文件，重跑时容易被脚本自动 `rm -rf` 清理导致误删有效数据。
本技能的脚本设计原则是：**发现非空目录一律停止并报错，绝不自动清空**，需要人工确认后清理。

## 3. 插件版本与 PG 大版本不匹配

常见案例：`postgis` 或 `pg_cron` 在 PGDG 仓库中往往按 PG 大版本单独打包
（如 `postgis34_16`、`pg_cron_16`），如果只写通用包名 `postgis`，可能装到不兼容的版本，
或在多版本共存的机器上装错目标。安装脚本统一采用 `<plugin>_<pg_version>` 优先尝试，
失败后再尝试通用包名，两者都失败则报错而非静默跳过。

## 4. 复制槽导致主库磁盘打满

如果从库长时间离线或复制中断，而主库配置了物理复制槽（replication slot），
主库会为该槽保留所有未被消费的 WAL，即使 `wal_keep_size` 设置较小也不会生效——
复制槽的保留优先级更高。这是生产事故的高发点。

**建议**：为复制槽配置监控（如 `pg_replication_slots.safe_wal_size`），
设置磁盘水位告警，并在从库确认永久下线时及时 `pg_drop_replication_slot`。

## 5. SELinux 阻断自定义数据目录

若数据目录不是 `/var/lib/pgsql/*` 默认路径，SELinux enforcing 模式下会拒绝 postgres
进程访问，报错通常出现在日志中的 `Permission denied`，而 `ls`/`chmod` 检查看起来一切正常。

**正确做法**：
```bash
semanage fcontext -a -t postgresql_db_t "/pgdata/16/data(/.*)?"
restorecon -Rv /pgdata/16/data
```
而不是直接 `setenforce 0` 关闭 SELinux（关闭会带来更大的安全面）。

## 6. Patroni REST API / etcd 端口未放通

Patroni 各节点间需要通过 REST API（默认 8008）和 etcd 客户端端口（2379）通信。
若只放通了 PostgreSQL 的 5432 端口，会出现"每个节点单独看都正常，但集群状态一直显示
异常或无法选出 Leader"的现象。Step 2 的环境探测阶段应提前发现并处理，而非等到 Step 7
部署 Patroni 时才发现连不通。

## 7. Failover 测试选择断网还是停服务

直接断网（如 iptables DROP 或拔网线模拟）更接近真实网络分区场景，但影响面更大，
可能同时影响该节点上的监控 agent、SSH 管理连接等，导致测试后难以恢复现场。
默认使用 `systemctl stop postgresql` 模拟"进程级故障"，只在用户明确要求验证
"网络分区场景下的仲裁行为"时才使用断网方式，且需提前告知运维/监控团队以免误报警。

## 8. 密码通过命令行参数传递

`some-tool --password=xxx` 这类写法会让密码明文出现在 `ps aux` 输出、
shell history、以及某些系统的审计日志中。本技能所有脚本统一通过环境变量
（`PGSUPERPW`、`PGREPLPW`）或一次性 pwfile（用后立即删除）传递密码，
不接受密码作为位置参数或 `--xxx=` 形式的命令行参数。
