# KingbaseES V8R6/V9R1 语言层 DNA：工具命令、SQL 方言、错误码与驱动

> 调研范围：命令行工具族、KSQL 方言（vs Oracle / PostgreSQL / MySQL）、JDBC/ODBC 驱动、PL/SQL 兼容层、错误码与 kingbase.conf 特有参数。
> 信息源：官方手册 help.kingbase.com.cn、CSDN kingbase 认证博客、KingbaseES 中文社区。
> 截止版本：KingbaseES V8R6 / V9R1C2B14 / V9R2C12（Oracle 兼容版） / V9R3C11（MySQL 兼容版） / V9R4C12（SQLServer 兼容版）。

---

## 1. 命令行工具族速查

### 1.1 服务器管理：sys_ctl（pg_ctl 的金仓改造版）

`sys_ctl` 几乎照搬 `pg_ctl` 语法，但可执行文件叫 `kingbase`，数据目录默认放 `data/`。

| 子命令 | 用法 | 等价 PG | 备注 |
|---|---|---|---|
| `initdb` | `initdb -USYSTEM -D data --case-insensitive` | `initdb` | `initdb` 决定大小写敏感（实例级） |
| `start` | `sys_ctl start -D /data -l logfile` | `pg_ctl start` | 集群用 `sys_monitor.sh start` |
| `stop` | `sys_ctl stop -D /data -m smart\|fast\|immediate` | `pg_ctl stop` | 三种 shutdown 模式同 PG |
| `restart` | `sys_ctl restart -D /data` | `pg_ctl restart` | — |
| `reload` | `sys_ctl reload -D /data` | `pg_ctl reload` | 重载 `kingbase.conf` / `sys_hba.conf` |
| `status` | `sys_ctl status -D /data` | `pg_ctl status` | — |
| `promote` | `sys_ctl promote -D /data` | `pg_ctl promote` | 主备切换提升备机为主 |
| `logrotate` | `sys_ctl logrotate -D /data` | `pg_ctl logrotate` | 轮转日志 |
| `kill` | `sys_ctl kill SIGNALNAME PID` | `pg_ctl kill` | — |

**关键差异**：
- 配置文件名为 `kingbase.conf`（不是 `postgresql.conf`），但 KES 仍兼容 `postgresql.conf` 别名
- HBA 文件叫 `sys_hba.conf`（PG 是 `pg_hba.conf`），格式与 PG `pg_hba.conf` 几乎一致
- 默认端口 `54321`（PG 是 `5432`），默认值改写以避免与 PG 冲突
- 后台进程名是 `kingbase`（不是 `postgres`），用 `ps -ef | grep kingbase` 查
- 来源：<https://blog.csdn.net/Kingbase_/article/details/122843516>、<https://www.cnblogs.com/kingbase/archive/2021/10/12.html>

### 1.2 集群管理：sys_monitor.sh（R6 起的主备集群入口）

| 操作 | 命令 | 备注 |
|---|---|---|
| 整集群启动 | `sys_monitor.sh start` | 先启主 → 加载 VIP → 启备 |
| 整集群停止 | `sys_monitor.sh stop` | 默认 `smart` 模式 |
| 整集群重启 | `sys_monitor.sh restart` | — |
| 单节点起/停 | `sys_monitor.sh startlocal\|stoplocal` | 仅控制本节点 |
| 集群状态 | `repmgr cluster show` | 借用 repmgr 语义 |
| 故障切换 | `sys_monitor.sh failover` | 提升备为主 |
| VIP 漂移 | 集群脚本自动 `arping` | 需 arping 属主为 kingbase 用户 |
| 监控进程开关 | `monitor_exporter.sh start\|stop` | 启停 node_exporter/kingbase_exporter |

**典型坑**：
- `incorrect command permissions for the virtual ip` → `arping` 文件属主必须为 `kingbase` 用户，否则 VIP 漂移失败
- `The virtual ip has already exists and not on primary host` → 旧 VIP 未释放，需先 `arping -U` 释放或手工 `ip addr del`
- `awk: symbol lookup error: libreadline.so.7: undefined symbol: up` → 部署 postgis 后 awk 加载的 readline 与 KES 自带版本冲突，需 `LD_LIBRARY_PATH` 隔离
- 来源：<https://blog.csdn.net/lyu1026/article/details/129312492>、<https://www.cnblogs.com/tiany1224/p/16639455.html>、<https://www.cnblogs.com/kingbase/p/17561142.html>

### 1.3 客户端：ksql（psql 的金仓改造版）

`ksql` 是 KingbaseES 交互式客户端，psql 的方言变体。

**常用参数**：

```
ksql [选项]... [数据库名 [用户名]]
  -h HOST     连接服务器 IP（默认本地 socket）
  -p PORT     端口（默认 54321）
  -U USER     用户名
  -d DBNAME   目标库
  -W          强制口令提示
  -c "SQL"    执行单条 SQL 后退出
  -f file.sql  批量执行 SQL 脚本
  -l          列出所有数据库
  -V          打印版本
  -o file     输出到文件
  -X          不读取 ~/.ksqlrc
  -1          整体作为一个事务
  -B          启用验证码登录
  -M          启用客户端加密
```

**元命令（与 psql 对齐）**：

| 元命令 | 作用 |
|---|---|
| `\l+` | 列出所有数据库（详细） |
| `\c db user` | 切换数据库/用户 |
| `\dn+` | 列出模式及权限 |
| `\du+` | 列出所有用户/角色 |
| `\dt schema.*` | 列出指定模式下所有表 |
| `\d table` | 查看表结构（包含列、索引、约束、触发器） |
| `\d+ table` | 查看表结构（详细） |
| `\i file.sql` | 执行 SQL 脚本 |
| `\o file` | 把后续输出重定向到文件 |
| `\! cmd` | 执行 shell 命令 |
| `\q` | 退出 |
| `\conninfo` | 显示当前连接信息 |
| `\a` | 切换对齐/非对齐模式 |
| `\r` | 清空查询缓冲 |

**与 psql 的差异**：
- 中文 help：`echo "export LANG=zh_CN.UTF-8" >> ~/.bashrc` 后 `\?` 输出中文
- 不能 Ctrl+L 清屏（KStudio 中可行）
- 不支持 `\copy ... from stdin` 的 stdin 重定向（必须用文件）
- 来源：<https://blog.csdn.net/arthemis_14/article/details/124028836>、<https://blog.csdn.net/arthemis_14/article/details/142177667>、<https://blog.csdn.net/weixin_58142792/article/details/135351919>

### 1.4 备份恢复工具族

| 工具 | 作用 | 等价 PG | 关键参数 |
|---|---|---|---|
| `sys_dump` | 逻辑备份单库 | `pg_dump` | `-F c\|p\|d\|t`、`-Z 6`、`-j 4` |
| `sys_dumpall` | 备份全集群（含角色/表空间） | `pg_dumpall` | — |
| `sys_restore` | 恢复 dump 文件 | `pg_restore` | `-g srcSch -G tgtSch` 跨模式恢复 |
| `sys_rman` | 物理备份（增量+WAL 归档） | `pg_rman` | 需开启 WAL 归档 |
| `ksql -f` | 恢复纯 SQL 脚本 | `psql -f` | 替代 sys_restore 的 SQL 场景 |
| `initdb` | 初始化新实例 | `initdb` | `-m oracle\|pg\|mysql` 决定兼容模式 |

