#!/usr/bin/env python3
"""
kingbase_large_table_optimize 数据采集脚本（KingbaseES / 金仓）
----------------------------------------------------------------
只读采集：遍历实例中所有（或指定的）数据库，找出候选大表，
采集其大小、膨胀、DML 活跃度、扫描模式、索引深度等原始数据，
输出为 JSON，供后续人工/Agent 分析并生成优化报告使用。

兼容模式：本脚本默认 KingbaseES 运行在 PostgreSQL 兼容模式，
全部使用 pg_* 目录视图/函数（已在 V9R1C10 实测）。

连接参数优先级（从高到低）：
  1. 命令行参数（--host/--port/--user/--password/--dbname）
  2. 环境变量 PGHOST / PGPORT / PGDBNAME(兼容 PGDATABASE) / PGUSER / PGPASSWORD
  3. 内置默认值 127.0.0.1:5432 / kingbase / kingbase / 123456

安全说明：
- 全程只执行 SELECT 查询，不执行任何 DDL/DML/VACUUM/ANALYZE。
- 密码优先从 PGPASSWORD 环境变量或 --password 参数读取，不写入日志。
- 只连接用户显式指定的 host:port，不发起其他任何网络请求。

依赖：pip install psycopg2-binary --break-system-packages
"""

import argparse
import json
import math
import os
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("缺少依赖，请先执行: pip install psycopg2-binary --break-system-packages",
          file=sys.stderr)
    sys.exit(1)

BLOCK_SIZE = 8192
BTREE_FANOUT_ESTIMATE = 200  # 经验扇出系数，仅用于数量级估算层高

# 内置默认连接参数（金仓）
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5432
DEFAULT_USER = "kingbase"
DEFAULT_PASSWORD = "123456"
DEFAULT_DBNAME = "kingbase"

# 金仓内置系统 schema（大表初筛时排除，可按实例实际情况调整）
KES_SYSTEM_SCHEMAS = [
    "pg_catalog", "information_schema", "pg_toast",
    "sys", "sys_catalog", "sys_hm", "sysmac", "sysaudit",
    "src_restrict", "sys_anon",
]


def resolve_connection(host, port, user, password, dbname):
    """命令行 > 环境变量 > 默认值"""
    host = host or os.environ.get("PGHOST") or DEFAULT_HOST
    port = int(port or os.environ.get("PGPORT") or DEFAULT_PORT)
    user = user or os.environ.get("PGUSER") or DEFAULT_USER
    password = password if password is not None else (
        os.environ.get("PGPASSWORD") or DEFAULT_PASSWORD
    )
    dbname = dbname or os.environ.get("PGDBNAME") or os.environ.get("PGDATABASE") or DEFAULT_DBNAME
    return host, port, user, password, dbname


def connect(host, port, user, password, dbname):
    return psycopg2.connect(
        host=host, port=port, user=user, password=password,
        dbname=dbname, connect_timeout=10,
    )


def fetch_all(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]


def list_databases(conn):
    rows = fetch_all(conn, """
        SELECT datname FROM pg_database
        WHERE datistemplate = false AND datallowconn = true
        ORDER BY datname;
    """)
    return [r["datname"] for r in rows]


def check_kbstattuple(conn):
    """金仓精确膨胀分析扩展（等价 PG 的 pgstattuple）。注意用 pg_extension 而非 sys_extension。"""
    rows = fetch_all(conn, """
        SELECT extname FROM pg_extension WHERE extname = 'kbstattuple';
    """)
    return len(rows) > 0


