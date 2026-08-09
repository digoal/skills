#!/usr/bin/env python3
"""
kingbase_security_audit.py
只读 KingbaseES（金仓）安全审计脚本，配合 kingbase-security-audit SKILL.md 使用。

安全约束：
- 全程只读，脚本内不包含任何 DDL/DML 语句。
- 每个连接建立后立即设置 SESSION CHARACTERISTICS AS TRANSACTION READ ONLY。
- 密码优先从环境变量 PGPASSWORD 读取，避免出现在命令行参数 / 进程列表中。
- 任何权限不足的查询会被捕获并记录为"受限项"，不会中断整体审计。

连接参数优先级（与 SKILL.md 连接约定一致）：
  1. 命令行参数（--host/--port/--user/--password/--dbname）
  2. 环境变量 PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDBNAME（PGDATABASE 作为 PGDBNAME 别名）
  3. 缺省值：PGHOST=127.0.0.1 PGPORT=5432 PGDBNAME=kingbase PGUSER=kingbase PGPASSWORD=123456

用法：
  export PGPASSWORD='***'
  python3 kingbase_security_audit.py --out report.json
  # 或显式指定：
  python3 kingbase_security_audit.py --host 127.0.0.1 --port 5432 --user kingbase --dbname kingbase --out report.json

依赖：
  pip install "psycopg[binary]"  # 或 psycopg2-binary（两者均可，自动探测）
"""

import argparse
import datetime
import ipaddress
import json
import os
import sys

try:
    import psycopg2
    import psycopg2.extras
    DRIVER = "psycopg2"
    ROW_FACTORY = None  # psycopg2 通过 cursor_factory=RealDictCursor 实现
    _PSYCOPG2_MODULE = psycopg2
except ImportError:
    try:
        import psycopg as psycopg3  # type: ignore
        from psycopg.rows import dict_row

        # 统一接口：把 psycopg3 映射为 psycopg2 风格调用
        class _Psycopg2Compat:
            extras = None  # psycopg3 无 extras 模块，cursor_factory 由下方包装

        DRIVER = "psycopg3"
        _PSYCOPG2_MODULE = _Psycopg2Compat()
        _PSYCOPG2_MODULE.connect = psycopg3.connect
        ROW_FACTORY = dict_row
    except ImportError:
        print("请先安装依赖: pip install psycopg2-binary  或  pip install 'psycopg[binary]'", file=sys.stderr)
        sys.exit(1)

# ---------------------------------------------------------------------------
# 连接参数解析：命令行 > 环境变量 > 缺省值
# ---------------------------------------------------------------------------
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5432
DEFAULT_DBNAME = "kingbase"
DEFAULT_USER = "kingbase"
DEFAULT_PASSWORD = "123456"

# 系统 schema（金仓除 pg_catalog/information_schema 外还有一套系统 schema，敏感列扫描必须排除）
SYSTEM_SCHEMAS = (
    "pg_catalog", "information_schema", "sys_catalog",
    "sysaudit", "sysmac", "sys_hm", "src_restrict", "anon",
)

PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]

SENSITIVE_COLUMN_PATTERN = (
    "password|pwd|secret|token|key|card|id_card|idcard|phone|mobile|ssn|credential"
)


def is_internal(addr):
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return True  # 无法解析的地址（如 unix socket 本地连接）不计入公网风险
    return any(ip in net for net in PRIVATE_NETS)


def resolve_args(args):
    """命令行 > 环境变量 > 缺省值。"""
    host = args.host or os.environ.get("PGHOST") or DEFAULT_HOST
    port = args.port or int(os.environ.get("PGPORT") or DEFAULT_PORT)
    user = args.user or os.environ.get("PGUSER") or DEFAULT_USER
    dbname = args.dbname or os.environ.get("PGDBNAME") or os.environ.get("PGDATABASE") or DEFAULT_DBNAME
    password = args.password or os.environ.get("PGPASSWORD") or DEFAULT_PASSWORD
    return host, port, user, dbname, password


