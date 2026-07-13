# 整改命令参考 (references/remediation.md)

本文件汇总 pg-security-audit 常见高危/警告发现对应的修复命令，供报告"修复建议"列引用。所有命令均为**修改配置后需要人工审核并在运维窗口执行**，本技能本身绝不代为执行。

## 1. pg_hba.conf 相关

### 1.1 trust 认证（高危）
```
# 修改前（危险示例）
host  all  all  0.0.0.0/0  trust

# 修改后
host  all  all  10.0.0.0/8  scram-sha-256
```
修改后重新加载配置（不中断连接）：
```bash
pg_ctl reload -D <data_directory>
# 或
psql -c "SELECT pg_reload_conf();"
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
- 逐步将应用连接串切换到新角色，观察无异常后收回原超级用户在 pg_hba.conf 中对应库的准入。

### 2.2 密码永不过期
```sql
ALTER ROLE <rolename> VALID UNTIL '2026-12-31';
```
建议纳入定期轮换脚本，结合密钥管理系统（Vault/KMS）统一管理有效期。

### 2.3 空密码但允许登录
- 确认该角色的实际认证方式（结合 pg_hba.conf，可能是 peer/ident/cert 认证，属正常设计）；
- 若确为遗留问题，补充密码：
```sql
ALTER ROLE <rolename> PASSWORD '***';
```

## 3. 敏感数据加密

- 明文存储的敏感列建议采用 `pgcrypto` 扩展做列级加密（需评估性能与查询模式影响）：
```sql
-- 需DBA评估后在维护窗口执行，非本审计脚本执行
CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- 示例：写入时加密
INSERT INTO users(phone_encrypted) VALUES (pgp_sym_encrypt('13800000000', '<key>'));
```
- 更推荐的长期方案：应用层加密/脱敏 + 数据库仅存储密文或哈希，密钥由独立 KMS 管理，不与数据库同机存放。
- 对手机号、身份证号等，若业务只需校验而非还原，优先使用单向哈希（如 `sha256` + 盐）而非可逆加密。

## 4. 网络与连接治理

- 非内网来源连接：结合防火墙/安全组收敛只允许应用服务器网段访问数据库端口。
- 建议数据库不直接暴露公网，通过 VPN/专线/堡垒机访问。
- 对确需公网访问的场景，强制 `hostssl` + 客户端证书双向认证。

## 5. 长事务与异常会话治理

### 5.1 idle in transaction 过长
- 应用层排查连接池是否正确提交/回滚事务，检查是否有未关闭的显式事务。
- 数据库层可设置超时兜底（需评估对正常长事务业务的影响）：
```sql
ALTER SYSTEM SET idle_in_transaction_session_timeout = '10min';
SELECT pg_reload_conf();
```

### 5.2 长时间运行查询
```sql
-- 先确认业务合理性，再考虑终止（终止操作需业务方确认，非本审计脚本执行）
SELECT pg_cancel_backend(<pid>);   -- 温和取消
SELECT pg_terminate_backend(<pid>); -- 强制终止连接
```

## 6. 权限授予（用于消除"受限项"）

若审计账号权限不足导致部分检查无法执行，建议为专用审计账号授予（由 DBA 在运维窗口执行）：
```sql
GRANT pg_monitor TO audit_user;          -- PG10+ 内置只读监控角色，覆盖pg_stat_*/pg_hba_file_rules等
GRANT pg_read_all_settings TO audit_user; -- 读取所有配置
GRANT pg_read_all_stats TO audit_user;    -- 读取所有统计视图明细
```
`pg_monitor` 是这三者的合集，通常授予一个即可满足本技能全部只读检查需求，且不具备任何写权限。
