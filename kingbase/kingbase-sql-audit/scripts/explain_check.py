#!/usr/bin/env python3
# explain_check.py
# 对给定 SQL 文件中的每条可 EXPLAIN 的语句（SELECT/INSERT/UPDATE/DELETE/MERGE/WITH）
# 只读方式获取执行计划，绝不加 ANALYZE，绝不真正执行会修改数据的语句。
# Python SDK 通道（psycopg2 优先，自动降级 psycopg3），与 explain_check.sh 结果等价。
#
# 用法:
#   export PGPASSWORD='your_password'          # 推荐；也可用 --password
#   ./explain_check.py [--host H] [--port P] [--user U] [--dbname D] -f sql_file.sql
#
# 连接参数解析优先级: 命令行 > 环境变量(PGHOST/PGPORT/PGUSER/PGDBNAME/PGDATABASE/PGPASSWORD 及 KINGBASE* 变体) > 缺省值
#
# 金仓差异（已在 V9R1C10 实测）:
#   - EXPLAIN (..., BUFFERS) 必须配 ANALYZE 否则报错，因此一律用 EXPLAIN (COSTS, VERBOSE, FORMAT TEXT)
#   - 只读事务使用 BEGIN; SET TRANSACTION READ ONLY; ...; ROLLBACK;
#   - 按分号切分语句时做了单引号/双引号/$$ dollar-quoting 感知，函数体内含分号不会被误切

import argparse
import os
import re
import sys

try:
    import psycopg2
    DRIVER = "psycopg2"
except ImportError:
    try:
        import psycopg as psycopg2  # psycopg3 兼容层
        DRIVER = "psycopg3"
    except ImportError:
        sys.stderr.write("缺少 psycopg2 依赖，请先执行: pip install psycopg2-binary (或 psycopg[binary])\n")
        sys.exit(1)

DEFAULTS = {
    "host": "127.0.0.1",
    "port": "5432",
    "dbname": "kingbase",
    "user": "kingbase",
    "password": "123456",
}

_ENV_MAP = {
    "host": ("PGHOST", "KINGBASEHOST", "KINGBASE_HOST"),
    "port": ("PGPORT", "KINGBASEPORT", "KINGBASE_PORT"),
    "dbname": ("PGDBNAME", "PGDATABASE", "KINGBASEDBNAME", "KINGBASE_DBNAME", "KINGBASE_DATABASE"),
    "user": ("PGUSER", "KINGBASEUSER", "KINGBASE_USER"),
    "password": ("PGPASSWORD", "KINGBASEPASSWORD", "KINGBASE_PASSWORD"),
}

EXPLAINABLE = {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "WITH"}
DDL_DCL = {"ALTER", "CREATE", "DROP", "GRANT", "REVOKE", "COMMENT", "TRUNCATE"}


def resolve_conn(args):
    cfg = {}
    for key in DEFAULTS:
        cfg[key] = getattr(args, key) or None
        if cfg[key] is None:
            for env in _ENV_MAP[key]:
                if os.environ.get(env):
                    cfg[key] = os.environ[env]
                    break
        if cfg[key] is None:
            cfg[key] = DEFAULTS[key]
    return cfg


def strip_comments(text):
    """去掉整行 -- 注释（不影响字符串内部）。"""
    return "\n".join(
        ln for ln in text.splitlines() if not re.match(r"^\s*--", ln)
    )


def split_statements(text):
    """按顶层分号切分 SQL，感知单引号/双引号/$$ dollar-quoting。"""
    statements = []
    buf = []
    state = "normal"
    dollar_tag = None
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if state == "normal":
            if c == "'":
                state = "single"
                buf.append(c)
            elif c == '"':
                state = "double"
                buf.append(c)
            elif c == "$":
                m = re.match(r"\$[A-Za-z_0-9]*\$", text[i:])
                if m:
                    dollar_tag = m.group(0)
                    state = "dollar"
                    buf.append(dollar_tag)
                    i += len(dollar_tag) - 1
                else:
                    buf.append(c)
            elif c == ";":
                stmt = "".join(buf).strip()
                if stmt:
                    statements.append(stmt)
                buf = []
            else:
                buf.append(c)
        elif state == "single":
            buf.append(c)
            if c == "'":
                if i + 1 < n and text[i + 1] == "'":
                    buf.append("'")
                    i += 1
                else:
                    state = "normal"
        elif state == "double":
            buf.append(c)
            if c == '"':
                if i + 1 < n and text[i + 1] == '"':
                    buf.append('"')
                    i += 1
                else:
                    state = "normal"
        elif state == "dollar":
            buf.append(c)
            if text.startswith(dollar_tag, i):
                if len(dollar_tag) > 1:
                    buf.append(dollar_tag[1:])
                    i += len(dollar_tag) - 1
                state = "normal"
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def main():
    parser = argparse.ArgumentParser(description="KingbaseES SQL 上线审查: EXPLAIN 只读检查 (psycopg2/psycopg3)")
    parser.add_argument("--host")
    parser.add_argument("--port")
    parser.add_argument("--user")
    parser.add_argument("--dbname")
    parser.add_argument("--password", help="密码；推荐使用 PGPASSWORD 环境变量，避免出现在 shell history")
    parser.add_argument("-f", "--file", required=True, help="SQL 文件路径")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        sys.stderr.write(f"错误: 找不到 SQL 文件 {args.file}\n")
        sys.exit(1)

    cfg = resolve_conn(args)
    try:
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"], user=cfg["user"],
            dbname=cfg["dbname"], password=cfg["password"], connect_timeout=10,
        )
    except Exception as exc:
        sys.stderr.write(
            f"无法连接 KingbaseES host={cfg['host']} port={cfg['port']} "
            f"dbname={cfg['dbname']} user={cfg['user']}: {exc}\n"
        )
        sys.exit(2)

    try:
        cur = conn.cursor()
        cur.execute("SET default_transaction_read_only = on")
        conn.commit()
        cur.close()

        with open(args.file, encoding="utf-8", errors="replace") as f:
            text = f.read()

        stmts = split_statements(strip_comments(text))
        idx = 0
        for stmt in stmts:
            first_word = stmt.lstrip().split(None, 1)[0].upper() if stmt.strip() else ""
            idx += 1
            if first_word in EXPLAINABLE:
                print(f"===== 语句 #{idx} 执行计划 ({first_word}) =====")
                print("--- 原始SQL ---")
                print(stmt)
                print("--- 执行计划 ---")
                cur = conn.cursor()
                try:
                    cur.execute("BEGIN")
                    cur.execute("SET TRANSACTION READ ONLY")
                    cur.execute("SET LOCAL statement_timeout = '30s'")
                    try:
                        cur.execute("EXPLAIN (COSTS, VERBOSE, FORMAT TEXT) " + stmt)
                        for r in cur.fetchall():
                            print(r[0])
                    except Exception as exc:
                        print(f"[错误] 无法获取执行计划: {exc}")
                        print("[提示] 可能含未绑定参数($1/:param)或依赖上下文，请人工复核。")
                finally:
                    try:
                        cur.execute("ROLLBACK")
                    except Exception:
                        conn.rollback()
                    cur.close()
                print()
            elif first_word in DDL_DCL:
                print(f"===== 语句 #{idx} ({first_word}) — DDL/DCL，跳过 EXPLAIN，转人工审查环节 =====")
                print(stmt)
                print()
            else:
                print(f"===== 语句 #{idx} ({first_word or '空'}) — 未识别类型，转人工审查环节 =====")
                print(stmt)
                print()
        print(f"############ EXPLAIN 检查完成，共处理 {idx} 条语句 ############")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
