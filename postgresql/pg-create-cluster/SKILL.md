---
name: pg-create-cluster
description: 创建 PostgreSQL 流复制集群;当用户想新建/部署 PG 流复制集群时使用
when_to_use: 用户表达"建库/部署/创建 PostgreSQL/PG 集群/流复制"等意图
contributor_type: "enterprise"
org_name: "中启乘数科技（杭州）科技有限公司"
---

# 创建 PostgreSQL 流复制集群(已有主机路径)

本 skill 通过同目录脚本 `create_pg_sr_cluster.py` 端到端驱动 CLup HTTP 接口,在**已有在线主机**上创建 PG 流复制集群(1 主 + N 备)。脚本负责登录、按主机匹配 PG 版本、preflight 校验、提交创建、轮询任务;你(Claude Code)负责对话式引导用户做选择并调用脚本。

## 环境前提
- CLup 在跑。**默认连本地 `http://127.0.0.1:8090`**(或 conf `http_port`);连远程用 `--url http://IP:port` 或 `CLUP_URL`。**建库第一步要先问用户本地还是远程**(见下文"建库第一步")。
- **凭据走环境变量(推荐)`CLUP_USER`/`CLUP_PASS`,或 `--user`/`--pass`**。绝不写死。没有先问用户要。
- 解释器: `/opt/csu_pyenv/bin/python`(自带 pycryptodome,脚本做密码加密依赖它)。
- 主机上的 PG 得是**能在该 OS 上跑起来的**(initdb 不缺 .so)。同一台机上 PG 二进制若是为别的 OS 版本编的(如 EL8 的 PG 跑在 Rocky9),initdb 会缺 `libicui18n.so.60`/`libssl.so.1.1` 而失败 —— 换装得对的主机或正确编译的 PG。

## 像聊天,不要变表单
- **每次只问 1 个问题**,等用户回答再问下一个。**绝不**写成"请提供:1.集群名 2.版本 3.节点…"清单。
- 用**真实数据**让用户做选择题:先跑 `hosts`/`vips`/`binpaths` 把真实主机/VIP/版本给用户点选,而不是开放填空。
- 每轮先扫历史对话,**已定下的绝不重问**。

## 建库第一步:问本地还是远程(在凭据之前)
开口第一件事就问:**"这次连本地 CLup 还是远程?"** —— 连接配置要先于凭据确定。
- **本地**(CLup server 跑在本机,最常见): 脚本默认连 `http://127.0.0.1:8090`(或 conf `http_port`),**命令不带 `--url`**。
- **远程**(CLup server 在别的机器): 让用户填 `--url` 的值,**必须给格式提示** —— 填 `http://<IP>:<port>`,例如 `http://10.198.170.11:8090`;**不带末尾 `/`**;端口一般 8090;写到 `IP:port` 为止,后面**不要**加 `/api`。拿到后**后续每条脚本命令都加 `--url <用户填的>`**(嫌每条都写就先 `export CLUP_URL=<url>`,之后命令省去 `--url`)。
- 再问凭据(`CLUP_USER`/`CLUP_PASS` 或 `--user`/`--pass`)。

## 建库参数:用户只需决定这些(连接本地/远程见上节;其余走默认)
1. **集群名**
2. **主库 IP**(从 `hosts` 选在线、agent 可达的)
3. **备库 IP**(1 台或多台;从剩余在线主机选;同一台不能既主又备)
4. **PG 完整版本**(用 `binpaths --host <主库IP>` 看实际装的,如 `16.10`;整个集群同一版本,各节点都得装了)
5. **VIP + 池**(跑 `vips`:它已用 CLup `get_free_vip_list` 排除被集群占用的、再用主机 IP 列表排除"是主机IP"的,直接给出**可选 VIP**;从末尾 `recommended selectable VIPs` 里挑一个,不会再撞占用/主机IP)
6. **repl 流复制账号密码**(脚本默认 repl_user=db_user、repl_pass=db_pass,和前端一致;用户要自定义再带 `--repl-user/--repl-pass`)

> 管理员账号/端口/os_user/os_uid/probe 配置缺省取模板(`template`);**setting_list 系统自动从 `get_init_db_conf` 按 PG 版本取**(含 `listen_addresses='*'` 等,关键,见下),不要问用户。

## 主路径
> 命令里 `--user <u> --pass <p>` 是凭据;**连远程 CLup 还要加 `--url <url>`(本地省略)**。下面按本地写;远程时每条都加 `--url <url>`,或先 `export CLUP_URL=<url>`。

1. **探查**(给用户做选择题):
   ```
   /opt/csu_pyenv/bin/python create_pg_sr_cluster.py --user <u> --pass <p> hosts
   /opt/csu_pyenv/bin/python create_pg_sr_cluster.py --user <u> --pass <p> vips
   /opt/csu_pyenv/bin/python create_pg_sr_cluster.py --user <u> --pass <p> binpaths --host <主库IP>
   ```
