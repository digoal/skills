#!/usr/bin/env python3
# safe_explain.py —— 安全获取 KingbaseES（金仓）执行计划（Python SDK 通道）
# 与 safe_explain.sh 结果等价，psycopg2 优先，自动降级 psycopg3。
#
# 安全策略（与 .sh 版一致）:
#   - 只读 SELECT: 设置 statement_timeout 后 EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
#   - DML: BEGIN + SET LOCAL statement_timeout + EXPLAIN ANALYZE + 无条件 ROLLBACK，绝不 COMMIT
#   - --no-analyze: 仅 EXPLAIN (VERBOSE) 估算计划，不真实执行
#   - --params '{"$1": 100, "$2": "2026-01-01"}': 内联替换绑定变量（数值/布尔/null 不加引号）
#
# 用法:
#   export PGPASSWORD='xxx'                # 推荐；也可用 --password
#   ./safe_explain.py [--host HOST] [-p PORT] [-U USER] [-d DBNAME] -f sql_file.sql \
#       [--timeout 30] [--dml] [--no-analyze] [--params '{"$1": 1}']
#
# 连接参数解析优先级: 命令行 > 环境变量(PGHOST/PGPORT/PGUSER/PGDBNAME/PGDATABASE/PGPASSWORD 及 KINGBASE* 变体) > 缺省值
#   缺省值: 127.0.0.1:5432 kingbase/kingbase/123456

import argparse
import json
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

DML_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "MERGE"}


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


def first_keyword(sql):
    """剥离开头注释（-- 行注释 / /* */ 块注释）与前置括号后，取首个关键字。
    用于 DML 识别：避免带注释的 DML（如 '-- 更新\nUPDATE ...'）被误判为只读。"""
    s = sql
    while True:
        s = re.sub(r"^[ \t\r\n()]+", "", s)
        if not s:
            return ""
        if s.startswith("--"):
            j = s.find("\n")
            s = s[j + 1:] if j != -1 else ""
            continue
        if s.startswith("/*"):
            j = s.find("*/")
            s = s[j + 2:] if j != -1 else ""
            continue
        break
    m = re.match(r"[A-Za-z]+", s)
    return m.group(0).upper() if m else ""


def substitute_params(sql, params_json):
    """内联替换 $1/$2 绑定变量。数值/布尔/null 不加引号，其余按字符串字面量。"""
    if not params_json:
        return sql
    params = json.loads(params_json)

    def lit(v):
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, (int, float)):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"

    for k, v in params.items():
        if not re.fullmatch(r"\$\d+", k):
            sys.stderr.write(f"参数键必须是 $1/$2 形式: {k}\n")
            sys.exit(1)
        sql = re.sub(re.escape(k) + r"(?![0-9])", lambda m: lit(v), sql)
    return sql


def main():
    parser = argparse.ArgumentParser(description="KingbaseES SQL 调优: 安全 EXPLAIN (psycopg2/psycopg3)")
    parser.add_argument("--host", help="连接主机（或用 PGHOST 环境变量）")
    parser.add_argument("-p", "--port")
    parser.add_argument("-U", "--user")
    parser.add_argument("-d", "--dbname")
    parser.add_argument("--password", help="密码；推荐使用 PGPASSWORD 环境变量")
    parser.add_argument("-f", "--file", required=True, help="SQL 文件路径")
    parser.add_argument("-t", "--timeout", type=int, default=30, help="statement_timeout 秒数，默认 30")
    parser.add_argument("--dml", action="store_true", help="显式声明 DML，走事务+回滚路径")
    parser.add_argument("--no-analyze", action="store_true", help="仅估算计划，不真实执行")
    parser.add_argument("--params", default="", help='JSON: {"$1": 100, "$2": "2026-01-01"}')
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        sys.stderr.write(f"错误: 找不到 SQL 文件 {args.file}\n")
        sys.exit(1)

    cfg = resolve_conn(args)
    with open(args.file, "r", encoding="utf-8") as f:
        sql = f.read().strip().rstrip(";").strip()

    first_word = first_keyword(sql)
    is_dml = args.dml or first_word in DML_KEYWORDS
    if not first_word and not args.dml:
        print("[警告] 未能识别 SQL 首关键字，将按只读路径处理；若这是 DML 请显式加 --dml。")
    elif not first_word:
        pass

    sql = substitute_params(sql, args.params)
    if args.params:
        print("== 已按 --params 内联替换绑定变量 ==")

    explain = "EXPLAIN (VERBOSE, FORMAT TEXT)" if args.no_analyze else "EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT)"

    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"], user=cfg["user"],
        password=cfg["password"], dbname=cfg["dbname"],
    )
    conn.autocommit = False
    cur = conn.cursor()
    try:
        cur.execute(f"SET statement_timeout = {args.timeout * 1000}")
        cur.execute("SET lock_timeout = 5000")
        if is_dml:
            cur.execute("BEGIN")
            cur.execute(f"SET LOCAL statement_timeout = {args.timeout * 1000}")
            print("== DML 模式：事务内 EXPLAIN ANALYZE，结束后强制 ROLLBACK，绝不提交 ==")
        try:
            cur.execute(f"{explain} {sql}")
            for row in cur.fetchall():
                print(row[0])
        finally:
            if is_dml:
                cur.execute("ROLLBACK")
                print("== 已回滚，未对数据造成任何持久化变更 ==")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