**典型命令**：
```bash
# 逻辑备份（自定义压缩格式）
sys_dump -h 192.168.1.100 -p 54321 -U backup_admin \
  -F c -Z 6 -j 4 -f /backup/db_$(date +%Y%m%d).dmp PROD_DB

# 跨模式恢复
sys_restore -h 127.0.0.1 -U system -d target_db \
  -g source_schema -G target_schema /backup/db.dmp

# 物理备份（基于 sys_rman）
sys_rman backup --backup-mode=full --kingbase-path=/data
```

来源：<https://www.cnblogs.com/kingbase/p/16582112.html>、<https://blog.csdn.net/sinat_36528886/article/details/134450141>、<https://help.kingbase.com.cn/v8/highly/backup-restore/index.html>

### 1.5 工具全景

| 工具 | 形态 | 适用场景 |
|---|---|---|
| `ksql` | CLI | DBA/开发，远程/脚本化 |
| `sys_ctl` | CLI | 服务启停 |
| `sys_monitor.sh` | 集群脚本 | R6/R3 主备集群 |
| `sys_dump`/`sys_restore` | CLI | 逻辑备份恢复 |
| `sys_rman` | CLI | 物理备份恢复 |
| `KStudio`（含 EasyKStudio） | GUI | 库对象管理、SQL 编辑、EXPLAIN 可视化 |
| `KEMCC`（金仓统一管控平台） | Web | 多集群/多实例纳管、批量部署、读写分离切换 |
| `KDTS`（Kingbase Data Transformation Service） | Web | Oracle/MySQL/SQLServer/PG/GBase/DM → KES 迁移 |
| `KMonitor` | Web + Prometheus | 指标采集 + Grafana 面板 + 告警 |
| `KDDM`（Kingbase Database Diagnostic Manager） | Web | 自动 AWR/KWR 快照 + 性能诊断建议 |
| `KCA`（数据库对象管理工具） | GUI | 类似 Navicat，对象浏览/编辑 |

来源：<https://help.kingbase.com.cn/v8/development/develop-transfer/index.html>、<https://max.book118.com/html/2022/0927/6112125224004242.shtm>、<https://blog.csdn.net/weixin_45564816/article/details/140895980>

---

## 2. KSQL 方言差异表（≥20 行：KSQL vs Oracle vs PostgreSQL）

> 兼容模式由 `compatible_mode = 'oracle' | 'postgresql' | 'mysql'` 决定，可在 `kingbase.conf` 全局、initdb 初始化、单库 `CREATE DATABASE ... WITH COMPATIBLE_MODE = 'oracle'`、会话级 `SET compatible_mode TO 'oracle'` 四个粒度设置。

| # | 维度 | KSQL（Oracle 兼容模式） | Oracle | KSQL（PG 兼容模式） | PostgreSQL | KSQL（MySQL 兼容模式） | MySQL |
|---|---|---|---|---|---|---|---|
| 1 | 序列（自增） | `SEQUENCE` + `NEXTVAL` / `CURRVAL`，支持 `CREATE SEQUENCE ... START WITH N INCREMENT BY N` | `SEQUENCE` + `NEXTVAL`/`CURRVAL` | `SEQUENCE` + `nextval()`，`SERIAL`/`BIGSERIAL` | `SERIAL`/`SEQUENCE` | `AUTO_INCREMENT` | `AUTO_INCREMENT` |
| 2 | 伪列分页 | `WHERE ROWNUM < N` | `ROWNUM` 伪列 | `LIMIT N OFFSET M` | `LIMIT/OFFSET` 或 `FETCH FIRST N ROWS ONLY` | `LIMIT N OFFSET M` | `LIMIT/OFFSET` |
| 3 | 高级分页 | `OFFSET N ROWS FETCH NEXT M ROWS ONLY` | `OFFSET N ROWS FETCH NEXT M ROWS ONLY`（12c+） | `LIMIT/OFFSET` | `LIMIT/OFFSET` | `LIMIT/OFFSET` | `LIMIT/OFFSET` |
| 4 | 虚表 | `DUAL`（保留 Oracle 语义） | `DUAL` | 可省略 `FROM` | 不可省略（但允许 `SELECT 1;` 不带 FROM） | `DUAL`（保留） | 可省略 `FROM` |
| 5 | 当前时间 | `SYSDATE`/`SYSTIMESTAMP` | `SYSDATE`/`SYSTIMESTAMP` | `CURRENT_TIMESTAMP`/`now()` | `now()`/`CURRENT_TIMESTAMP` | `NOW()`/`CURRENT_TIMESTAMP` | `NOW()`/`CURRENT_TIMESTAMP` |
| 6 | 字符串拼接 | `\|\|` 或 `CONCAT()` | `\|\|` | `\|\|` | `\|\|` | `CONCAT()`（`\|\|` 在非 strict 模式可用） | `CONCAT()` |
| 7 | NULL 处理 | `NVL(a,b)`、`NVL2(a,b,c)`、`COALESCE(a,b,c)` | `NVL`/`NVL2`/`COALESCE` | `COALESCE` | `COALESCE` | `IFNULL(a,b)`、`COALESCE` | `IFNULL`/`COALESCE` |
| 8 | 条件表达式 | `DECODE(...)` + `CASE WHEN` | `DECODE` + `CASE` | `CASE WHEN` | `CASE` | `CASE WHEN` + `IF()` | `IF()` + `CASE` |
| 9 | 数值类型 | `NUMBER(p,s)`（p 1-38，s -84-127） | `NUMBER(p,s)` | `NUMERIC(p,s)`/`INTEGER` | `NUMERIC`/`INTEGER` | `DECIMAL(p,s)`/`INT` | `DECIMAL`/`INT` |
| 10 | 字符类型 | `VARCHAR2(n BYTE\|CHAR)`、`NVARCHAR2`、`CLOB`、`NCLOB` | 同左 | `VARCHAR(n)`、`TEXT` | `VARCHAR`/`TEXT` | `VARCHAR(n)`、`TEXT` | `VARCHAR`/`TEXT` |
| 11 | 日期类型 | `DATE`（含时分秒） | `DATE` 含时分秒 | `DATE`（仅日期） | `DATE` 仅日期 | `DATETIME`/`TIMESTAMP` | `DATETIME`/`TIMESTAMP` |
| 12 | 时间戳 | `TIMESTAMP`、`TIMESTAMP WITH TIME ZONE` | `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE` | `TIMESTAMP`/`TIMESTAMPTZ` | `TIMESTAMP`/`TIMESTAMPTZ` | `DATETIME`/`TIMESTAMP` | `DATETIME`/`TIMESTAMP` |
| 13 | 大对象 | `BLOB`/`CLOB`/`NCLOB` + `DBMS_LOB` | `BLOB`/`CLOB`/`DBMS_LOB` | `BYTEA`/`TEXT` | `BYTEA`/`TEXT` | `BLOB`/`TEXT` | `BLOB`/`TEXT` |
| 14 | 大小写敏感 | 实例级 `case_sensitive=Y/N`（initdb 决定）；不引则转大写/小写 | 默认不敏感，存大写 | 标识符统一小写，区分大小写 | 区分大小写 | 不区分 | 不区分 |
| 15 | 标识符引号 | `"`（双引号 = 严格区分） | `"`（双引号 = 严格区分） | `"`（双引号 = 严格区分） | `"` | `` ` ``（反引号） | `` ` ``（反引号） |
| 16 | 字符串引号 | `''` | `''` | `''` | `''` | `''` | `''` |
| 17 | 递归查询 | `CONNECT BY ... START WITH ...`（Oracle 语法） | `CONNECT BY` | `WITH RECURSIVE` | `WITH RECURSIVE` | `WITH RECURSIVE` | `WITH RECURSIVE`（8.0+） |
| 18 | DECODE 函数 | `DECODE(col, v1, r1, v2, r2, default)` | 同左 | 不支持 | 不支持 | 不支持 | 不支持 |
| 19 | (+) 外连接 | 支持 Oracle 风格 `WHERE t1.x = t2.x(+)` | `(+)` 语法 | 不支持，必须 `LEFT JOIN` | 必须显式 JOIN | 不支持 | 必须显式 JOIN |
| 20 | 层次查询 | `LEVEL`、`CONNECT_BY_ISLEAF` 伪列 | `LEVEL`/`CONNECT_BY_ISLEAF` | 用 `WITH RECURSIVE` | 用 `WITH RECURSIVE` | 用 `WITH RECURSIVE` | 用 `WITH RECURSIVE` |
| 21 | 注释 | `--`、`/* */` | `--`、`/* */` | `--`、`/* */` | `--`、`/* */` | `--`、`/* */`、`#` | `--`、`/* */`、`#` |
| 22 | 模式终止符 | `/`（SQL*Plus 兼容，需 `SET SQLTERM ;` 切回） | `;` 或 `/` | `;` | `;` | `;` | `;` |
| 23 | 字符串转义 | `''` 表示单引号；`q'[xxx]'` | `''` 或 `q'[]'` | `''` 或 `E'\\\\'` | `''` 或 `E'\\\\'` | `''` 或 `\\\\'` | `''` 或 `\\\\'` |
| 24 | 事务控制 | `COMMIT`/`ROLLBACK`/`SAVEPOINT` | 同左 | 同左 | 同左 | 同左 + `autocommit` 默认 | 同左 |
| 25 | 同义词 | `CREATE [PUBLIC] SYNONYM ... FOR ...` | 同左 | 不支持 | 不支持 | 不支持 | 不支持 |
| 26 | 外部链接（DBLink） | `CREATE DATABASE LINK ... USING 'dsn'`（需 `kdb_database_link` 扩展） | `CREATE DATABASE LINK` | `dblink` 扩展（PG 风格） | `dblink` 扩展 | `FEDERATED` 引擎 | `FEDERATED` 引擎 |
| 27 | 序列引用 | `seq.NEXTVAL` / `seq.CURRVAL` | 同左 | `nextval('seq')` / `currval('seq')` | 同左 | `AUTO_INCREMENT`，无 NEXTVAL | — |
| 28 | 子查询别名 | 必带 `SELECT * FROM (sub) alias` | 必须有别名 | 子查询可不带别名 | 必须有别名 | 同 PG | 必须有别名 |
| 29 | 分页模板 | `SELECT * FROM (SELECT t.*, ROWNUM rn FROM t) WHERE rn BETWEEN N AND M` | 同左 | `SELECT * FROM t LIMIT M OFFSET N` | `SELECT * FROM t LIMIT M OFFSET N` | `SELECT * FROM t LIMIT M OFFSET N` | 同左 |
| 30 | Hint | `SELECT /*+ INDEX(t idx_col) */ ...` | 同左 | 不支持 | 不支持 | 不支持 | 不支持 |

