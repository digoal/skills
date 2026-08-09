# KingbaseES 日志格式与金仓特有消息速查

> 本文内容来源：KingbaseES V9R1C10（V009R001C010，PG 兼容模式，实测于 2026-08）实例实测 + 官方文档。
> 用于日志分析时快速核对：默认参数、文件名模式、消息模式、常见坑。

## 1. 实测默认参数（`SHOW` 确认，PG 兼容模式）

| 参数 | 实测值 | 说明 |
|---|---|---|
| `server_version` | 12.1 | 金仓的 PG 兼容版本号（内核实际为 KES V9R1） |
| `log_destination` | `stderr` | 默认 stderr 文本；可配 `csvlog` 得到结构化 CSV |
| `logging_collector` | `on` | 日志落盘 |
| `log_directory` | `sys_log` | **金仓特有**：相对 `data_directory` 的子目录（PG 是 `log`） |
| `log_filename` | `kingbase-%Y-%m-%d_%H%M%S.log` | **金仓特有**：前缀 `kingbase-`（PG 是 `postgresql-`） |
| `log_line_prefix` | `%m [%p]` | 时间戳含毫秒+时区，如 `2026-08-09 09:00:45.981 UTC [92]` |
| `log_rotation_age` | `1440` (min) | 按天轮转为主 |
| `log_rotation_size` | `10240` (kB) | 10MB |
| `log_timezone` | `UTC`（实测） | 实例间可能不同，分析前必须确认 |
| `log_min_duration_statement` | `-1` | **金仓默认不记慢 SQL**，需要慢查询维度时必须先开 |
| `log_checkpoints` | `off` | **金仓默认关闭** checkpoint 日志 |
| `log_autovacuum_min_duration` | `-1` | **金仓默认不记 autovacuum** |
| `log_connections` / `log_disconnections` | `off` | 连接日志默认关闭 |
| `max_prepared_transactions` | `0`（默认，2PC 未开启） | 金仓默认不支持 PREPARE TRANSACTION |

## 2. 目录/文件名速查

```bash
# 日志目录（默认在数据目录下）
ls -la ${DATA_DIR}/sys_log/
# 典型文件名
kingbase-2026-08-09_083730.log     # 按时间戳轮转
kingbase-2026-08-09_090045.log.gz  # 可能被压缩轮转
# 若找不到 sys_log，用 SHOW log_directory 与 SHOW data_directory 确认
```

日志目录权限通常为 `drwx------ kingbase`，分析时若当前用户无权限，提示用 `sudo -u kingbase` 或有权限的账户。

## 3. 常见消息模式（实测样例）

### 3.1 崩溃与自动恢复（金仓与 PG 同构）

```
2026-08-09 08:50:31.448 UTC [255] LOG:  database system was interrupted; last known up at 2026-08-09 08:42:31 UTC
2026-08-09 08:50:31.969 UTC [255] LOG:  database system was not properly shut down; automatic recovery in progress
2026-08-09 08:50:31.973 UTC [255] LOG:  redo starts at 0/50000D0
2026-08-09 08:50:31.973 UTC [255] LOG:  redo wal segment count 5
2026-08-09 08:50:32.001 UTC [252] LOG:  database system is ready to accept connections
```

- `was interrupted`（异常中断）vs `was shut down`（正常关闭）——连续多次 `was interrupted` 提示主机被 kill/断电/重启或进程被强杀。
- 恢复窗口 = `was interrupted` 到 `database system is ready`。

### 3.2 认证失败（金仓特有：引用 `sys_hba.conf`）

```
2026-08-09 09:03:07.366 UTC [135] FATAL:  password authentication failed for user "sao"
2026-08-09 09:03:07.366 UTC [135] DETAIL:  Connection matched sys_hba.conf line 63: "host    all             all             0.0.0.0/0               scram-sha-256"
```

- 认证配置文件叫 **`sys_hba.conf`**，不是 `pg_hba.conf`。
- 认证失败风暴通常伴随应用侧重连，需关联 `pg_stat_activity` 或连接池日志判断。

### 3.3 客户端常见习惯性问题（金仓特有场景）

```
FATAL:  database "/kingbase:123456@127.0.0.1:5432/kingbase" does not exist
```
- 客户端把 JDBC URL 整体当成库名传入（常见于迁移工具配置错误）。

```
FATAL:  database "postgres" does not exist
```
- 客户端默认连 `postgres` 库，但金仓默认库名是 **`kingbase`**（或安装时指定）。这是习惯性问题，不是故障。

### 3.4 配置变更审计（金仓特有）