def find_large_tables(conn, top_n, min_size_gb):
    """大表初筛：TOP N 或总大小超过阈值的业务表（排除金仓系统 schema）"""
    return fetch_all(conn, """
        SELECT
          n.nspname AS schema_name,
          c.relname AS table_name,
          pg_total_relation_size(c.oid) AS total_bytes,
          pg_relation_size(c.oid) AS table_bytes,
          pg_indexes_size(c.oid) AS index_bytes,
          COALESCE(pg_total_relation_size(t.oid), 0)
            - COALESCE(pg_relation_size(t.oid), 0) AS toast_bytes,
          c.reltuples::bigint AS est_rows,
          CASE WHEN p.partrelid IS NOT NULL THEN true ELSE false END AS is_partitioned,
          (SELECT count(*) FROM pg_inherits i WHERE i.inhparent = c.oid) AS partition_count
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_class t ON t.oid = c.reltoastrelid
        LEFT JOIN pg_partitioned_table p ON p.partrelid = c.oid
        WHERE c.relkind IN ('r', 'p')
          AND n.nspname <> ALL (%(exclude)s)
          AND (
            pg_total_relation_size(c.oid) > %(min_bytes)s
            OR c.oid IN (
              SELECT c2.oid FROM pg_class c2
              JOIN pg_namespace n2 ON n2.oid = c2.relnamespace
              WHERE c2.relkind IN ('r','p')
                AND n2.nspname <> ALL (%(exclude)s)
              ORDER BY pg_total_relation_size(c2.oid) DESC
              LIMIT %(top_n)s
            )
          )
        ORDER BY total_bytes DESC;
    """, {"min_bytes": min_size_gb * 1024 ** 3, "top_n": top_n, "exclude": KES_SYSTEM_SCHEMAS})


def get_bloat_stats(conn, schema, table):
    rows = fetch_all(conn, """
        SELECT n_live_tup, n_dead_tup,
          CASE WHEN (n_live_tup + n_dead_tup) = 0 THEN 0
               ELSE round(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 2)
          END AS dead_tup_pct
        FROM pg_stat_user_tables
        WHERE schemaname = %s AND relname = %s;
    """, (schema, table))
    return rows[0] if rows else None


def get_kbstattuple(conn, schema, table):
    """金仓精确膨胀：kbstattuple（全表扫描，只对候选表调用）"""
    qualified = f'"{schema}"."{table}"'
    try:
        rows = fetch_all(conn, "SELECT * FROM kbstattuple(%s);", (qualified,))
        return rows[0] if rows else None
    except Exception:
        conn.rollback()
        try:
            rows = fetch_all(conn, "SELECT * FROM kbstattuple(%s::regclass);", (qualified,))
            return rows[0] if rows else None
        except Exception as e:
            conn.rollback()
            return {"error": str(e)}


def get_dml_activity(conn, schema, table):
    rows = fetch_all(conn, """
        SELECT n_tup_ins, n_tup_upd, n_tup_del, n_tup_hot_upd,
               n_live_tup, n_dead_tup,
               last_vacuum, last_autovacuum, last_analyze, last_autoanalyze
        FROM pg_stat_user_tables
        WHERE schemaname = %s AND relname = %s;
    """, (schema, table))
    return rows[0] if rows else None


def get_scan_pattern(conn, schema, table):
    rows = fetch_all(conn, """
        SELECT seq_scan, seq_tup_read, idx_scan, idx_tup_fetch
        FROM pg_stat_user_tables
        WHERE schemaname = %s AND relname = %s;
    """, (schema, table))
    return rows[0] if rows else None


def get_index_depth(conn, schema, table, has_kbstattuple):
    rows = fetch_all(conn, """
        SELECT
          s.indexrelname,
          s.idx_scan, s.idx_tup_read, s.idx_tup_fetch,
          pg_relation_size(s.indexrelid) AS index_bytes,
          am.amname AS index_type,
          pg_get_indexdef(s.indexrelid) AS index_def,
          s.indexrelid::regclass::text AS index_full_name
        FROM pg_stat_user_indexes s
        JOIN pg_class ic ON ic.oid = s.indexrelid
        JOIN pg_am am ON am.oid = ic.relam
        WHERE s.schemaname = %s AND s.relname = %s
        ORDER BY index_bytes DESC;
    """, (schema, table))
    for r in rows:
        if r["index_type"] == "btree":
            if has_kbstattuple:
                # 金仓 kbstatindex 直接给出精确 B-Tree 层高
                r["exact_btree_level"] = get_kbstatindex(conn, r["index_full_name"])
            if r["index_bytes"] > 0:
                r["estimated_btree_level"] = max(
                    1, math.ceil(math.log(max(r["index_bytes"] / BLOCK_SIZE, 1), BTREE_FANOUT_ESTIMATE))
                )
            else:
                r["estimated_btree_level"] = None
        else:
            r["exact_btree_level"] = None
            r["estimated_btree_level"] = None
    return rows