**典型差异说明**：

- **大小写**：KES 安装时（initdb）通过 `case_sensitive=Y` 或 `--case-insensitive` 决定（实例级，事后不可改）。`Y` 适合 Oracle 迁移，`N` 适合 MySQL/SQLServer 迁移。
  - 不带双引号：大小写敏感模式 → 转大写；不敏感模式 → 转小写
  - 带双引号：严格按引号内大小写
  - 来源：<https://www.cnblogs.com/hxb2016/archive/2004/01/13/14302618.html>、<https://blog.csdn.net/u013938578/article/details/132146693>
- **DATE 语义差异**：Oracle/KES-Oracle 中 `DATE` 含时分秒（`SYSDATE` 返回 `2024-01-01 13:25:59`），PG 中 `DATE` 仅日期（`2024-01-01`）
- **DBLink**：KES 实现 `kdb_database_link` 扩展（基于 `kingbase_fdw` 包装），可访问 KES/PG/Oracle；必须 `shared_preload_libraries` 包含 `kdb_database_link`，否则新连接会报 `unsupported for database link`
  - 来源：<https://www.cnblogs.com/kingbase/p/17103117.html>
- **CONNECT BY**：KES 用 PL/SQL 解析器实现 Oracle 层次查询语法，但与 `WITH RECURSIVE` 在执行计划上不同
- **DECODE**：Oracle 兼容模式下完整支持，非兼容模式必须改写为 `CASE WHEN`
  - 来源：<https://blog.csdn.net/Kingbase_/article/details/122063237>、<https://cloud.tencent.com/developer/article/2633923>

---

## 3. KSQL 错误码速查（Kingbase 特有 + 常用 SQLSTATE）

> KES 基于 PG 内核，SQLSTATE 体系沿用 PG 标准 5 位编码。同时 KES 自定义错误码前缀 `KB`、DCI（ODBC）层错误码用数字码。

### 3.1 SQLSTATE 标准码（PostgreSQL 继承）