```
2026-08-09 09:31:12.061 UTC [263] LOG:  attention:superuser kingbase is modifying sys_stat_statements.track by ALTER SYSTEM SET statement
2026-08-09 09:31:12.082 UTC [89]  LOG:  received SIGHUP, reloading configuration files
2026-08-09 09:31:12.084 UTC [89]  LOG:  parameter "sys_stat_statements.track" changed to "top"
```
- 金仓对超级用户 `ALTER SYSTEM` 有专门提示，属正常行为，但要纳入配置变更维度。

### 3.5 归档未配置（金仓特有）

```
LOG:  config the real archive_command string as soon as possible to archive WAL files
```
- 提示 `archive_command` 仍是占位/未配置真实值，应提醒确认归档链路。

### 3.6 2PC 未开启（金仓特有）

```
ERROR:  2pc are not enabled
ERROR:  the prepared transaction with identifier "gid_xxx" does not exist, you can find prepared view for all identifier
```
- 金仓默认 `max_prepared_transactions` 相关 2PC 未开启，涉及 `PREPARE TRANSACTION` 的 SQL 会失败。

### 3.7 事务块限制（与 PG 一致）

```
ERROR:  ALTER SYSTEM cannot run inside a transaction block
ERROR:  REINDEX CONCURRENTLY cannot run inside a transaction block
```
- 客户端在事务块内执行了不允许的语句，通常来自迁移/初始化脚本。

### 3.8 `sys_stat_statements` 同名对象 schema 差异（金仓特有坑）

```
ERROR:  column "total_exec_time" does not exist at character 190
```
- 金仓中 `sys_stat_statements` 可能同时存在于 `public`（扩展视图，PG12 兼容列）与 `sys_catalog`（内部对象，列结构不同）。
- 报 `column ... does not exist` 时，先用 `SHOW search_path` / `\d sys_stat_statements` 确认解析到了哪个对象。

## 3.9 csvlog 结构化格式（开启后）

- 开启方法：`scripts/enable_csvlog.sql`（psql/ksql）或 `scripts/enable_csvlog.py --enable`（Python）。`ALTER SYSTEM SET log_destination = 'stderr,csvlog'; SELECT pg_reload_conf();` 即可，无需重启；回滚为 `'stderr'`。需要超级用户。
- 开启后日志目录出现与 `.log` 同基名的 `.csv` 文件（如 `kingbase-2026-08-09_090045.csv`），可同时保留文本日志。
- csvlog 每行是标准 CSV，**字段可能含内嵌逗号/引号/换行**（如多行 SQL），必须用 `scripts/parse_csvlog.py`（Python csv 模块）解析，禁止 grep/awk 硬切。
- 列布局与 PG12 兼容（log_time, user_name, database_name, process_id, session_id, session_line_num, command_tag, session_start_time, virtual_transaction_id, transaction_id, error_severity, sql_state_code, message, detail, hint, internal_query, internal_position, context, query, query_pos, location, application_name）；解析器会动态读取文件表头，以实际表头为准。
- `log_time` 形如 `2026-08-09 09:00:45.981 UTC`（带时区名），`query` 字段含完整 SQL（有内嵌换行）。

## 4. 解析要点（金仓 stderr 文本格式）

1. 事件主行：`<timestamp> [<pid>] <LEVEL>:  <message>`，`log_line_prefix = %m [%p]`。
2. 续行归并：`STATEMENT:`/`DETAIL:`/`CONTEXT:`/`HINT:` 与主行**同时间戳同 PID**，必须归并为同一事件再统计；`STATEMENT:` 文本本身还可能跨多行（带缩进），后续无前缀行属于上一个事件。
3. 过滤时间段时优先用时间戳字符串比较（格式统一为 `YYYY-MM-DD HH:MM:SS.mmm`），注意 `log_timezone` 与用户给的本地时间可能不一致。
4. csvlog 场景必须用 `scripts/parse_csvlog.py`（Python `csv` 模块）解析——字段可含内嵌逗号/引号/换行，禁止 grep/awk 硬切；具体列布局与开启方法见上文 **3.9**。

## 5. 官方文档链接

- 错误报告和日志（运行时配置-日志）：https://docs.kingbase.com.cn/cn/KES-V9R1C10/administration/Config_Mgmt/runtime-config-logging
- 数据库管理总览：https://docs.kingbase.com.cn/cn/KES-V9R1C10/introduction （入口，正文为 JS 渲染，`curl` 仅能取到导航壳）
- 说明：docs.kingbase.com.cn 正文需要浏览器渲染；若无法访问，以上实测参数/消息模式可作为可靠依据。