def get_kbstatindex(conn, index_name):
    try:
        rows = fetch_all(conn, """
            SELECT tree_level, index_size, internal_pages, leaf_pages,
                   avg_leaf_density, leaf_fragmentation
            FROM kbstatindex(%s);
        """, (index_name,))
        return rows[0] if rows else None
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}


def collect_for_database(host, port, user, password, dbname, top_n, min_size_gb):
    conn = connect(host, port, user, password, dbname)
    conn.autocommit = True
    try:
        has_kbstattuple = check_kbstattuple(conn)
        candidates = find_large_tables(conn, top_n, min_size_gb)
        tables = []
        for c in candidates:
            schema, table = c["schema_name"], c["table_name"]
            entry = {
                "schema": schema,
                "table": table,
                "sizes": {
                    "total_bytes": c["total_bytes"],
                    "table_bytes": c["table_bytes"],
                    "index_bytes": c["index_bytes"],
                    "toast_bytes": c["toast_bytes"],
                },
                "est_rows": c["est_rows"],
                "is_partitioned": c["is_partitioned"],
                "partition_count": c["partition_count"],
                "bloat": get_bloat_stats(conn, schema, table),
                "kbstattuple": get_kbstattuple(conn, schema, table) if has_kbstattuple else None,
                "dml_activity": get_dml_activity(conn, schema, table),
                "scan_pattern": get_scan_pattern(conn, schema, table),
                "indexes": get_index_depth(conn, schema, table, has_kbstattuple),
            }
            tables.append(entry)
        return {
            "database": dbname,
            "kbstattuple_available": has_kbstattuple,
            "tables": tables,
        }
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="采集 KingbaseES（金仓）大表原始统计数据（只读）")
    ap.add_argument("--host", default=None, help="默认取 PGHOST 环境变量，再取 127.0.0.1")
    ap.add_argument("--port", type=int, default=None, help="默认取 PGPORT 环境变量，再取 5432")
    ap.add_argument("--user", default=None, help="默认取 PGUSER 环境变量，再取 kingbase")
    ap.add_argument("--password", default=None, help="默认取 PGPASSWORD 环境变量，再取 123456")
    ap.add_argument("--dbname", default=None,
                    help="指定单个数据库；默认取 PGDBNAME/PGDATABASE 环境变量，再取 kingbase；"
                         "均未指定则遍历所有非模板库")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--min-size-gb", type=float, default=10.0)
    ap.add_argument("-o", "--output", default=None, help="输出 JSON 文件路径，默认打印到 stdout")
    args = ap.parse_args()

    host, port, user, password, dbname = resolve_connection(
        args.host, args.port, args.user, args.password, args.dbname
    )

    if not password:
        print("警告: 未提供密码，尝试使用 .pgpass 或信任认证连接", file=sys.stderr)

    admin_conn = connect(host, port, user, password, dbname)
    try:
        dbnames = [dbname] if args.dbname or os.environ.get("PGDBNAME") or os.environ.get("PGDATABASE") else list_databases(admin_conn)
    finally:
        admin_conn.close()

    result = {"instance": {"host": host, "port": port, "user": user}, "databases": []}
    for db in dbnames:
        try:
            result["databases"].append(
                collect_for_database(host, port, user, password, db, args.top_n, args.min_size_gb)
            )
        except Exception as e:
            result["databases"].append({"database": db, "error": str(e)})

    output_json = json.dumps(result, default=str, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"已写入: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