| SQLSTATE | 含义 | 典型原因 | 解决思路 |
|---|---|---|---|
| `00000` | successful_completion | 成功 | — |
| `01000` | warning | 通用警告 | 检查 NOTIFY/RAISE WARNING |
| `08001` | sqlclient_unable_to_establish_sqlconnection | TCP socket 连接失败 | 检查 `-p`、防火墙、监听 `listen_addresses` |
| `08006` | connection_failure | 连接中断 | 检查 VIP 漂移、网络闪断 |
| `0A000` | feature_not_supported | 特性不支持（如 Oracle 模式下用 `MERGE` 语法触发器） | 升级版本/换兼容模式 |
| `22P02` | invalid_text_representation | 类型转换失败（如 `int = 'abc'`） | 严格校验入参 |
| `22001` | string_data_right_truncation | 字符串超长 | 调字段长度或截断；MySQL 兼容模式可关 `STRICT_TRANS_TABLES` |
| `22023` | invalid_parameter_value | 参数值非法（如 `LIMIT -1`） | 校验参数 |
| `23000` | integrity_constraint_violation | 约束冲突 | 捕获 SQLSTATE 后判断重试/告警 |
| `23502` | not_null_violation | NOT NULL 字段插入 NULL | 加默认值/补非空校验 |
| `23503` | foreign_key_violation | 外键约束失败 | 检查关联表数据 |
| `23505` | unique_violation | 唯一约束冲突 | 捕获异常 + upsert |
| `23514` | check_violation | CHECK 约束失败 | 校验输入值范围 |
| `25006` | read_only_sql_transaction | 事务只读 | 改主库/提升权限 |
| `25P02` | in_failed_sql_transaction | 当前事务已失败，需 `ROLLBACK` | 捕获后 `ROLLBACK` 重开事务 |
| `34000` | cursor_name_not_found | 游标不存在 | 检查 `DECLARE` 与 `OPEN` 顺序 |
| `39000` | foreign_data_wrapper_error | FDW 错误（dblink/外部表） | 检查扩展配置 |
| `3D000` | invalid_catalog_name | 数据库不存在 | 校验 `dbname` |
| `40001` | serialization_failure | 序列化失败（SERIALIZABLE 隔离级） | 重试事务 |
| `40002` | transaction_integrity_constraint_violation | 事务完整性约束 | 事务中多语句部分失败 |
| `40P01` | deadlock_detected | 死锁 | 重试；KSQL 提供 `sys_cancel_backend(pid)`/`sys_terminate_backend(pid)` |
| `42501` | insufficient_privilege | 权限不足 | `GRANT` 补权 |
| `42703` | undefined_column | 列不存在 | 检查 schema/列名大小写（大小写敏感模式配双引号） |
| `42P01` | undefined_table | 表/视图不存在 | 检查 `search_path`、模式名 |
| `42P07` | duplicate_table | 表已存在 | 加 `IF NOT EXISTS` |
| `42P10` | duplicate_object | 对象重复（如索引） | 检查 `CREATE` 前是否存在 |
| `42883` | undefined_function | 函数不存在（schema 不一致） | 加 `schema.` 前缀或调 `search_path` |
| `42830` | invalid_foreign_key | 外键定义非法 | 检查字段类型匹配 |
| `42939` | reserved_name | 保留字/系统列名 | 加双引号或改名 |
| `53200` | out_of_memory | 内存溢出 | 调大 `shared_buffers`/`work_mem` |
| `53400` | configuration_limit_exceeded | 配置上限 | 调 `max_connections`/`max_locks_per_transaction` |
| `54000` | program_limit_exceeded | 语句/对象超长 | 拆分语句 |
| `55P03` | lock_not_available | `NOWAIT` 锁等待超时 | 重试/调整锁策略 |
| `57014` | query_canceled | 用户取消（`pg_cancel_backend`） | 客户端超时设置 |
| `57P01` | admin_shutdown | 管理员 shutdown | 检查 `sys_ctl stop` 操作 |
| `57P02` | crash_shutdown | 进程崩溃 | 查 `sys_log`，重启服务 |
| `57P03` | cannot_connect_now | 数据库启动中 | 等待 startup 完成 |
| `58000` | system_error | 内部错误 | 收集 `sys_log` 找研发 |
| `58030` | io_error | 磁盘 I/O 失败 | 检查磁盘空间、文件权限 |
| `F0000` | config_file_error | 配置错误 | `kingbase -D data --check-conf` 校验 |
| `KB001` | ksql_syntax_error | 语法错误（KES 自定义） | 检查 SQL |
| `KB002` | ksql_privilege_error | 自定义权限错误 | 审计用户权限 |

### 3.2 Kingbase 特有错误信息（中文 + 英文）

| 错误信息 | 含义 | 解决思路 |
|---|---|---|
| `致命错误: 用户 "xxx" Password 认证失败` | 认证失败 | Windows 部署：改 `sys_hba.conf` 中 `scram-sha-256` 为 `md5` 或 `trust`（限可信网络） |
| `kbjdbc:autodetected server-encoding to be GB2312` | 客户端编码探测告警 | 客户端连接串显式加 `?clientEncoding=GBK` 或 `?clientEncoding=UTF8` |
| `ERROR: requested character too large` | 字符编码不匹配（GBK 环境下用 `ASCII()` 取中文字符） | 改用 `LENGTH()/SUBSTR()`，或全角转半角函数 |
| `ERROR: Unsupported for database link` | dblink 扩展未加载到新连接 | `shared_preload_libraries += 'kdb_database_link'`，重启 |
| `ERROR: type "q" does not exist` (R6) | JDBC 元数据查询被限速（`Statement.cancel` 误中断） | 关 JDBC 自动 cancel 或重连 |
| `致命错误: 已保留的连接位置为执行` | Windows 客户端的连接池保留位置不足 | 调大客户端连接池 |
| `ERROR: 无效的 "UTF8" 编码字节顺序` | 字符集不匹配 | 客户端 / JDBC / DB 字符集统一为 UTF8/GBK/GB18030 |
| `ERROR: 字段 "xxx" 必须出现在 GROUP BY 子句中或者在聚合函数中使用` | MySQL `ONLY_FULL_GROUP_BY` 模式触发 | `SET sql_mode=''` 或改造 SQL |
| `ERROR: permission denied for schema xxx` | 模式权限不足 | `GRANT USAGE ON SCHEMA xxx TO user` |
| `ERROR: relation "xxx" does not exist` | 表不存在（大小写问题） | 在大小写敏感模式需用双引号包表名 |
| `ERROR: terminating connection due to administrator command` | 管理员终止 | 检查是否有自动 `sys_cancel_backend` 脚本误触发 |
| `ERROR: new encoding (UTF8) is incompatible with the encoding of the template database (GBK)` | 字符集与模板库不匹配 | `initdb` 时统一字符集，或用 `template0` 重建库 |
| `ERROR: could not open extension control file ".../kdb_database_link.control"` | 扩展文件不存在 | 安装扩展包，确认 `$KINGBASE/share/extension` 下有 .control |
| `KSQLException: An I/O error occurred while sending to this backend` | 网络 I/O 异常 | 调 `socketTimeout=0`/`loginTimeout`，启用连接重试 |
| `KSQLException: 无效的 "UTF8" 编码字节顺序: 0x00` | 字符含 NULL 字节 | 过滤入参 `\0` |
| `KSQLException: This connection has been closed.` | 连接被服务端关闭（VIP 漂移/超时） | 启用 JDBC 重连；使用连接池的 `testOnBorrow` |
| `KSQLException: BatchEntry ... 行被忽略：BatchEntry ... INSERT/UPDATE 失败` | 批量执行有失败行 | 改为非批量逐条提交，或捕获后跳过失败行 |

### 3.3 DCI（ODBC）层数字错误码

| 错误码 | 含义 | 备注 |
|---|---|---|
| `90028` | 字段值超出范围 | 调字段长度/精度 |
| `90001` | 语法错误 | — |
| `90002` | 对象不存在 | 表/视图/列 |
| `90003` | 权限不足 | — |
| `90005` | 数据类型不匹配 | — |
| `90100` | 连接中断 | — |
| `IM002` | 数据源未找到 / 驱动未安装 | 检查 `odbcinst.ini` |

来源：<https://blog.csdn.net/arthemis_14/article/details/134990621>、<https://blog.csdn.net/weixin_39339737/article/details/135269511>、<https://www.cnblogs.com/kingbase/p/17126626.html>

---

## 4. JDBC / ODBC 连接串模板（≥5 种场景）

### 4.1 JDBC 基础连接

```java
// 1. 基础单库连接
String url = "jdbc:kingbase8://192.168.1.100:54321/testdb";
Connection conn = DriverManager.getConnection(url, "system", "manager");

// 2. Properties 方式
String url = "jdbc:kingbase8://localhost:54321/testdb";
java.util.Properties info = new java.util.Properties();
info.put("user", "system");
info.put("password", "manager");
Connection con = DriverManager.getConnection(url, info);
```

驱动类：`com.kingbase8.Driver`（V8R6+）/ `com.kingbase.Driver`（V7，向后兼容）

### 4.2 JDBC 关键参数

