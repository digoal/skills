---
name: pg-security-audit
description: "PostgreSQL 数据库安全审计专家技能。给定一个 PostgreSQL 实例的连接信息（主机、端口、数据库、用户名、密码），对该实例执行全面只读安全评估，覆盖 pg_hba.conf 认证规则、超级用户与角色权限、密码策略、敏感数据列（password/secret/token/key/card/id_card/phone等）明文风险、非内网来源连接、长事务与 idle in transaction 会话、异常进程等，最终输出高危/警告分级的中文 Markdown 审计报告。触发条件：用户提到「PostgreSQL 安全审计」「PG 安全检查」「数据库安全评估」「审计一下这个PG实例」「pg_hba 检查」「有没有 trust 认证」「数据库权限审计」「敏感数据加密检查」「有没有超级用户风险」「帮我看看这个库安不安全」「渗透测试前的数据库基线检查」，或提供了 PostgreSQL 连接信息并希望做安全体检/合规检查/等保测评相关的数据库项时，都应使用本技能。即使用户只说「帮我查一下这个库有没有安全问题」并给出了连接串，也应使用本技能。本技能严格只读，绝不执行任何 DDL/DML 写操作。"
tags: [PostgreSQL, 安全风险, 安全评估]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# PostgreSQL 安全审计专家 (pg-security-audit)

对一个 PostgreSQL 实例执行端到端、只读的安全基线审计，产出一份可直接用于整改跟踪的中文安全评估报告。适用场景：上线前安全体检、等保/合规测评、渗透测试前基线摸底、日常安全巡检。

## 核心原则（不可违反）

1. **绝对只读**：整个审计过程中，禁止执行任何 `CREATE`、`ALTER`、`DROP`、`INSERT`、`UPDATE`、`DELETE`、`GRANT`、`REVOKE`、`VACUUM FULL` 等写操作或 DDL/DML。所有查询限定在系统目录（`pg_catalog`）、标准视图（`information_schema`）和统计信息视图（`pg_stat_*`）范围内。
2. **会话级防护**：每条连接建立后，第一时间执行 `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;` 作为安全兜底，即使误触发写操作也会被数据库拒绝。
3. **最小权限暴露**：审计过程中读到的密码哈希、密钥等内容禁止在报告中明文展示，只报告"是否存在/是否为空/是否明文存储"的判断结论，不展示具体敏感值。
4. **权限不足不阻断**：任何系统视图查询失败（权限不足），记录为"受限项"，在报告中明确说明并给出应授予的最小权限，继续执行后续检查，不中断整个审计流程。

## 前置要求

- 可用的 PostgreSQL 客户端：`psql` 或 Python `psycopg2`/`psycopg[binary]`（二选一均可，脚本默认使用 psycopg2）。
- 连接信息：主机、端口、数据库名（通常为 `postgres` 或维护库）、用户名、密码。
- 建议使用的审计账号至少具备 `pg_monitor`（PG10+ 内置角色）权限以获得完整的 `pg_stat_activity`/`pg_stat_replication` 查询文本和 `pg_hba_file_rules` 可见性；若只有普通只读账号，权限受限项会被如实记录而非跳过。
- 网络需能连通目标实例的 `host:port`。

## 工作流程

### Step 0：建立连接与安全兜底

1. 使用提供的连接信息建立连接（优先连到 `postgres` 库或用户指定的维护库）。
2. 连接后立即执行：
   ```sql
   SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
   ```
3. 记录连接是否成功；若失败（认证失败/网络不通/库不存在），报告中止并说明具体错误原因，不进行后续步骤。

### Step 1：连接与权限信息收集

```sql
-- 版本
SELECT version();
-- 启动时间
SELECT pg_postmaster_start_time();
-- 数据目录
SHOW data_directory;
-- 预加载库
SHOW shared_preload_libraries;
-- 当前连接数上限
SHOW max_connections;
```

列出所有非模板数据库：
```sql
SELECT datname, datallowconn, datconnlimit
FROM pg_database
WHERE datistemplate = false
ORDER BY datname;
```

角色与属性（集群级，仅需查一次）：
```sql
SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb,
       rolcanlogin, rolreplication, rolbypassrls, rolconnlimit,
       rolvaliduntil
FROM pg_roles
ORDER BY rolsuper DESC, rolname;
```

密码是否为空（需要 superuser 或 pg_monitor 权限访问 `pg_shadow`，否则记为受限项）：
```sql
SELECT usename, passwd IS NULL AS no_password, valuntil
FROM pg_shadow
ORDER BY no_password DESC;
```
> 若无权限访问 `pg_shadow`，报告中标注："受限项：无法判断是否存在空密码角色，需要 superuser 权限或将审计账号加入 pg_monitor 角色组"。

### Step 2：核心安全基线检查（必须包含）

