# 整改命令参考 (references/remediation.md)

本文件汇总 kingbase-security-audit 常见高危/警告发现对应的修复命令，供报告"修复建议"列引用。所有命令均为**修改配置后需要人工审核并在运维窗口执行**，本技能本身绝不代为执行。

KingbaseES 命令/文件命名与 PG 的对应关系：`pg_ctl` → `sys_ctl`、`pg_hba.conf` → `sys_hba.conf`、`postgresql.conf` → `kingbase.conf`、`pg_reload_conf()` → `sys_reload_conf()`（`pg_reload_conf()` 在 PG 兼容模式下通常也可用）。连接协议与 PG 完全兼容，psql 可直连。

## 1. sys_hba.conf 相关

### 1.1 trust 认证（高危）
```
# 修改前（危险示例）
host  all  all  0.0.0.0/0  trust

# 修改后
host  all  all  10.0.0.0/8  scram-sha-256
```
修改后重新加载配置（不中断连接）：
```bash
sys_ctl reload -D <data_directory>
# 或
psql -c "SELECT pg_reload_conf();"   # 金仓 PG 兼容模式可用；如报错则用 sys_reload_conf()
```

### 1.2 公网暴露 (0.0.0.0/0 / ::/0)
- 收敛为具体的内网段或跳板机/应用服务器固定 IP。
- 如确需公网访问，务必叠加：`scram-sha-256` 认证 + 防火墙白名单 + SSL 强制（`hostssl` 而非 `host`）。

### 1.3 replication 伪数据库准入过宽
```
# 仅允许备库/灾备节点的固定 IP 使用复制协议连接
host  replication  repl_user  <备库固定IP>/32  scram-sha-256
```

## 2. 超级用户治理

### 2.1 应用使用超级用户连接（高危）
- 为业务应用创建专用的最小权限角色，禁止业务连接串使用 superuser：
```sql
-- 示例（需DBA在运维窗口执行，非本审计脚本执行）
CREATE ROLE app_readonly LOGIN PASSWORD '***' NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE appdb TO app_readonly;
GRANT USAGE ON SCHEMA public TO app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_readonly;
```
- 逐步将应用连接串切换到新角色，观察无异常后收回原超级用户在 sys_hba.conf 中对应库的准入。

### 2.2 密码永不过期
```sql
ALTER ROLE <rolename> VALID UNTIL '2026-12-31';
```
建议纳入定期轮换脚本，结合密钥管理系统（Vault/KMS）统一管理有效期。

### 2.3 空密码但允许登录
- 确认该角色的实际认证方式（结合 sys_hba.conf，可能是 peer/ident/cert 认证，属正常设计）；
- 若确为遗留问题，补充密码：
```sql
ALTER ROLE <rolename> PASSWORD '***';
```

## 3. 金仓安全特性加固

### 3.1 启用数据库审计（sysaudit，高危发现的通用整改项）
金仓数据库审计需要先加载扩展，在 `kingbase.conf` 中修改 `shared_preload_libraries` 加入 `sysaudit` 并重启实例，然后由审计管理员（SSO）创建审计规则：
```bash
# kingbase.conf
shared_preload_libraries = '..., sysaudit, ...'
# 重启实例（需运维窗口）
sys_ctl restart -D <data_directory>
```
```sql
-- 由 SSO 审计管理员执行，创建审计规则（示例：审计 sysuser 用户的所有语句）
-- 注意：sysaudit 的 CREATE AUDIT 具体语法随版本演进，以官方《数据库审计》手册为准：
-- https://docs.kingbase.com.cn/cn/KES-V9R1C10/safe/database-audit
CREATE AUDIT ALL STATEMENTS BY sysuser;
-- 查看审计规则
SELECT * FROM sysaudit.all_audit_rules;   -- 仅 SAO/SSO 可查
-- 查看审计规则（函数方式）
SELECT * FROM sysaudit.show_audit_rules();
```
审计日志文件位于 `<data_directory>/sys_log/sys_audit*.log`（具体由 `log_destination`/`logging_collector` 与审计参数决定），应纳入独立归档与防篡改保护。

