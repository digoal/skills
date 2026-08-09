#!/usr/bin/env python3
# kingbase-log-analyzer: 开启 csvlog 结构化日志（Python SDK 版）
#
# 等价于 enable_csvlog.sql，另提供 --check（只读查看，默认）与 --revert（回滚到 stderr）。
#
# 用法：
#   ./enable_csvlog.py                       # 不带参数＝只读查看当前日志配置（默认，安全）
#   ./enable_csvlog.py --enable              # 开启 csvlog（stderr,csvlog 并存）+ reload
#   ./enable_csvlog.py --revert              # 回滚为 stderr + reload
#
# 连接参数解析优先级：命令行 > 环境变量(PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDBNAME/PGDATABASE) > 缺省。
# 依赖：psycopg2（pip install psycopg2-binary）

import argparse
import os
import sys


def get_conn(args):
    try:
        import psycopg2
    except ImportError:
        sys.stderr.write("缺少 psycopg2 依赖，请先执行: pip install psycopg2-binary\n")
        sys.exit(1)
    try:
        conn = psycopg2.connect(
            host=args.host, port=args.port, user=args.user,
            password=args.password, dbname=args.dbname, connect_timeout=10,
        )
        conn.autocommit = True
        return conn
    except Exception as exc:
        sys.stderr.write(f"连接失败: {exc}\n")
        sys.exit(1)


def main():
    dbname_env = os.environ.get("PGDBNAME") or os.environ.get("PGDATABASE") or "kingbase"
    ap = argparse.ArgumentParser(description="KingbaseES 开启/查看 csvlog 日志配置")
    ap.add_argument("--enable", action="store_true",
                    help="开启 csvlog（stderr,csvlog 并存）+ reload；不带参数则只读查看")
    ap.add_argument("--revert", action="store_true", help="回滚为 stderr + reload")
    ap.add_argument("--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PGPORT", "5432")))
    ap.add_argument("--user", default=os.environ.get("PGUSER", "kingbase"))
    ap.add_argument("--password", default=os.environ.get("PGPASSWORD", "123456"))
    ap.add_argument("--dbname", default=dbname_env)
    args = ap.parse_args()

    if args.enable and args.revert:
        sys.stderr.write("--enable 与 --revert 不能同时使用\n")
        sys.exit(2)

    conn = get_conn(args)

    def show(what):
        with conn.cursor() as cur:
            cur.execute(f"SHOW {what}")
            print(f"  {what} = {cur.fetchone()[0]}")

    print("===== 当前日志配置 =====")
    for p in ("log_destination", "logging_collector", "log_directory", "log_filename"):
        show(p)

    if args.enable:
        with conn.cursor() as cur:
            cur.execute("ALTER SYSTEM SET log_destination = 'stderr,csvlog'")
            cur.execute("ALTER SYSTEM SET logging_collector = on")
            cur.execute("SELECT pg_reload_conf()")
        print("\n===== 已开启 csvlog（stderr,csvlog 并存）并 reload =====")
        show("log_destination")
        print("提示：日志目录将出现与 .log 同基名的 .csv 文件，可用 parse_csvlog.py 解析。")
    elif args.revert:
        with conn.cursor() as cur:
            cur.execute("ALTER SYSTEM SET log_destination = 'stderr'")
            cur.execute("SELECT pg_reload_conf()")
        print("\n===== 已回滚为 stderr 并 reload =====")
        show("log_destination")

    conn.close()


if __name__ == "__main__":
    main()