**2.1 pg_hba.conf 审查**（需要 superuser 或 pg_read_all_settings/pg_monitor 权限）：
```sql
SELECT line_number, type, database, user_name, address, netmask, auth_method, error
FROM pg_hba_file_rules
ORDER BY line_number;
```
分析并标记：
- `auth_method = 'trust'` → **高危（Critical）**：任意来源无需密码即可登录。
- `address` 为 `0.0.0.0/0`、`::/0`，或 `type = 'host'` 且未限定地址 → **高危**：非内网暴露面。
- `database` 数组包含 `replication` 且来源非明确的复制专用地址段 → **高危/警告**：复制通道可能被滥用做数据全量拉取。
- 若查询失败（权限不足）→ 记为受限项，提示需授予 `pg_monitor` 角色或 superuser。

**2.2 超级用户审查**：
```sql
-- 所有超级用户
SELECT rolname FROM pg_roles WHERE rolsuper = true;

-- 当前正在使用超级用户账号建立应用连接的会话
SELECT a.pid, a.usename, a.datname, a.client_addr, a.application_name,
       a.state, a.backend_start
FROM pg_stat_activity a
JOIN pg_roles r ON a.usename = r.rolname
WHERE r.rolsuper = true
  AND a.pid <> pg_backend_pid();

-- 使用超级用户的流复制连接
SELECT pid, usename, client_addr, application_name, state, sync_state
FROM pg_stat_replication;
```
标记：应用程序（`application_name` 非 `psql`/运维工具，或 `client_addr` 非运维跳板机）使用超级用户账号连接 → **高危**：权限未做最小化拆分。

**2.3 密码策略**：
结合 Step 1 的 `pg_shadow.no_password` 和 `pg_roles.rolvaliduntil`：
- `no_password = true` 且 `rolcanlogin = true` → **高危**：允许登录但无密码（可能走 peer/trust/cert 认证，需结合 pg_hba 交叉验证是否合理）。
- `rolvaliduntil IS NULL` 且该角色非系统内置角色 → **警告**：密码永不过期，建议纳入定期轮换策略。

### Step 3：敏感数据加密检查

对 Step 1 中列出的**每一个**非模板数据库，逐一连接后执行：
```sql
SELECT table_schema, table_name, column_name, data_type,
       col_description(
         (quote_ident(table_schema) || '.' || quote_ident(table_name))::regclass::oid,
         ordinal_position
       ) AS column_comment
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
  AND column_name ~* '(password|pwd|secret|token|key|card|id_card|idcard|phone|mobile|ssn|credential)'
ORDER BY table_schema, table_name, column_name;
```
对每个命中列：
- 若 `data_type` 为 `bytea` 或列注释包含"加密/hash/encrypted/密文"等字样 → 视为已做保护，标注"疑似已加密，建议人工确认"。
- 若 `data_type` 为 `text`/`varchar`/`character varying` 且无相关注释 → **警告**：疑似明文存储敏感信息，需人工抽样确认并考虑列级加密（pgcrypto）或应用层加密。
- 本步骤只做**推断**，报告中必须明确注明"以下为基于列名/类型/注释的推断结果，需人工抽样验证实际存储内容，审计过程不读取任何具体行数据"。

### Step 4：来源地址与网络风险

```sql
SELECT client_addr, usename, datname, application_name, count(*) AS conn_count
FROM pg_stat_activity
WHERE client_addr IS NOT NULL
GROUP BY client_addr, usename, datname, application_name
ORDER BY conn_count DESC;
```

在应用层（不在 SQL 中）用以下私网段判断是否为内网地址：`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`、`127.0.0.0/8`。也可直接用 SQL 完成分类：
```sql
SELECT pid, usename, datname, client_addr, application_name, backend_start
FROM pg_stat_activity
WHERE client_addr IS NOT NULL
  AND NOT (
    client_addr <<= '10.0.0.0/8'::inet OR
    client_addr <<= '172.16.0.0/12'::inet OR
    client_addr <<= '192.168.0.0/16'::inet OR
    client_addr <<= '127.0.0.0/8'::inet
  );
```
统计非内网连接总数，逐条列出用户、数据库、应用名 → 非内网来源且非明确的公网 SaaS/云服务出口 → **警告**（若同时命中 trust 认证或超级用户，则升级为**高危**）。

### Step 5：异常进程与资源检查