2. **创建**(参数齐了直接调;加 `--wait` 轮询到完成):
   ```
   /opt/csu_pyenv/bin/python create_pg_sr_cluster.py --user <u> --pass <p> \
     create --cluster-name <名> --primary <主库IP> --standby <备库IP1,IP2> \
     --version <完整版本> --vip <VIP> --pool-id <池ID> --repl-pass <密码> --wait
   ```
   成功打印 `SUCCESS: cluster created (task N)`。脚本内部: 登录 → 逐节点匹配 pg_bin_path → 取 setting_list(含 listen_addresses='*')→ preflight(目录空/端口/VIP)→ 组装 body(密码加密)→ 提交 → 轮询任务(`state=1` 成功、`-1` 失败)。

## 子命令速查
| 子命令 | 作用 |
|---|---|
| `login` | 验证登录 |
| `hosts` | 列在线主机 |
| `vips` | 列每池**可选 VIP**(空闲且非主机IP;末尾给 recommended)。可 `--pool-id N` 只看某池 |
| `binpaths --host IP` | 列该主机 PG 路径+版本 |
| `template` | 建库模板默认值 |
| `check --host IP --pgdata P [--port N] [--pool-id X --vip V]` | preflight 校验 |
| `create ...` | 建集群(`--wait` 轮询;端口/VIP 冲突会自动拦下不提交) |
| `task --task-id N` | 查任务状态(0=进行中,1=成功,-1=失败) |
| **`delete --cluster-id N`** | **完整拆除**: 停所有 DB → 删数据目录 → 删集群 + 释放 VIP |

## 出错时怎么办(已踩过的坑 + 解法)

**建库失败、想重新来 —— 先 `delete` 再重试。**
`delete --cluster-id N` 会把该集群的 DB 全停掉、数据目录删掉、集群记录和 VIP 都清掉,干干净净可以重试。**注意: 单独调 CLup 的 `delete_cluster` 只清表、不停 PG 不删数据;本 skill 的 `delete` 子命令已把 stop_db+delete_db(rm_pgdata)+delete_cluster 三步封装好,用它。**

常见错误:
- **`create_replication_user ... database not connected!`** → 99% 是 setting_list 问题(没 listen_addresses 导致新 PG 只听 localhost,CLup server 连不上)。本 skill 已自动从 `get_init_db_conf` 取 setting_list,正常不会再现;若改脚本时又复现,先查 setting_list 里有没有 `listen_addresses='*'`。
- **initdb 报 `error while loading shared libraries: libXXX.so`**(如 libicui18n.so.60 / libssl.so.1.1)→ 该主机的 PG 二进制是为别的 OS 版本编的(典型: EL8 的 PG 跑在 Rocky9)。换装对的 PG,或换一台 PG 编译正常的主机。
- **`The vip(X) is aready used by ...`** → VIP 被占。正常不该发生:`vips` 已用 `get_free_vip_list` 排除被占的、再排除主机IP。若仍撞上(两次 `vips` 之间被别处抢占),重跑 `vips` 换一个。
- **`port 5432 used on <host>`** → 端口被占(可能有没清掉的旧 PG)。换个 `--port`,或先 `delete` 掉占用它的集群。
- **`no pg_bin_path with version X`** → 某节点没装目标版本。跑 `binpaths --host <ip>` 看它实际装的,换版本或换主机。
- **任务 `state=-1`(失败)** → 用 `task --task-id N` 拿状态;详细错误查 CLup 后端日志 `/home/clup/clup-all/clup-server/logs/clup-server.log`(搜 `Connection refused`/`error`)或任务日志接口。
- **验证连库时报 `password authentication failed for user "postgres"`** → **别拿 `CREATE BODY` 顶层打印的 `db_pass`(如 `XuMG5a13UrsgHiWFLVoMDoOOA`)当登录密码**,那是 `to_db_text` 的 AES 加密串,不是明文。实例真实密码 = 模板默认明文 `postgres`(= `db_list` 每节点那个 `db_pass`,也是没传 `--db-pass` 时的默认值)。连库用:
  ```
  PGPASSWORD=postgres /usr/pgsql-14/bin/psql -h <VIP 或 主库IP> -U postgres
  ```
  (验证复制:`SELECT application_name,state,sync_state,sent_lsn,replay_lsn FROM pg_stat_replication;`,备库 `state=streaming` 且 `replay_lsn=sent_lsn` 即健康。)
- **`clup_cluster.state=0` 别误判为故障** → 现网 CLup 这版 `clup_cluster.state` **0 = 正常**(库里所有健康集群都是 0);CLAUDE.md/`cluster_state.so` 写的 `1=Normal` 是逻辑 HA state,不是这个表的列。判健康看 `clup_db.db_state=0`(Running)+ 主备角色正确 + `pg_stat_replication` 在 streaming。

## 范围说明(v1)
- 仅支持**已有在线主机**、**显式指定**主备节点(`--primary`/`--standby`)。至少 2 台(1 主 1 备),建议 3 台(1 主 2 备)。
- **不支持**新建虚拟机再建集群(`create_vm_sr_cluster`,留 v2)。主机不够时如实告诉用户。
- 密码走 `--pass` 会出现在进程命令行,更推荐环境变量 `CLUP_PASS`。