### 3.2 启用三权分立（sepapower，满足等保分权要求）
```bash
# kingbase.conf
shared_preload_libraries = '..., sepapower, ...'
# 重启后按金仓分权手册创建 SAO（安全管理员）/SSO（审计管理员）角色并授权
```
典型角色（金仓初始化或分权配置后自动创建）：
- `sao`：安全管理员，负责用户/权限管理
- `sso`：审计管理员，负责审计规则与审计日志
启用后，超级用户将无法再直接读取审计数据（`sysaudit.all_audit_rules` 等报 permission denied），属预期行为。

### 3.3 启用强制访问控制（sysmac + src_restrict）
```bash
# kingbase.conf
shared_preload_libraries = '..., src_restrict, ...'
# 涉及涉密场景时启用标签访问控制（sysmac 扩展）
CREATE EXTENSION IF NOT EXISTS sysmac;
```
启用后按金仓《标记与强制访问控制》手册配置标签、级别与主体/客体标记（`sysmac.sysmac_level`/`sysmac.sysmac_user` 等表由 SAO 角色管理）。

### 3.4 透明列加密（kdb_ce_col）
```sql
-- 对敏感列启用透明加密（需先配置主密钥，具体见金仓《透明存储加密》手册）
-- 示例：CREATE TABLE ... COLUMN_ENCRYPTED ...（语法随版本演进，以官方手册为准）
-- 查询已加密列
SELECT * FROM sys_catalog.kdb_ce_col;
```
透明加密对应用透明，是敏感列明文风险的首选整改方案之一。

## 4. 敏感数据加密

- 明文存储的敏感列优先采用金仓**透明列加密**（kdb_ce_col）或应用层加密：
- 更推荐的长期方案：应用层加密/脱敏 + 数据库仅存储密文或哈希，密钥由独立 KMS 管理，不与数据库同机存放。
- 对手机号、身份证号等，若业务只需校验而非还原，优先使用单向哈希（如 `sha256` + 盐）而非可逆加密。
- 若已部署 `anon` 数据脱敏扩展，应对敏感列配置脱敏规则（`CREATE MASKING ...`，语法以金仓《数据脱敏》手册为准）。

## 5. 网络与连接治理

- 非内网来源连接：结合防火墙/安全组收敛只允许应用服务器网段访问数据库端口。
- 建议数据库不直接暴露公网，通过 VPN/专线/堡垒机访问。
- 对确需公网访问的场景，强制 `hostssl` + 客户端证书双向认证。

## 6. 长事务与异常会话治理

### 6.1 idle in transaction 过长
- 应用层排查连接池是否正确提交/回滚事务，检查是否有未关闭的显式事务。
- 数据库层可设置超时兜底（需评估对正常长事务业务的影响）：
```sql
ALTER SYSTEM SET idle_in_transaction_session_timeout = '10min';
SELECT pg_reload_conf();
```

### 6.2 长时间运行查询
```sql
-- 先确认业务合理性，再考虑终止（终止操作需业务方确认，非本审计脚本执行）
SELECT pg_cancel_backend(<pid>);   -- 温和取消
SELECT pg_terminate_backend(<pid>); -- 强制终止连接
```

## 7. 权限授予（用于消除"受限项"）

若审计账号权限不足导致部分检查无法执行，建议为专用审计账号授予（由 DBA 在运维窗口执行）：
```sql
GRANT pg_monitor TO audit_user;           -- PG 兼容模式内置只读监控角色（金仓提供同义 sys_monitor）
GRANT pg_read_all_settings TO audit_user; -- 读取所有配置
GRANT pg_read_all_stats TO audit_user;    -- 读取所有统计视图明细
```
`pg_monitor` 是后两者的合集，通常授予一个即可满足本技能大部分只读检查需求，且不具备任何写权限。
> 注意：三权分立开启后，`sysaudit.all_audit_rules` 与 `sysmac.*` 的访问权**不属于** pg_monitor 范畴，只能通过 SAO/SSO 角色获得。