| 参数 | 含义 | 示例 |
|---|---|---|
| `user` / `password` | 凭据 | `system / manager` |
| `clientEncoding` | 客户端编码 | `UTF8` / `GBK` / `GB18030` |
| `compatible_mode` | 兼容模式 | `oracle` / `postgresql` / `mysql` |
| `SocketTimeout` | socket 超时（秒） | `0`=无限；默认 `0` |
| `loginTimeout` | 登录超时（秒） | `30` |
| `tcpKeepAlive` | TCP keepalive | `true` |
| `AssumeMinServerVersion` | 声明最低服务端版本 | `9.0` |
| `ApplicationName` | 应用名（出现在 `sys_stat_activity`） | `order-service` |
| `stringtype` | 字符串类型 | `varchar` / `unspecified` |
| `loggerLevel` | 驱动日志级别 | `DEBUG` / `INFO` / `OFF` |
| `loggerFile` | 日志文件 | `/tmp/kingbase-jdbc.log` |
| `ConfigurePath` | 配置文件路径 | `jdbc.conf` |
| `USEDISPATCH` | 启用 Statement 调度 | `true` / `false` |
| `FetchSize` | 游标 fetch 大小 | `1000` |
| `rewriteBatchedInserts` | 批量 INSERT 重写 | `true` |

### 4.3 JDBC 集群与读写分离（V8R6+ 重点）

```java
// 4. JDBC 连接 V8R6 主备集群（自动选主 + 故障重连）
String url = "jdbc:kingbase8://192.168.1.100:54321,192.168.1.101:54321,192.168.1.102:54321/testdb" +
             "?targetServerType=primary" +    // 只连主
             "&loadBalanceHosts=true" +        // 负载均衡
             "&hostRecheckSeconds=10" +        // 主机漂移检测间隔
             "&socketTimeout=10" +             // socket 超时
             "&loginTimeout=5" +               // 登录超时
             "&tcpKeepAlive=true";             // TCP 心跳

// 5. JDBC 读写分离（一主两备）
String url = "jdbc:kingbase8://192.168.1.100:54321,192.168.1.101:54321,192.168.1.102:54321/testdb" +
             "?READONLYHOSTS=192.168.1.101,192.168.1.102" +  // 只读节点
             "&READONLYPORT=54321" +
             "&usedispatch=true" +              // 启用分发
             "&dispatchMode=2";                // 分发策略：2=轮询
```

**jdbc.conf 配置文件示例**（推荐生产环境用）：
```ini
USEDISPATCH=true
DISPATCHMODE=2
READONLYHOSTS=192.168.1.101,192.168.1.102
READONLYPORT=54321
SOCKETTIMEOUT=30
LOGIN_TIMEOUT=10
TCP_KEEPALIVE=true
```

### 4.4 JDBC SSL 加密连接

```java
// 6. SSL 加密连接
String url = "jdbc:kingbase8://192.168.1.100:54321/testdb" +
             "?ssl=true" +
             "&sslmode=require" +               // disable/allow/prefer/require/verify-ca/verify-full
             "&sslcert=/path/client.crt" +
             "&sslkey=/path/client.key" +
             "&sslrootcert=/path/ca.crt";
```

服务端配置（`kingbase.conf`）：
```ini
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_ca_file = 'ca.crt'
```

### 4.5 ODBC 数据源配置

**Windows 系统 DSN**：
```
Data Source Name: KINGBASE_PROD
Database: testdb
Server: 192.168.1.100
Port: 54321
User Name: SYSTEM
Password: ********
```

**Linux odbc.ini**：
```ini
[v8r6]
Description=KingbaseES
Driver=KingbaseES V8R6 ODBC Driver
Servername=192.168.1.100
Port=54321
Database=testdb
Username=SYSTEM
Password=manager
```

**odbcinst.ini**：
```ini
[KingbaseES V8R6 ODBC Driver]
Description = ODBC for KingbaseES
Driver = /home/kingbase/KingbaseES/V8/KESRealPro/V008R006C006B0021/Interface/odbc/kdbodbcw.so
Debug = 1
CommLog = 1
```

**Python pyodbc 串**：
```python
# 7. Python 连接
import pyodbc
conn = pyodbc.connect(
    "DRIVER={KingbaseES 8.6 ODBC Driver};"
    "SERVER=192.168.1.100;"
    "PORT=54321;"
    "DATABASE=testdb;"
    "UID=SYSTEM;PWD=manager"
)
```

### 4.6 Oracle 通过 DG4ODBC 访问 KingbaseES

```
-- 8. Oracle → KingbaseES DBLink
-- $ORACLE_HOME/hs/admin/initKINGBASE_DSN.ora
HS_FDS_CONNECT_INFO = KINGBASE_DSN
HS_FDS_TRACE_LEVEL = OFF
HS_LANGUAGE = AMERICAN_AMERICA.AL32UTF8
HS_NLS_NCHAR = UCS2
HS_FDS_SHAREABLE_NAME = /usr/lib64/libodbc.so

-- listener.ora 中添加
(SID_DESC =
  (SID_NAME = KINGBASE_DSN)
  (ORACLE_HOME = /u01/app/oracle)
  (PROGRAM = dg4odbc)
)
```

### 4.7 .NET / Go / Node.js 驱动

```csharp
// 9. .NET Kdbndp 连接
var conn = new NpgsqlConnection("Host=192.168.1.100;Port=54321;Username=SYSTEM;Password=manager;Database=testdb;");
```

```go
// 10. Go gokb 驱动（KingbaseES 官方维护）
import (
    "database/sql"
    _ "github.com/kingbase/gokb"
)
db, _ := sql.Open("kingbase", "host=192.168.1.100 port=54321 user=SYSTEM password=manager dbname=testdb sslmode=disable")
```

**JDBC URL 模板速查**：
```
jdbc:kingbase8://[host]:[port]/[database]?[param1=val1&param2=val2&...]
jdbc:kingbase8://host1:port1,host2:port2,host3:port3/db?loadBalanceHosts=true&targetServerType=primary
jdbc:kingbase8://host:port/db?ssl=true&sslmode=require&sslcert=...&sslkey=...&sslrootcert=...
jdbc:kingbase8://host:port/db?compatible_mode=oracle&clientEncoding=UTF8&socketTimeout=30
jdbc:kingbase8://host:port/db?READONLYHOSTS=host2,host3&usedispatch=true&dispatchMode=2
```

来源：<https://blog.csdn.net/weixin_38143404/article/details/135359269>、<https://help.kingbase.com.cn/v8/development/client-interfaces/odbc/index.html>、<https://my.oschina.net/u/5489833/blog/5395172>、<https://www.cnblogs.com/gdjgs/p/20039122>、<https://www.cnblogs.com/happy-0824/p/16932763.html>

---

## 5. KStudio / KEMCC 关键操作流程

### 5.1 KStudio（GUI 客户端，类似 Navicat / DBeaver）

**安装路径**：
- Windows：`C:\KingbaseES\V8\ClientTools\guitools\KStudio\KStudio.exe`
- Linux：`/opt/Kingbase/ES/V8/ClientTools/guitools/KStudio/`
- ARM：`/usr/local/Kingbase/ClientTools/guitools/KStudio/`

**核心操作流**：
1. **连接管理**：`新建连接 → KingbaseES → 填 IP/端口/库/用户/密码 → 选 SSL → 驱动属性 → 测试`
2. **对象管理**：导航树右键 → `属性`（表结构/索引/约束/触发器一体展示）→ `查看数据`
3. **SQL 编辑器**：`Ctrl+Space` 自动补全 → `F5` 执行 → `EXPLAIN` 可视化执行计划
4. **结果集编辑**：双击单元格直接改 → 提交到 `RETURNING`
5. **数据导出**：结果集 → `导出` → CSV/XLSX/SQL/JSON
6. **逻辑备份**：右键库 → `KingbaseES dump` → 选格式/目标路径

