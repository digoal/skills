#!/usr/bin/env python3
# kingbase-find-unused-index 批量扫描脚本（Python SDK 版）
#
# 用法:
#   export PGPASSWORD='your_password'   # 可选；也可通过命令行/env/连接串传入
#   ./find_unused_indexes.py <host> <port> <user> [dbname_regex_filter]
#
# 依赖: psycopg2 (pip install psycopg2-binary)
#
# 行为与 find_unused_indexes.sh 完全一致：枚举实例下所有非模板、可连接
# 数据库，逐库输出未使用索引明细。便于嵌入到更大的诊断流水线或被
# Agent 工具进程直接调用。

import argparse
import os
import re
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.stderr.write(
        "缺少 psycopg2 依赖，请先执行: pip install psycopg2-binary\n"
    )
    sys.exit(1)


# KingbaseES 内置 schema，不作为用户级"未使用索引"判定
KBUILTIN_SCHEMAS = (
    "sys_catalog", "sys_hm", "sysaudit", "sysmac",
    "src_restrict", "xlog_record_read",
    "dbms_job", "dbms_scheduler", "kdb_schedule", "anon",
)


def connect(host, port, user, dbname, password=None):
    """使用 libpq 兼容 DSN 连接。"""
    return psycopg2.connect(
        host=host,
        port=port,
        user=user,
        dbname=dbname,
        password=password,
        connect_timeout=10,
    )


def list_databases(conn):
    """列出非模板、可连接的所有数据库。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT datname FROM pg_database "
            "WHERE datistemplate = false AND datallowconn = true "
            "ORDER BY datname"
        )
        return [r[0] for r in cur.fetchall()]


def stats_window(conn):
    """取统计信息重置时间与实例启动时间，用于判断 idx_scan=0 是否可信。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT stats_reset, pg_postmaster_start_time() "
            "FROM pg_stat_database WHERE datname = current_database()"
        )
        row = cur.fetchone()
        return {"stats_reset": row[0], "instance_start": row[1]}


UNUSED_INDEX_SQL = """
    SELECT
      n.nspname                                      AS schema_name,
      s.relname                                       AS table_name,
      s.indexrelname                                  AS index_name,
      pg_size_pretty(pg_relation_size(s.indexrelid))  AS index_size,
      pg_size_pretty(pg_relation_size(s.relid))       AS table_size,
      round(
        100.0 * pg_relation_size(s.indexrelid) /
        NULLIF(pg_relation_size(s.relid), 0), 1
      )                                                AS index_pct_of_table,
      s.idx_scan,
      i.indisunique                                   AS is_unique,
      i.indisexclusion                                AS is_exclusion,
      EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conindid = s.indexrelid
          AND c.contype IN ('f','u','p')
      )                                                AS backs_constraint,
      pg_get_indexdef(s.indexrelid)                   AS index_def
    FROM pg_stat_user_indexes s
    JOIN pg_index i     ON i.indexrelid = s.indexrelid
    JOIN pg_class c      ON c.oid = s.relid
    JOIN pg_namespace n  ON n.oid = c.relnamespace
    WHERE s.idx_scan = 0
      AND NOT i.indisprimary
      AND n.nspname NOT IN ({schemas})
    ORDER BY pg_relation_size(s.indexrelid) DESC;
""".format(schemas=", ".join(f"'{s}'" for s in KBUILTIN_SCHEMAS))


def find_unused_indexes(conn):
    """执行未使用索引扫描，返回 list[dict]。"""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(UNUSED_INDEX_SQL)
        return cur.fetchall()


def main():
    parser = argparse.ArgumentParser(
        description="KingbaseES 未使用索引扫描（psycopg2 版）",
    )
    parser.add_argument("host")
    parser.add_argument("port", type=int)
    parser.add_argument("user")
    parser.add_argument("dbname_filter", nargs="?", default=".*",
                        help="可选：只扫描名字匹配该正则的数据库")
    parser.add_argument("--admin-db", default=os.environ.get("PGDATABASE", "kingbase"),
                        help="用于枚举 pg_database 的管理库，"
                             "默认 PGDATABASE 环境变量 / kingbase")
    parser.add_argument("--password",
                        default=os.environ.get("PGPASSWORD"),
                        help="PGPASSWORD 环境变量或显式传入，"
                             "不要写到命令行历史；推荐使用 env 变量")
    args = parser.parse_args()

    if not args.password:
        sys.stderr.write(
            "警告: 未提供 --password 且 PGPASSWORD 也未设置，"
            "将依赖 ~/.pgpass 或触发交互式输入。\n"
        )

    db_filter_re = re.compile(args.dbname_filter)

    try:
        admin_conn = connect(args.host, args.port, args.user, args.admin_db, args.password)
    except Exception as exc:
        sys.stderr.write(f"无法连接到 admin 库 {args.admin_db}: {exc}\n")
        sys.exit(2)

    databases = list_databases(admin_conn)
    admin_conn.close()
    print(f"==> 共发现 {len(databases)} 个数据库")

    for db in databases:
        if not db_filter_re.search(db):
            continue
        print()
        print("########################################")
        print(f"## 数据库: {db}")
        print("########################################")
        try:
            conn = connect(args.host, args.port, args.user, db, args.password)
        except Exception as exc:
            print(f"!! 跳过: 无法连接 {db}: {exc}", file=sys.stderr)
            continue
        try:
            ctx = stats_window(conn)
            print(
                f"统计窗口: stats_reset={ctx['stats_reset']}, "
                f"instance_start={ctx['instance_start']}"
            )
            rows = find_unused_indexes(conn)
            if not rows:
                print("未发现符合条件 (idx_scan=0 且非主键/内置 schema) 的索引。")
                continue
            for i, r in enumerate(rows, 1):
                print(
                    f"[{i}] {r['schema_name']}.{r['index_name']} on "
                    f"{r['table_name']} | index={r['index_size']} "
                    f"table={r['table_size']} ({r['index_pct_of_table']}%) "
                    f"idx_scan={r['idx_scan']} "
                    f"backs_constraint={r['backs_constraint']}"
                )
                print(f"    DDL: {r['index_def']}")
        finally:
            conn.close()

    print()
    print("==> 扫描完成。")


if __name__ == "__main__":
    main()