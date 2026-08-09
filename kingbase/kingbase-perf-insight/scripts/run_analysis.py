#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kingbase-perf-insight: 统一只读查询执行入口（python sdk / psycopg2 方式）

与 scripts/run_analysis.sh 行为等价，只是改用 python 驱动连接数据库。

用法：
  export PGPASSWORD='xxx'
  ./run_analysis.py -h HOST -p PORT -U USER -d DBNAME -f SQL_FILE \
    [--schema stat_snapshot] [--start "2026-01-15 14:00:00"] [--end "2026-01-15 16:00:00"] \
    [--snap-begin 100] [--snap-end 101]

连接信息解析优先级（与 SKILL.md 一致）：
  1. 命令行参数 -h/-p/-U/-d
  2. 环境变量 PGHOST/PGPORT/PGUSER/PGDBNAME（兼容 PGDATABASE）
  3. 缺省值：PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGDBNAME=kingbase PGPASSWORD=123456

说明：
  - 密码只从环境变量 PGPASSWORD 或 --password 参数读取。
  - 所有查询在 READ ONLY 事务中执行，任何写操作都会被数据库拒绝。
  - SQL 文件中的 {schema}/{start_time}/{end_time}/:snap_begin_id/:snap_end_id 占位符会被替换为实际值。
"""

import argparse
import os
import re
import sys

try:
    import psycopg2
except ImportError:
    sys.stderr.write("错误：需要 psycopg2，请执行 pip install psycopg2-binary\n")
    sys.exit(1)


def parse_args():
    p = argparse.ArgumentParser(description="kingbase-perf-insight 只读查询执行器 (python sdk)",
                                add_help=False)
    p.add_argument("--help", action="help", help="显示帮助并退出")
    p.add_argument("-h", "--host", dest="host", default=None)
    p.add_argument("-p", "--port", dest="port", default=None)
    p.add_argument("-U", "--user", dest="user", default=None)
    p.add_argument("-d", "--dbname", dest="dbname", default=None)
    # 注意：刻意不提供 --password 命令行参数——明文密码会出现在 ps aux/历史记录中，
    # 与技能安全约定冲突。密码一律通过环境变量 PGPASSWORD（或 ~/.pgpass）传递。
    p.add_argument("-f", "--file", dest="sql_file", required=True)
    p.add_argument("--schema", default="stat_snapshot")
    p.add_argument("--start", default="")
    p.add_argument("--end", default="")
    p.add_argument("--snap-begin", dest="snap_begin", default="")
    p.add_argument("--snap-end", dest="snap_end", default="")
    return p.parse_args()


def resolve_conn(args):
    """连接信息解析：命令行参数 > 环境变量 > 缺省值"""
    host = args.host or os.environ.get("PGHOST", "127.0.0.1")
    port = args.port or os.environ.get("PGPORT", "5432")
    user = args.user or os.environ.get("PGUSER", "kingbase")
    dbname = args.dbname or os.environ.get("PGDBNAME") or os.environ.get("PGDATABASE", "kingbase")
    password = os.environ.get("PGPASSWORD", "123456")
    return {
        "host": host,
        "port": port,
        "user": user,
        "dbname": dbname,
        "password": password,
    }


def substitute(sql, args):
    # 若 SQL 引用了快照ID占位符但调用方未提供，直接报错而不是静默替换为 NULL
    # （静默替换会让查询悄悄返回空结果，掩盖“忘了传 --snap-begin/--snap-end”的错误）。
    if ":snap_begin_id" in sql and not args.snap_begin:
        sys.stderr.write("错误：SQL 引用了 :snap_begin_id，但未提供 --snap-begin\n")
        sys.exit(1)
    if ":snap_end_id" in sql and not args.snap_end:
        sys.stderr.write("错误：SQL 引用了 :snap_end_id，但未提供 --snap-end\n")
        sys.exit(1)
    sql = sql.replace("{schema}", args.schema)
    sql = sql.replace("{start_time}", args.start)
    sql = sql.replace("{end_time}", args.end)
    sql = re.sub(r":snap_begin_id\b", args.snap_begin, sql)
    sql = re.sub(r":snap_end_id\b", args.snap_end, sql)
    return sql


def main():
    args = parse_args()
    conn_info = resolve_conn(args)
    with open(args.sql_file, "r", encoding="utf-8") as f:
        sql = substitute(f.read(), args)

    sql = "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;\n" + sql

    try:
        conn = psycopg2.connect(**conn_info)
        conn.set_session(readonly=True, autocommit=False)
        cur = conn.cursor()
        # 以分号分隔的多语句脚本依次执行，保留每个结果集。
        # 注意：此拆分方式要求 SQL 文件中的字符串字面量/函数体里不要出现分号
        # （本技能附带的 8 个分析脚本均满足该约束）。
        for stmt in sql.split(";"):
            # 去掉整行注释后再判断是否为空语句，避免 psycopg2 报 "empty query"
            stmt = re.sub(r"^\s*--.*$", "", stmt, flags=re.M).strip()
            if not stmt:
                continue
            cur.execute(stmt)
            if cur.description is not None:
                headers = [d.name for d in cur.description]
                rows = cur.fetchall()
                print("\t".join(headers))
                for row in rows:
                    print("\t".join("" if v is None else str(v) for v in row))
        cur.close()
        conn.commit()
    except psycopg2.Error as e:
        sys.stderr.write("数据库错误: %s\n" % e)
        sys.exit(1)
    finally:
        if "conn" in locals() and conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