```sql
-- 所有活跃（非idle）会话概览
SELECT pid, usename, datname, state, wait_event_type, wait_event,
       now() - query_start AS duration, left(query, 200) AS query_snippet
FROM pg_stat_activity
WHERE state IS DISTINCT FROM 'idle'
ORDER BY duration DESC NULLS LAST;

-- 运行超过 1 小时的查询
SELECT pid, usename, datname, state, now() - query_start AS duration,
       left(query, 200) AS query_snippet
FROM pg_stat_activity
WHERE state = 'active'
  AND now() - query_start > interval '1 hour';

-- idle in transaction 超过 5 分钟的会话（连接池/事务泄漏常见根因）
SELECT pid, usename, datname, now() - state_change AS idle_duration,
       left(query, 200) AS last_query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND now() - state_change > interval '5 minutes'
ORDER BY idle_duration DESC;
```
PostgreSQL 系统目录不直接暴露单进程 CPU/内存占用；若审计环境具备操作系统访问权限，可用上述查询得到的 `pid` 交叉执行 `ps -o pid,%cpu,%mem,etime,cmd -p <pid>` 辅助判断资源异常进程；若没有 OS 访问权限，此项在报告中注明"受限项：无 OS 层访问权限，无法核实进程级 CPU/内存占用，建议结合 pg_stat_statements 扩展的 total_exec_time/calls 做查询级资源画像"。

## 输出格式

最终报告为中文 Markdown，结构固定如下：

```markdown
# PostgreSQL 安全审计报告

- 审计目标：<host>:<port>/<database>
- 审计时间：<执行时间>
- 数据库版本：<version()>

## 一、高危发现（Critical）
| 序号 | 风险项 | 具体位置/证据 | 风险说明 | 修复建议（命令） |
|---|---|---|---|---|
| 1 | pg_hba trust 认证 | pg_hba_file_rules 第 N 行 | 任意来源免密登录 | 修改 pg_hba.conf 第 N 行认证方式为 scram-sha-256 后 `pg_ctl reload` |

## 二、警告发现（Warning）
| 序号 | 风险项 | 具体位置/证据 | 加固建议 |
|---|---|---|---|

## 三、受限项说明
| 检查项 | 受限原因 | 需要授予的权限 |
|---|---|---|

## 四、摘要统计
| 指标 | 数值 |
|---|---|
| 数据库总数 | |
| 角色总数 | |
| 超级用户数 | |
| 当前活跃连接数 | |
| 非内网来源连接数 | |
| pg_hba 高危规则数 | |
| 敏感列疑似明文数 | |

## 五、整改优先级与持续监控建议
1. （按风险等级+修复成本排序的整改清单）
...
后续建议：定期复跑本审计（如每周一次）、开启 pgaudit 扩展记录敏感操作、对 pg_hba.conf 变更纳入代码评审。
```

高危判定的具体命令建议参见 `references/remediation.md`；批量执行全部检查可参考 `scripts/pg_security_audit.py`（Python + psycopg2）与 `scripts/queries.sql`（纯 SQL 版本，适合直接用 psql 执行）。

## Pitfalls & Solutions

| 坑点 | 现象 | 解决方案 |
|---|---|---|
| `pg_hba_file_rules` 查询返回空或报错 | 普通用户无权限查看该视图完整内容 | 提示需要 superuser 或 `pg_monitor`/`pg_read_all_settings` 角色，报告中记为受限项而非当作"无风险" |
| `pg_shadow` 无法访问 | 权限不足 | 同上，记为受限项，不影响其他检查继续执行 |
| 敏感列扫描误报 | 列名含 `key` 但实际是业务主键（如 `primary_key_id`），并非敏感信息 | 报告中注明"基于列名推断，需人工确认"，不做绝对化结论 |
| 大量数据库导致 Step 3 耗时长 | 逐库连接扫描 information_schema 较慢 | 可先用 Step 1 的数据库列表做优先级排序，先扫业务库、后扫模板/系统库，或允许用户指定重点库范围 |
| 连接信息中密码明文出现在命令行 | 存在被 `ps`/shell history 记录的风险 | 优先使用环境变量传递密码（如 `PGPASSWORD`）或 psycopg2 连接参数，不在日志中回显密码 |
| 误判 idle in transaction 阈值 | 5 分钟阈值对所有业务不通用 | 阈值可作为默认值，若用户说明业务本身有长事务需求，可在报告中调整判定标准并注明依据 |

## 注意事项

- **绝不执行任何写操作**：包括看似无害的 `ANALYZE`、`VACUUM`（非 FULL）也应避免，除非用户明确单独要求且这不属于本技能范畴。
- **不在报告中回显密码哈希、密钥原文等敏感数值**，只报告风险结论。
- 若目标实例是生产库，建议提示用户在业务低峰期执行，虽然本审计只读且成本极低，但 `pg_stat_activity`/`information_schema` 全表扫描在超大规模多库场景下仍可能产生轻微额外负载。
- 报告语言固定为中文。
- 若某类检查因版本过低（如 PG 9.x 无 `pg_hba_file_rules`，该视图为 PG10+ 引入）而无法执行，需在报告受限项中说明版本原因而非报错终止。