来源：<https://blog.csdn.net/weixin_33743248/article/details/86342200>、<https://max.book118.com/html/2022/0927/6112125224004242.shtm>

### 5.2 KEMCC（金仓统一管控平台）

**核心场景**：
1. **介质管理**：上传 KingbaseES ISO → 平台识别可部署目标（单机/主备/读写分离）
2. **服务器纳管**：`服务器 → 新增 → 填 SSH 信息 → 检测磁盘挂载点 → 授信`
3. **一键部署主备**：选主备模板 → 选主/备节点 → 选 VIP → 创建实例
4. **读写分离集群切换**：主备部署后 → `实例 → 切换 → 读写分离集群`
5. **实例监控**：实例页签 → 实时 CPU/内存/连接数/QPS/TPS/主备延迟
6. **告警规则**：CPU>80% 持续 5min/磁盘使用率>90%/备库延迟>30s → 邮件/短信/钉钉

来源：<https://blog.csdn.net/LFCuiYs/article/details/156299404>

### 5.3 慢 SQL 诊断流程

```sql
-- Step 1: 开启慢 SQL 监控
-- 修改 kingbase.conf
shared_preload_libraries = 'sys_stat_statements,auto_explain'
sys_stat_statements.max = 5000
sys_stat_statements.track = all    -- 跟踪所有 SQL（含存储过程内）
auto_explain.log_min_duration = 1000   -- 记录超过 1s 的执行计划
log_min_duration_statement = 1000     -- 慢日志阈值

-- Step 2: 重启服务
sys_ctl restart -D /data

-- Step 3: 查询慢 SQL Top N
SELECT 
  query, calls, 
  round(mean_exec_time::numeric, 2) AS avg_ms, 
  round(total_exec_time::numeric, 2) AS total_ms
FROM sys_stat_statements
ORDER BY mean_exec_time DESC LIMIT 20;

-- Step 4: 看具体执行计划
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) 
SELECT * FROM orders WHERE created_at > now() - interval '1 day';
```

**EXPLAIN 关键字段**（与 PG 一致）：
- `cost`：启动成本..总成本（越小越好）
- `rows`：预估返回行数
- `actual rows`：`ANALYZE` 模式下的实际行数
- `Index Scan` / `Seq Scan` / `Bitmap Index Scan`：扫描方式
- `Buffers: shared hit/read/dirtied/written`：I/O 情况

来源：<https://www.cnblogs.com/kingbase/p/17931012.html>、<https://www.cnblogs.com/kingbase/p/15207549.html>、<https://blog.csdn.net/arthemis_14/article/details/134311408>、<https://blog.csdn.net/weixin_27015733/article/details/159950291>

### 5.4 KMonitor 关键指标（Grafana 面板）

| 指标 | 来源 | 含义 |
|---|---|---|
| `kingbase_connections_total` | kingbase_exporter | 活跃连接数 |
| `kingbase_tps` | kingbase_exporter | 每秒事务数 |
| `kingbase_qps` | kingbase_exporter | 每秒查询数 |
| `kingbase_locks_total` | kingbase_exporter | 锁总数 |
| `kingbase_longest_transaction_seconds` | kingbase_exporter | 最长事务时长 |
| `kingbase_replication_lag_seconds` | kingbase_exporter | 主备延迟 |
| `node_cpu_usage` | node_exporter | CPU 使用率 |
| `node_memory_MemAvailable` | node_exporter | 可用内存 |
| `node_disk_free` | node_exporter | 剩余磁盘 |

来源：<https://max.book118.com/html/2022/0811/8103047136004126.shtm>

---

## 6. kingbase.conf 特有配置参数

| 参数 | 作用 | 典型值 | 备注 |
|---|---|---|---|
| `compatible_mode` | SQL 方言兼容模式 | `oracle` / `postgresql` / `mysql` | 核心开关，DB 级 |
| `case_sensitive` | 大小写敏感 | `Y` / `N` | 实例级，initdb 决定 |
| `enable_pg_compatibility` | PG 增强特性 | `on` / `off` | LATERAL JOIN/JSONB 操作符 |
| `pg_compat_version` | PG 兼容版本 | `12` / `13` / `15` | 建议 `12`（覆盖 90%） |
| `sql_mode` | MySQL 兼容 sql_mode | `ONLY_FULL_GROUP_BY,ANSI_QUOTES,STRICT_ALL_TABLES` | MySQL 模式专用 |
| `plsql.compile_checks` | PL/SQL 编译检查 | `true` / `false` | 启用强类型匹配 |
| `check_function_bodies` | 创建函数时验证 | `true` / `false` | 默认 `true` |
| `shared_preload_libraries` | 预加载扩展 | `sys_stat_statements,auto_explain,kdb_database_link` | 多值用逗号 |
| `auto_explain.log_min_duration` | 慢执行计划阈值 | `1000`（毫秒） | -1 禁用 |
| `sys_stat_statements.max` | SQL 跟踪条数 | `5000` | — |
| `sys_stat_statements.track` | 跟踪范围 | `top` / `all` / `none` | `all` 含函数内 SQL |
| `listen_addresses` | 监听地址 | `*` / `0.0.0.0` | 默认 localhost |
| `port` | 监听端口 | `54321` | 默认非 PG 端口 |
| `unix_socket_directories` | Unix 套接字路径 | `/tmp` 或自定义 | 服务器启动时设置 |
| `max_connections` | 最大连接数 | `100` | 集群部署需考虑 VIP 漂移 |
| `kingbase.escape_like` | LIKE 模式转义 | `true` / `false` | — |

来源：<https://blog.csdn.net/arthemis_14/article/details/125221914>、<https://blog.csdn.net/Kingbase_/article/details/122063237>、<https://www.cnblogs.com/kingbase/p/17798312.html>

---

## 7. PL/SQL 兼容层支持矩阵

| Oracle 特性 | KES 支持度 | 备注 |
|---|---|---|
| `DECLARE/BEGIN/EXCEPTION/END` 块 | 完整支持 | — |
| `CREATE OR REPLACE PROCEDURE/FUNCTION` | 完整支持 | — |
| `PACKAGE`（包规范 + 包体） | 部分支持 | 同名函数需重命名；包内过程/函数命名冲突需调整 |
| `PACKAGE` 初始化段 | 部分支持 | — |
| `TRIGGER` 行级/语句级 | 完整支持 | `FOR EACH ROW` 区分 |
| `BEFORE/AFTER/INSTEAD OF` | 完整支持 | — |
| 触发器 `INSERTING/UPDATING/DELETING` | 完整支持 | — |
| `SYS_REFCURSOR` 游标 | 完整支持 | — |
| `%TYPE` / `%ROWTYPE` 属性 | 完整支持 | — |
| `BULK COLLECT INTO` | 完整支持 | — |
| `FORALL` 批量 DML | 部分支持 | — |
| `EXCEPTION` 自定义 | 完整支持 | `WHEN OTHERS THEN` |
| `DBMS_OUTPUT.PUT_LINE` | 完整支持 | — |
| `DBMS_LOB`（SUBSTR/COPY/APPEND） | 完整支持 | 行为一致 |
| `DBMS_SQL` 动态 SQL | 部分支持 | — |
| `DBMS_SCHEDULER` | 部分支持 | — |
| `UTL_FILE` | 部分支持 | 需 `utl_file` 扩展 |
| `DBMS_STATS` 收集统计信息 | 完整支持 | — |
| `MERGE INTO` | 完整支持 | — |
| `CONNECT BY` 递归 | 完整支持 | Oracle 模式 |
| `MODEL` 子句 | 不支持 | 需用 CTE 重构 |
| `PIVOT/UNPIVOT`（行转列） | 部分支持 | — |
| `XMLTYPE` / `XMLQUERY` | 部分支持 | — |
| `JSON_OBJECT_T` / `JSON_ARRAY_T` | 部分支持 | — |
| `DBMS_RANDOM` | 完整支持 | — |
| `SEQUENCE.NEXTVAL` / `CURRVAL` | 完整支持 | — |
| `AUTO_INCREMENT` 字段 | 不支持 | 用 `SERIAL` 或 `IDENTITY` |
| `ROWID` 伪列 | 完整支持 | — |
| `ROWNUM` 伪列 | 完整支持 | — |
| `LEVEL` 伪列 | 完整支持 | — |
| `SYSDATE` / `SYSTIMESTAMP` | 完整支持 | — |
| `NVL/NVL2/DECODE/COALESCE` | 完整支持 | — |
| `DUAL` 虚表 | 完整支持 | — |
| `(+)` 外连接语法 | 完整支持 | Oracle 模式 |
| 加密 PL/SQL 源（`wrap`） | 完整支持 | 不能加密触发器；不加密包规范 |
| 同义词 `SYNONYM` | 完整支持 | `PUBLIC`/`PRIVATE` |
| 物化视图 | 完整支持 | 含刷新机制 |
| 外部表 | 完整支持 | `oracle_fdw`/`kingbase_fdw` |
| 分区表 | 完整支持 | RANGE/LIST/HASH |

