#!/usr/bin/env python3
"""
pg_security_audit.py
只读 PostgreSQL 安全审计脚本，配合 pg-security-audit SKILL.md 使用。

安全约束：
- 全程只读，脚本内不包含任何 DDL/DML 语句。
- 每个连接建立后立即设置 SESSION CHARACTERISTICS AS TRANSACTION READ ONLY。
- 密码优先从环境变量 PGPASSWORD 读取，避免出现在命令行参数 / 进程列表中。
- 任何权限不足的查询会被捕获并记录为"受限项"，不会中断整体审计。

用法：
  export PGPASSWORD='***'
  python3 pg_security_audit.py --host <host> --port 5432 --user <user> --dbname postgres --out report.json

依赖：
  pip install "psycopg[binary]"  # 或 psycopg2-binary
"""

import argparse
import datetime
import getpass
import ipaddress
import json
import os
import sys

try:
    import psycopg2
    import psycopg2.extras
    DRIVER = "psycopg2"
except ImportError:
    try:
        import psycopg as psycopg2  # type: ignore
        DRIVER = "psycopg"
    except ImportError:
        print("请先安装依赖: pip install psycopg2-binary  或  pip install 'psycopg[binary]'", file=sys.stderr)
        sys.exit(1)

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


def is_internal(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return True  # 无法解析的地址（如 unix socket 本地连接）不计入公网风险
    return any(ip in net for net in PRIVATE_NETS)


def connect(host, port, dbname, user, password, connect_timeout=10):
    conn = psycopg2.connect(
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
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return cur.fetchall()
    except Exception as e:  # noqa: BLE001 - 审计脚本需要兜住任意异常继续执行
        restricted_log.append({"check": label, "reason": str(e).strip()})
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def audit(args):
    password = args.password or os.environ.get("PGPASSWORD") or getpass.getpass("PGPASSWORD: ")
    restricted = []
    report = {
        "target": f"{args.host}:{args.port}/{args.dbname}",
        "audit_time": datetime.datetime.now().isoformat(),
        "driver": DRIVER,
    }

    conn = connect(args.host, args.port, args.dbname, args.user, password)

    # Step 1: 基本信息
    report["version"] = run_query(conn, "SELECT version() AS v;", restricted, "version")
    report["start_time"] = run_query(conn, "SELECT pg_postmaster_start_time() AS t;", restricted, "start_time")
    report["data_directory"] = run_query(conn, "SHOW data_directory;", restricted, "data_directory")
    report["shared_preload_libraries"] = run_query(conn, "SHOW shared_preload_libraries;", restricted, "shared_preload_libraries")

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

    # Step 2.1: pg_hba
    report["pg_hba_rules"] = run_query(
        conn,
        """SELECT line_number, type, database, user_name, address, netmask, auth_method, error
           FROM pg_hba_file_rules ORDER BY line_number;""",
        restricted, "pg_hba_file_rules (需要 superuser 或 pg_read_all_settings/pg_monitor 权限)",
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

    # Step 4: 连接来源
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

    # Step 5: 会话与资源
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

    # Step 3: 敏感列扫描 —— 逐库连接
    sensitive_by_db = {}
    for db in report["databases"]:
        dbname = db["datname"]
        try:
            dconn = connect(args.host, args.port, dbname, args.user, password)
        except Exception as e:  # noqa: BLE001
            restricted.append({"check": f"connect to database {dbname}", "reason": str(e).strip()})
            continue
        rows = run_query(
            dconn,
            f"""SELECT table_schema, table_name, column_name, data_type,
                       col_description(
                         (quote_ident(table_schema) || '.' || quote_ident(table_name))::regclass::oid,
                         ordinal_position
                       ) AS column_comment
                FROM information_schema.columns
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                  AND column_name ~* '({SENSITIVE_COLUMN_PATTERN})'
                ORDER BY table_schema, table_name, column_name;""",
            restricted, f"sensitive_columns[{dbname}]",
        )
        if rows:
            sensitive_by_db[dbname] = rows
        dconn.close()
    report["sensitive_columns_by_database"] = sensitive_by_db

    report["restricted_items"] = restricted
    conn.close()
    return report


def main():
    ap = argparse.ArgumentParser(description="PostgreSQL 只读安全审计脚本")
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=5432)
    ap.add_argument("--dbname", default="postgres", help="初始连接的维护库")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", default=None, help="不建议在命令行传密码，优先使用环境变量 PGPASSWORD")
    ap.add_argument("--out", default=None, help="输出 JSON 文件路径，不指定则打印到 stdout")
    args = ap.parse_args()

    report = audit(args)
    output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"审计结果已写入: {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
