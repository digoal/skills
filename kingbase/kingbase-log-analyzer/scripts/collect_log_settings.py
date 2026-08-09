#!/usr/bin/env python3
# kingbase-log-analyzer: 只读采集日志相关配置（Python SDK 版）
#
# 用法：
#   方式一（环境变量，缺省 127.0.0.1:5432/kingbase/kingbase/123456）：
#     ./collect_log_settings.py
#   方式二（显式连接参数）：
#     ./collect_log_settings.py --host 127.0.0.1 --port 5432 \
#       --user kingbase --password 123456 --dbname kingbase
#
# 说明：
#   - 与 collect_log_settings.sql 等价，二选一即可。
#   - 连接参数解析优先级：命令行参数 > 环境变量(PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE) > 缺省值。
#   - KingbaseES 默认采用 PG 兼容模式，连接参数沿用 PG 风格环境变量。
#   - 全部为只读 SHOW/SELECT，不做任何写操作。
#
# 依赖：psycopg2（pip install psycopg2-binary）

import argparse
import os
import sys


def main():
    # 库名环境变量：同时兼容用户指定的 PGDBNAME 与 PG 惯例的 PGDATABASE
    dbname_env = os.environ.get("PGDBNAME") or os.environ.get("PGDATABASE") or "kingbase"

    parser = argparse.ArgumentParser(description="采集 KingbaseES 日志相关配置（只读）")
    parser.add_argument("--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("PGPORT", "5432")))
    parser.add_argument("--user", default=os.environ.get("PGUSER", "kingbase"))
    parser.add_argument("--password", default=os.environ.get("PGPASSWORD", "123456"))
    parser.add_argument("--dbname", default=dbname_env)
    args = parser.parse_args()

    try:
        import psycopg2
    except ImportError:
        sys.stderr.write("缺少 psycopg2 依赖，请先执行: pip install psycopg2-binary\n")
        sys.exit(1)

    # (标题, SQL 或 SHOW 语句列表)
    SECTIONS = [
        ("1. 版本与环境", [
            "SELECT version();",
            "SHOW server_version;",
            "SHOW timezone;",
            "SHOW log_timezone;",
        ]),
        ("2. 日志输出格式与目录", [
            "SHOW log_destination;",
            "SHOW logging_collector;",
            "SHOW log_directory;",
            "SHOW log_filename;",
            "SHOW log_file_mode;",
            "SHOW log_truncate_on_rotation;",
            "SHOW log_rotation_age;",
            "SHOW log_rotation_size;",
            "SHOW log_line_prefix;",
        ]),
        ("3. 日志内容开关（决定哪些维度数据可得）", [
            "SHOW log_min_duration_statement;",
            "SHOW log_statement;",
            "SHOW log_checkpoints;",
            "SHOW log_connections;",
            "SHOW log_disconnections;",
            "SHOW log_lock_waits;",
            "SHOW log_temp_files;",
            "SHOW log_autovacuum_min_duration;",
            "SHOW log_min_messages;",
            "SHOW log_error_verbosity;",
        ]),
        ("4. 金仓特有：审计/安全/健康监控 相关开关", [
            "SELECT name, setting FROM pg_settings "
            "WHERE name IN ('sysaudit.log','sysmac.log','sys_hm',"
            " 'track_sql','track_instance','track_real_stats');",
        ]),
        ("5. 与日志分析相关的其他关键参数", [
            "SHOW data_directory;",
            "SHOW archive_mode;",
            "SHOW archive_command;",
            "SHOW max_connections;",
            "SHOW shared_buffers;",
            "SHOW checkpoint_timeout;",
            "SHOW max_wal_size;",
            "SHOW work_mem;",
            "SHOW max_prepared_transactions;",
        ]),
    ]

    conn = None
    try:
        conn = psycopg2.connect(
            host=args.host, port=args.port, user=args.user,
            password=args.password, dbname=args.dbname, connect_timeout=10,
        )
        conn.autocommit = True
    except Exception as exc:
        sys.stderr.write(f"连接失败: {exc}\n"
                         f"（已尝试 {args.user}@{args.host}:{args.port}/{args.dbname}）\n")
        sys.exit(1)

    with conn.cursor() as cur:
        for title, statements in SECTIONS:
            print(f"\n===== {title} =====")
            for sql in statements:
                try:
                    cur.execute(sql)
                    if cur.description is None:
                        continue
                    cols = [d[0] for d in cur.description]
                    for row in cur.fetchall():
                        # SHOW 返回单列（列名即参数名）；SELECT 返回 name/setting 两列
                        if len(row) == 1:
                            print(f"  {cols[0]} = {row[0]}")
                        else:
                            print(f"  {row[0]} = {row[1]}")
                except Exception as exc:
                    print(f"  [ERROR] {sql[:60]}... : {exc}")

    conn.close()
    print("\n===== 采集完成：请结合日志目录与上述参数判断数据可得性 =====")


if __name__ == "__main__":
    main()