来源：<https://blog.csdn.net/arthemis_14/article/details/126428324>、<https://my.oschina.net/u/5489833/blog/5566911>、<https://my.oschina.net/u/5489833/blog/10106250>、<https://www.cnblogs.com/dbaxmg/p/19598544>

---

## 8. KDTS 迁移工具速查

| 源数据库 | 目标 KES | KDTS 支持 |
|---|---|---|
| Oracle 11g/12c/19c | KES V8R6/V9R1 | 完整 |
| MySQL 5.6/5.7/8.0 | KES V8R6/V9R1 | 完整 |
| SQL Server 2008/2012/2016/2019 | KES V8R6/V9R1 | 完整 |
| PostgreSQL 9.x-15 | KES V8R6/V9R1 | 完整 |
| GBase 8a/8s | KES V8R6/V9R1 | 完整 |
| DM 7/8（达梦） | KES V8R6/V9R1 | 完整 |
| KingbaseES V7/V8 → V9 | KES V9R1 | 完整（同构） |

**KDTS-WEB 启动**：
```bash
# 1. 进入安装目录
cd /opt/Kingbase/ES/V8/ClientTools/guitools/KDts/KDTS-WEB

# 2. 启动
bin/startup.sh

# 3. 登录
# http://IP:54523  默认 kingbase / Kb_DI@2019
```

**典型迁移流程**：
1. 源端数据源：填 IP/端口/库/用户/密码 → 测试连接
2. 目标端数据源：填 KES 信息
3. 创建迁移任务：选源端 + 目标端
4. 选择迁移对象：模式/表/视图/存储过程/触发器
5. 选择迁移策略：结构 + 数据 / 仅结构 / 仅数据
6. 启动迁移：实时进度 + 错误日志
7. 验证：行数对比 + 抽样数据校验

**KDTS 端口修改**：`KDTS-WEB/conf/properties` 中 `port` 字段

**典型坑**：
- MySQL → KES 时 `AUTO_INCREMENT` → `SERIAL` 需手工调整
- Oracle 序列 → KES 序列时 `START WITH` 不一致
- Oracle `BLOB/CLOB` → KES `BYTEA/TEXT` 时需用 `lobtype=bytea` 参数

来源：<https://blog.csdn.net/u011436548/article/details/144691427>、<https://www.cnblogs.com/haiyoyo/p/18931618>、<https://blog.csdn.net/yhw1809/article/details/144564087>

---

## 9. 字符串拼接 / 字符集 / 大小写 三大易错点

### 9.1 字符串拼接

| 数据库 | 拼接符 | 备注 |
|---|---|---|
| Oracle | `\|\|` | — |
| KES（Oracle 模式） | `\|\|` 或 `CONCAT()` | 与 Oracle 一致 |
| PostgreSQL | `\|\|` | — |
| KES（PG 模式） | `\|\|` | — |
| MySQL | `CONCAT()`（`\|\|` 在 strict 模式无效） | — |
| KES（MySQL 模式） | `CONCAT()`，受 `sql_mode` 控制 | — |

### 9.2 字符集

| 字符集 | KES 支持 | 应用场景 |
|---|---|---|
| `UTF8` | 完整 | 国际化（推荐） |
| `GBK` | 完整 | 国内传统系统 |
| `GB18030` | 完整 | 国内传统系统扩展 |
| `SQL_ASCII` | 完整 | 兼容性测试，不推荐生产 |

**字符集切换**（需谨慎）：
```bash
# 仅可在 initdb 阶段决定，不能后期改
initdb -USYSTEM -D data --encoding=UTF8 --locale=zh_CN.UTF-8
# 或
initdb -USYSTEM -D data --encoding=GBK
```

**JDBC 端字符集对齐**：
```
?clientEncoding=UTF8
?clientEncoding=GBK
```

### 9.3 大小写敏感

| 模式 | 适用迁移 | 行为 |
|---|---|---|
| `case_sensitive=Y`（默认） | Oracle 迁移 | 不带双引号 → 转大写；带双引号 → 严格按引号 |
| `case_sensitive=N` / `--case-insensitive` | MySQL/SQLServer 迁移 | 不带双引号 → 转小写；带双引号 → 严格按引号 |

**查看当前值**：
```sql
SHOW case_sensitive;   -- on=敏感 / off=不敏感
```

**坑**：KES 改大小写敏感属性必须重 initdb，老数据需 sys_dump/sys_restore 倒一遍。

来源：<https://blog.csdn.net/u013938578/article/details/132146693>、<https://www.cnblogs.com/hxb2016/archive/2004/01/13/14302618.html>

---

## 10. KStudio 性能监控关键指标面板

| 分类 | 指标 | 用途 |
|---|---|---|
| 连接 | 总连接数、活跃连接数、空闲连接数、长事务数 | 排查连接泄漏 |
| SQL | QPS、TPS、慢 SQL 数量、平均响应时间、P95/P99 | 性能基线 |
| 锁 | 等待锁数、死锁数、Lock waits、Lock time | 排查阻塞 |
| IO | 磁盘读/写吞吐、checkpoint 频率、bgwriter 缓冲 | 排查 IO 瓶颈 |
| 内存 | shared_buffers 命中率、work_mem 使用、cache hit ratio | 调内存参数 |
| 复制 | 主备延迟、slot 数、wal_receiver 状态 | 主备集群健康度 |
| 表膨胀 | dead_tuples、last_vacuum、last_autovacuum | 触发 vacuum |

来源：<https://www.kingbase.com.cn/solution/details_659_30349.html>

---

## 11. 运维速查

### 11.1 启停场景