def connect(host, port, dbname, user, password, connect_timeout=10):
    # _PSYCOPG2_MODULE 在 psycopg2 模式下就是 psycopg2；在 psycopg3 模式下是兼容包装（暴露 .connect）
    conn = _PSYCOPG2_MODULE.connect(
        host=host, port=port, dbname=dbname, user=user, password=password,
        connect_timeout=connect_timeout,
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;")
    return conn


def run_query(conn, sql, restricted_log, label):
    """执行只读查询；权限不足或视图不存在时记录为受限项，不抛出异常中断整体流程。"""
    try:
        kwargs = {}
        if ROW_FACTORY is not None:
            kwargs["row_factory"] = ROW_FACTORY  # psycopg3
        else:
            kwargs["cursor_factory"] = psycopg2.extras.RealDictCursor  # psycopg2
        with conn.cursor(**kwargs) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            # psycopg2 RealDictRow 与 psycopg3 DictRow 都支持 dict()
            return [dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001 - 审计脚本需要兜住任意异常继续执行
        restricted_log.append({"check": label, "reason": str(e).strip()})
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def audit(args):
    host, port, user, dbname, password = resolve_args(args)
    restricted = []
    report = {
        "target": f"{host}:{port}/{dbname}",
        "audit_time": datetime.datetime.now().isoformat(),
        "driver": DRIVER,
    }

    conn = connect(host, port, dbname, user, password)

    # Step 1: 基本信息
    report["version"] = run_query(conn, "SELECT version() AS v;", restricted, "version")
    report["database_mode"] = run_query(
        conn,
        "SELECT setting FROM pg_settings WHERE name = 'database_mode';",
        restricted, "database_mode（金仓兼容模式）",
    )
    report["start_time"] = run_query(conn, "SELECT pg_postmaster_start_time() AS t;", restricted, "start_time")
    report["data_directory"] = run_query(conn, "SHOW data_directory;", restricted, "data_directory")
    report["shared_preload_libraries"] = run_query(
        conn, "SHOW shared_preload_libraries;", restricted, "shared_preload_libraries"
    )

    report["databases"] = run_query(
        conn,
        "SELECT datname, datallowconn, datconnlimit FROM pg_database WHERE datistemplate = false ORDER BY datname;",
        restricted, "database_list",
    )

    report["roles"] = run_query(
        conn,
        """SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb,
                  rolcanlogin, rolreplication, rolbypassrls, rolconnlimit, rolvaliduntil
           FROM pg_roles ORDER BY rolsuper DESC, rolname;""",
        restricted, "roles",
    )

    report["no_password_roles"] = run_query(
        conn,
        "SELECT usename, passwd IS NULL AS no_password, valuntil FROM pg_shadow ORDER BY no_password DESC;",
        restricted, "pg_shadow (需要 superuser 或 pg_monitor 权限)",
    )

    # Step 2.1: sys_hba.conf（PG 兼容视图，不可用时降级 sys_catalog.sys_hba_file_rules）
    report["hba_file"] = run_query(conn, "SHOW hba_file;", restricted, "hba_file")
    report["pg_hba_rules"] = run_query(
        conn,
        """SELECT line_number, type, database, user_name, address, netmask, auth_method, error
           FROM pg_hba_file_rules ORDER BY line_number;""",
        restricted, "pg_hba_file_rules (需要 superuser 或 pg_read_all_settings/pg_monitor 权限)",
    )
    if not report["pg_hba_rules"] and any(
        r.get("check") == "pg_hba_file_rules (需要 superuser 或 pg_read_all_settings/pg_monitor 权限)"
        for r in restricted
    ):
        report["pg_hba_rules"] = run_query(
            conn,
            """SELECT line_number, type, database, user_name, address, netmask, auth_method, error
               FROM sys_catalog.sys_hba_file_rules ORDER BY line_number;""",
            restricted, "sys_catalog.sys_hba_file_rules（降级查询）",
        )

    # Step 2.2: 超级用户使用情况
    report["superuser_connections"] = run_query(
        conn,
        """SELECT a.pid, a.usename, a.datname, a.client_addr::text AS client_addr,
                  a.application_name, a.state, a.backend_start
           FROM pg_stat_activity a
           JOIN pg_roles r ON a.usename = r.rolname
           WHERE r.rolsuper = true AND a.pid <> pg_backend_pid();""",
        restricted, "superuser_connections",
    )
    report["superuser_replication"] = run_query(
        conn,
        "SELECT pid, usename, client_addr::text AS client_addr, application_name, state, sync_state FROM pg_stat_replication;",
        restricted, "pg_stat_replication",
    )

    # Step 3: 金仓安全特性专项
    report["security_extensions"] = run_query(
        conn,
        "SELECT extname, extversion FROM pg_extension WHERE extname IN ('sepapower','sysaudit','sysmac','src_restrict') ORDER BY extname;",
        restricted, "security_extensions",
    )
    # sepapower / sysaudit 可能只出现在 shared_preload_libraries（pg_extension 无记录），需单独确认
    spl_raw = report.get("shared_preload_libraries")
    report["sepapower_in_preload"] = False
    report["sysaudit_in_preload"] = False
    if spl_raw:
        try:
            val = spl_raw[0].get("shared_preload_libraries") if isinstance(spl_raw[0], dict) else str(spl_raw[0])
            spl_text = str(val)
            report["sepapower_in_preload"] = "sepapower" in spl_text
            report["sysaudit_in_preload"] = "sysaudit" in spl_text
        except Exception:  # noqa: BLE001
            pass
    report["sepapower_params"] = run_query(
        conn,
        "SELECT name, setting FROM pg_settings WHERE name LIKE 'sepapower%' OR name = 'sync_security' ORDER BY name;",
        restricted, "sepapower_params",
    )
    report["sao_sso_roles"] = run_query(
        conn,
        "SELECT rolname, rolsuper, rolcreaterole, rolcanlogin FROM pg_roles WHERE rolname IN ('sao','sso') ORDER BY rolname;",
        restricted, "sao_sso_roles（三权分立）",
    )
    report["audit_rules"] = run_query(
        conn, "SELECT * FROM sysaudit.all_audit_rules;", restricted, "sysaudit.all_audit_rules（仅 SAO/SSO 可查）"
    )
    report["mac_tables"] = run_query(
        conn,
        "SELECT * FROM sysmac.sysmac_level;",
        restricted, "sysmac.sysmac_level（强制访问控制，仅 SAO/SSO 可查）",
    )
    report["mac_user_labels"] = run_query(
        conn,
        "SELECT * FROM sysmac.sysmac_user;",
        restricted, "sysmac.sysmac_user（主体标记，仅 SAO/SSO 可查）",
    )
    report["restrict_params"] = run_query(
        conn,
        "SELECT name, setting FROM pg_settings WHERE name LIKE 'restrict%' ORDER BY name;",
        restricted, "restrict_params（src_restrict）",
    )
    report["transparent_encryption_columns"] = run_query(
        conn,
        "SELECT * FROM sys_catalog.kdb_ce_col;",
        restricted, "kdb_ce_col（透明列加密元数据）",
    )
    report["anon_schema"] = run_query(
        conn,
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'anon';",
        restricted, "anon_schema（数据脱敏）",
    )

    # Step 5: 连接来源
    all_conns = run_query(
        conn,
        """SELECT pid, usename, datname, client_addr::text AS client_addr,
                  application_name, backend_start
           FROM pg_stat_activity WHERE client_addr IS NOT NULL;""",
        restricted, "connection_sources",
    )
    report["all_connections"] = all_conns
    report["external_connections"] = [
        c for c in all_conns if c.get("client_addr") and not is_internal(c["client_addr"])
    ]

    # Step 6: 会话与资源
    report["active_sessions"] = run_query(
        conn,
        """SELECT pid, usename, datname, state, wait_event_type, wait_event,
                  (now() - query_start)::text AS duration, left(query, 200) AS query_snippet
           FROM pg_stat_activity WHERE state IS DISTINCT FROM 'idle'
           ORDER BY query_start NULLS LAST;""",
        restricted, "active_sessions",
    )
    report["long_running_queries"] = run_query(
        conn,
        """SELECT pid, usename, datname, (now() - query_start)::text AS duration,
                  left(query, 200) AS query_snippet
           FROM pg_stat_activity
           WHERE state = 'active' AND now() - query_start > interval '1 hour';""",
        restricted, "long_running_queries",
    )
    report["idle_in_transaction"] = run_query(
        conn,
        """SELECT pid, usename, datname, (now() - state_change)::text AS idle_duration,
                  left(query, 200) AS last_query
           FROM pg_stat_activity
           WHERE state = 'idle in transaction' AND now() - state_change > interval '5 minutes'
           ORDER BY state_change;""",
        restricted, "idle_in_transaction",
    )

    # Step 4: 敏感列扫描 —— 逐库连接，排除金仓系统 schema
    sensitive_by_db = {}
    for db in report["databases"]:
        dbname_i = db["datname"]
        try:
            dconn = connect(host, port, dbname_i, user, password)
        except Exception as e:  # noqa: BLE001
            restricted.append({"check": f"connect to database {dbname_i}", "reason": str(e).strip()})
            continue
        rows = run_query(
            dconn,
            f"""SELECT table_schema, table_name, column_name, data_type,
                       col_description(
                         (quote_ident(table_schema) || '.' || quote_ident(table_name))::regclass::oid,
                         ordinal_position
                       ) AS column_comment
                FROM information_schema.columns
                WHERE table_schema NOT IN ({','.join("'" + s + "'" for s in SYSTEM_SCHEMAS)})
                  AND column_name ~* '({SENSITIVE_COLUMN_PATTERN})'
                ORDER BY table_schema, table_name, column_name;""",
            restricted, f"sensitive_columns[{dbname_i}]",
        )
        if rows:
            sensitive_by_db[dbname_i] = rows
        dconn.close()
    report["sensitive_columns_by_database"] = sensitive_by_db

    report["restricted_items"] = restricted
    conn.close()
    return report


def main():
    ap = argparse.ArgumentParser(description="KingbaseES 只读安全审计脚本")
    ap.add_argument("--host", default=None, help="主机（默认取 PGHOST 环境变量，再默认 127.0.0.1）")
    ap.add_argument("--port", type=int, default=None, help="端口（默认取 PGPORT，再默认 5432）")
    ap.add_argument("--dbname", default=None, help="初始连接的维护库（默认取 PGDBNAME/PGDATABASE，再默认 kingbase）")
    ap.add_argument("--user", default=None, help="用户名（默认取 PGUSER，再默认 kingbase）")
    ap.add_argument("--password", default=None, help="不建议在命令行传密码，优先使用环境变量 PGPASSWORD（再默认 123456）")
    ap.add_argument("--out", default=None, help="输出 JSON 文件路径，不指定则打印到 stdout")
    args = ap.parse_args()

    try:
        report = audit(args)
    except Exception as e:  # noqa: BLE001 - 连接失败等致命错误给出清晰提示而非裸堆栈
        print(f"审计中止：连接/执行失败，具体原因：{e}", file=sys.stderr)
        sys.exit(1)

    output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"审计结果已写入: {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
