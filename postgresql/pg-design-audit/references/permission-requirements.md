# 权限需求说明

pg-design-audit 遵循最小权限原则，所有检查均为只读查询。以普通业务账号（非超级用户）执行时，
部分系统视图可能受行级安全或权限限制，导致结果不完整。执行前建议确认以下权限，
若不满足，在报告中标记"权限不足，需授予 xxx 权限"，而不是静默跳过。

## 基础权限（几乎所有检查项依赖）

- 对目标数据库的 `CONNECT` 权限
- 对 `pg_catalog`、`information_schema` 中系统目录视图的 `SELECT` 权限（通常默认对所有角色开放）

## 分检查项权限

| 检查项 | 依赖视图/函数 | 权限要求 |
|---|---|---|
| 大表体积统计 (04) | `pg_total_relation_size()` | 需要对应表的 `SELECT` 权限或角色具备 `pg_monitor` / `pg_read_all_stats` |
| 索引使用统计 (05) | `pg_stat_user_indexes` | 普通角色可见自己有权限的对象；建议授予 `pg_monitor` 角色以获得完整视图 |
| 数据校验和 (07) | `SHOW data_checksums` | 无特殊权限要求，所有角色可执行 |
| public 模式建表权限检查 (07) | `has_schema_privilege()` | 无特殊权限要求 |
| 字段注释/对象注释 (03) | `obj_description()` / `col_description()` | 无特殊权限要求 |

## 推荐授权（用于审计场景，只读、不可写）

```sql
-- 在被扫描实例上，为审计账号授予只读统计权限（PostgreSQL 10+）
GRANT pg_monitor TO audit_readonly_user;
GRANT CONNECT ON DATABASE <dbname> TO audit_readonly_user;
GRANT USAGE ON SCHEMA public TO audit_readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO audit_readonly_user;
```

> `pg_monitor` 是 PostgreSQL 内置角色，仅授予统计信息只读能力，不包含任何 DDL/DML 权限，
> 符合本技能"仅只读查询系统表，严禁执行 DDL 或 DML"的执行约束。

## 若权限不足时的处理方式

1. 该检查项对应的 SQL 会返回空结果集或报错（如 `permission denied for table pg_stat_activity`）。
2. `run_audit.sh` 会将 stderr 单独写入 `<query>.err` 文件，不会中断整体扫描（`ON_ERROR_STOP=0`）。
3. Agent 在汇总报告时，若发现 `.err` 文件非空且包含 `permission denied`，须在报告"权限不足"章节
   明确列出：数据库名、检查项、建议授予的权限（参考上表），而不是省略该检查项或假装已通过。
