#!/usr/bin/env python3
"""
pg_large_table_optimize 数据采集脚本
------------------------------------
只读采集：遍历实例中所有（或指定的）数据库，找出候选大表，
采集其大小、膨胀、DML 活跃度、扫描模式、索引深度等原始数据，
输出为 JSON，供后续人工/Agent 分析并生成优化报告使用。

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


def check_pgstattuple(conn):
    rows = fetch_all(conn, """
        SELECT extname FROM pg_extension WHERE extname = 'pgstattuple';
    """)
    return len(rows) > 0


def find_large_tables(conn, top_n, min_size_gb):
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
          AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND (
            pg_total_relation_size(c.oid) > %(min_bytes)s
            OR c.oid IN (
              SELECT c2.oid FROM pg_class c2
              JOIN pg_namespace n2 ON n2.oid = c2.relnamespace
              WHERE c2.relkind IN ('r','p')
                AND n2.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
              ORDER BY pg_total_relation_size(c2.oid) DESC
              LIMIT %(top_n)s
            )
          )
        ORDER BY total_bytes DESC;
    """, {"min_bytes": min_size_gb * 1024 ** 3, "top_n": top_n})


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


def get_pgstattuple(conn, schema, table):
    try:
        rows = fetch_all(conn, "SELECT * FROM pgstattuple(%s);",
                          (f'"{schema}"."{table}"',))
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


def get_index_depth(conn, schema, table):
    rows = fetch_all(conn, """
        SELECT
          s.indexrelname,
          s.idx_scan, s.idx_tup_read, s.idx_tup_fetch,
          pg_relation_size(s.indexrelid) AS index_bytes,
          am.amname AS index_type,
          pg_get_indexdef(s.indexrelid) AS index_def
        FROM pg_stat_user_indexes s
        JOIN pg_class ic ON ic.oid = s.indexrelid
        JOIN pg_am am ON am.oid = ic.relam
        WHERE s.schemaname = %s AND s.relname = %s
        ORDER BY index_bytes DESC;
    """, (schema, table))
    for r in rows:
        if r["index_type"] == "btree" and r["index_bytes"] > 0:
            r["estimated_btree_level"] = max(
                1, math.ceil(math.log(max(r["index_bytes"] / BLOCK_SIZE, 1), BTREE_FANOUT_ESTIMATE))
            )
        else:
            r["estimated_btree_level"] = None
    return rows


def collect_for_database(host, port, user, password, dbname, top_n, min_size_gb):
    conn = connect(host, port, user, password, dbname)
    conn.autocommit = True
    try:
        has_pgstattuple = check_pgstattuple(conn)
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
                "pgstattuple": get_pgstattuple(conn, schema, table) if has_pgstattuple else None,
                "dml_activity": get_dml_activity(conn, schema, table),
                "scan_pattern": get_scan_pattern(conn, schema, table),
                "indexes": get_index_depth(conn, schema, table),
            }
            tables.append(entry)
        return {
            "database": dbname,
            "pgstattuple_available": has_pgstattuple,
            "tables": tables,
        }
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="采集 PostgreSQL 大表原始统计数据（只读）")
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=5432)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", default=os.environ.get("PGPASSWORD", ""))
    ap.add_argument("--dbname", default=None, help="指定单个数据库；不指定则遍历所有非模板库")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--min-size-gb", type=float, default=10.0)
    ap.add_argument("-o", "--output", default=None, help="输出 JSON 文件路径，默认打印到 stdout")
    args = ap.parse_args()

    if not args.password:
        print("警告: 未提供密码，尝试使用 .pgpass 或信任认证连接", file=sys.stderr)

    admin_conn = connect(args.host, args.port, args.user, args.password,
                          args.dbname or "postgres")
    try:
        dbnames = [args.dbname] if args.dbname else list_databases(admin_conn)
    finally:
        admin_conn.close()

    result = {"instance": {"host": args.host, "port": args.port}, "databases": []}
    for dbname in dbnames:
        try:
            result["databases"].append(
                collect_for_database(args.host, args.port, args.user, args.password,
                                      dbname, args.top_n, args.min_size_gb)
            )
        except Exception as e:
            result["databases"].append({"database": dbname, "error": str(e)})

    output_json = json.dumps(result, default=str, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"已写入: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