| 场景 | 命令 |
|---|---|
| 单机启动 | `sys_ctl start -D /data -l logfile` |
| 单机停止（默认 smart） | `sys_ctl stop -D /data` |
| 单机快速停止（fast） | `sys_ctl stop -D /data -m fast` |
| 单机立即停止（不推荐） | `sys_ctl stop -D /data -m immediate` |
| 重载配置 | `sys_ctl reload -D /data` |
| 集群启动 | `sys_monitor.sh start` |
| 集群停止 | `sys_monitor.sh stop` |
| 集群重启 | `sys_monitor.sh restart` |
| 集群单节点启 | `sys_monitor.sh startlocal` |
| 集群单节点停 | `sys_monitor.sh stoplocal` |
| 状态查询 | `sys_ctl status -D /data` |
| 主备切换 | `sys_monitor.sh failover` 或 `sys_ctl promote -D /data` |
| 强制 cancel 长事务 | `SELECT sys_cancel_backend(pid);` |
| 强制终止连接 | `SELECT sys_terminate_backend(pid);` |
| 慢 SQL Top 10 | `SELECT * FROM sys_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;` |
| 当前长事务 | `SELECT pid, query, xact_start FROM sys_stat_activity WHERE xact_start IS NOT NULL ORDER BY xact_start;` |
| 锁等待 | `SELECT * FROM sys_locks WHERE NOT granted;` |
| 死锁日志 | `tail -f data/sys_log/sys_log.log` |

### 11.2 备份恢复

```bash
# 逻辑备份（全库）
sys_dump -U system -d testdb -F c -Z 6 -j 4 -f /backup/testdb_$(date +%Y%m%d).dmp

# 逻辑备份（单表）
sys_dump -U system -d testdb -t schema.table_name -f /backup/table.sql

# 逻辑恢复
sys_restore -U system -d newdb -F c /backup/testdb.dmp

# 物理备份
sys_rman backup --backup-mode=full --kingbase-path=/data

# 物理恢复
sys_rman restore --kingbase-path=/data
```

### 11.3 高频配置修改

```bash
# 改端口
echo "port = 54322" >> data/kingbase.conf
sys_ctl reload -D data

# 改最大连接数
echo "max_connections = 200" >> data/kingbase.conf
sys_ctl reload -D data

# 改监听地址
echo "listen_addresses = '*'" >> data/kingbase.conf
sys_ctl reload -D data

# 修改 HBA 允许远程连接
echo "host all all 0.0.0.0/0 md5" >> data/sys_hba.conf
sys_ctl reload -D data

# 切换兼容模式
ALTER DATABASE testdb SET compatible_mode = 'oracle';
ALTER SYSTEM SET compatible_mode = 'oracle';
sys_ctl reload -D data
```

---

## 12. 踩坑高发区

| 坑 | 现象 | 解决 |
|---|---|---|
| Windows 平台默认认证 `scram-sha-256` | JDBC 连接报"Password 认证失败" | 改 `sys_hba.conf` 为 `md5`/`trust` |
| 密码含 `$` 等特殊字符 | ksql 报认证失败 | 用反斜杠转义 `\$` |
| 主备切换 VIP 未漂移 | 应用连接不上 | 确认 `arping` 属主为 `kingbase` 用户 |
| Cluster `node_exporter` 启动失败 | 安全漏洞扫描告警 | `monitor_exporter.sh stop` 关闭 |
| dblink 报 `unsupported for database link` | 新连接失效 | `shared_preload_libraries += 'kdb_database_link'` |
| `requested character too large` | GBK 环境下 `ASCII()` 取中文失败 | 用 `LENGTH()` + 自定义全角转半角函数 |
| 触发器 `WHEN OTHERS THEN` 后未抛错 | 业务异常被吞 | 显式 `RAISE EXCEPTION` |
| 字符串超长报错 | MySQL 兼容模式默认严格 | `SET sql_mode = ''` 关闭严格 |
| 跨模式 `dblink` 报错 | 多字符集环境 | 显式设 `clientEncoding` |
| JDBC 池主备切换后连接数持续上升 | VIP 漂移后老连接未释放 | 客户端加 `tcpKeepAlive=true` + `socketTimeout` |
| PL/SQL `MERGE INTO` 触发器不触发 | Oracle 模式默认禁用 | 设置 `enable_merge_trigger=on` |
| 初始化字符集与模板库不匹配 | `initdb` 失败 | 用 `template0` 或统一 `--encoding` |
| `ALTER TABLE ADD COLUMN` 含默认值时锁表 | 大表长时间等待 | 用 `ALTER TABLE ... ADD COLUMN ... DEFAULT ...` 不重写表（V8R6+ 优化） |
| `sys_stat_activity` 查不到当前应用 | 默认只显示 `datistemplate=false` | 加 `AND datname = current_database()` |
| `sys_dump` 大库超时 | 备份中断 | 加 `-j 4` 并行 + `-Z 6` 压缩 |

---

## 语言指纹

KingbaseES 的"语言层"DNA，浓缩为 8 条精炼特征：

1. **三态兼容模式是方言的灵魂**：`compatible_mode = 'oracle' / 'postgresql' / 'mysql'` 决定语法语义边界，迁移第一件事就是判断目标兼容模式——选错模式 `NVL/DECODE/ROWNUM/CONNECT BY/SYSDATE/DUAL` 全部失效。
2. **命令名前缀的"sys_"是金仓指纹**：`sys_ctl / sys_dump / sys_restore / sys_rman / sys_monitor / sys_hba.conf / sys_stat_statements` 全面替换 PG 的 `pg_` 前缀，但参数/语法/语义几乎完全兼容 PG，是为信创/审计要求做的"去 PG 化"。
3. **大小写敏感的实例级不可变性**：`case_sensitive` 在 `initdb` 阶段决定，事后不可改——这是 KES 最反直觉的"先天属性"，直接决定迁移 Oracle 时的双引号策略。
4. **PL/SQL 兼容深度领先国产库**：`PACKAGE`（部分）、`TRIGGER FOR EACH ROW`、`DBMS_OUTPUT / DBMS_LOB / DBMS_STATS`、`%TYPE/%ROWTYPE`、加密 PL/SQL 源（不能加密触发器）——这些是 KES 区别于 openGauss/GaussDB 的关键。
5. **JDBC 三件套是必考点**：`com.kingbase8.Driver` + `jdbc:kingbase8://` + 主备集群 URL 多 IP 逗号分隔；V8R6+ 的 `READONLYHOSTS + usedispatch + dispatchMode` 是读写分离的标准配方。
6. **错误码两套并存**：标准 SQLSTATE（PG 体系）+ 自定义 `KBxxx` + DCI 数字码（ODBC 层），调优时必须看 `sys_log` 而非只看应用层异常。
7. **字符集与大小写是历史包袱**：UTF8/GBK/GB18030 三选一（initdb 决定），与 MySQL 的 `utf8mb4`、PG 的 `UTF8` 都不完全等价，JDBC 端必须显式 `clientEncoding` 同步。
8. **VIP + repmgr + arping 是集群管理的"金三角"**：`sys_monitor.sh` 起停 + `arping` 漂移 + `repmgr cluster show` 状态——R6 集群的所有"诡异问题"几乎都出在这三者的权限/网络/属主配置上。

---

**总词数统计**：本调研文档共约 580 行，覆盖：命令行工具族速查表（15+ 命令）、KSQL 方言差异表（30 行 KSQL vs Oracle/PG/MySQL）、错误码速查（50+ 条 SQLSTATE + 自定义错误）、JDBC/ODBC 连接串模板（10 种场景）、KStudio/KEMCC 慢 SQL 诊断流程、kingbase.conf 特有参数、PL/SQL 兼容层矩阵、KDTS 迁移工具速查、踩坑高发区表。
