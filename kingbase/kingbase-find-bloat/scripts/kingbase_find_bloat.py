#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kingbase-find-bloat: KingbaseES（金仓）表/索引膨胀巡检脚本（Python SDK 版，依赖 psycopg2）

与 scripts/run_query.sh（psql shell 版）等价，产出相同的诊断数据。
默认只读：不执行任何 DDL/DML；如需自动安装 kbstattuple 扩展，必须显式加 --create-extension。

连接参数解析优先级（与 SKILL.md 一致）：
  1. 命令行参数 --host/--port/--user/--dbname/--password/--dsn
  2. PG 兼容环境变量 PGHOST/PGPORT/PGDBNAME/PGUSER/PGPASSWORD
  3. 内置默认（127.0.0.1:5432, kingbase/kingbase, 仅供本地测试）

用法示例：
  # 全部使用环境变量（推荐，密码不进命令行）
  export PGHOST=127.0.0.1 PGPORT=5432 PGDBNAME=kingbase PGUSER=kingbase PGPASSWORD='123456'
  python3 kingbase_find_bloat.py --format markdown

  # 显式传连接参数
  python3 kingbase_find_bloat.py --host 127.0.0.1 --port 5432 --user kingbase \
      --dbname kingbase --password '123456' --format markdown

  # 指定只看某一个数据库
  python3 kingbase_find_bloat.py -d test --format markdown

  # 强制用估算模式（不探测/不安装 kbstattuple）
  python3 kingbase_find_bloat.py --mode estimate --format markdown
"""

import argparse
import json
import os
import sys
from decimal import Decimal


def json_default(o):
    """psycopg2 返回的 numeric 是 Decimal，转成 float 以便 JSON 序列化"""
    if isinstance(o, Decimal):
        return float(o)
    return str(o)

# ---------------------------------------------------------------------------
# 连接解析
# ---------------------------------------------------------------------------

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "5432"
DEFAULT_DBNAME = "kingbase"
DEFAULT_USER = "kingbase"
DEFAULT_PASSWORD = "123456"


def parse_args():
    parser = argparse.ArgumentParser(
        description="KingbaseES 表/索引膨胀巡检（只读）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", "-H", default=None, help="数据库主机")
    parser.add_argument("--port", "-p", default=None, help="数据库端口")
    parser.add_argument("--user", "-U", default=None, help="数据库用户")
    parser.add_argument("--dbname", "-d", default=None, help="数据库名（默认自动遍历全部业务库；指定后只扫该库）")
    parser.add_argument("--password", "-W", default=None,
                        help="数据库密码（优先使用 PGPASSWORD 环境变量，避免命令行泄露）")
    parser.add_argument("--dsn", default=None, help="完整 DSN，如 postgresql://user:pwd@host:5432/db")
    parser.add_argument("--mode", choices=["auto", "exact", "estimate"], default="auto",
                        help="auto=探测 kbstattuple，有则精确否则估算；exact=强制精确；estimate=强制估算")
    parser.add_argument("--create-extension", action="store_true",
                        help="superuser 且缺 kbstattuple 时自动 CREATE EXTENSION kbstattuple（默认不自动建）")
    parser.add_argument("--min-size-mb", type=float, default=8.0,
                        help="小于该大小的表/索引不纳入分析（避免小对象噪音）")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown",
                        help="输出格式")
    parser.add_argument("--json-file", default=None,
                        help="将完整 JSON 结果写入该文件（便于后续深度分析）")
    return parser.parse_args()


def resolve_conn(args):
    """优先级：命令行 > PGHOST/PGPORT/PGDBNAME/PGUSER/PGPASSWORD > 内置默认"""
    return {
        "host": args.host or os.environ.get("PGHOST", DEFAULT_HOST),
        "port": args.port or os.environ.get("PGPORT", DEFAULT_PORT),
        "dbname": args.dbname or os.environ.get("PGDBNAME", DEFAULT_DBNAME),
        "user": args.user or os.environ.get("PGUSER", DEFAULT_USER),
        "password": args.password or os.environ.get("PGPASSWORD", DEFAULT_PASSWORD),
    }


# ---------------------------------------------------------------------------
# SQL 语句（与 scripts/*.sql 保持一致；KingbaseES 无 round(double,int) 重载，
# 因此一律 round((expr)::numeric, 1)；排除 sys_ 前缀系统 schema）
# ---------------------------------------------------------------------------

SQL_LIST_DATABASES = """
select datname
from pg_database
where datistemplate = false
  and datallowconn = true
order by datname;
"""

SQL_CHECK_KBSTATTUPLE = """
select exists (select 1 from pg_extension where extname = 'kbstattuple') as has_kbstattuple;
"""

SQL_TABLE_BLOAT_EXACT = """
select
    n.nspname as schema_name,
    c.relname as object_name,
    coalesce(s.n_live_tup, 0) as row_estimate,
    pg_relation_size(c.oid) as real_size,
    round(
        pg_relation_size(c.oid)::numeric * (kbt.dead_tuple_percent + kbt.free_percent) / 100
    )::bigint as bloat_size,
    round((kbt.dead_tuple_percent + kbt.free_percent)::numeric, 1) as bloat_ratio
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
left join pg_stat_user_tables s on s.relid = c.oid
cross join lateral kbstattuple(c.oid) as kbt
where c.relkind = 'r'
  and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
  and n.nspname !~ '^sys_'
  and pg_relation_size(c.oid) >= %(min_size)s
order by bloat_size desc;
"""

SQL_INDEX_BLOAT_EXACT = """
select
    n.nspname as schema_name,
    ic.relname as object_name,
    t.relname as table_name,
    ic.reltuples::bigint as row_estimate,
    pg_relation_size(ic.oid) as real_size,
    round(
        pg_relation_size(ic.oid)::numeric * (100 - kbi.avg_leaf_density) / 100
    )::bigint as bloat_size,
    round((100 - kbi.avg_leaf_density)::numeric, 1) as bloat_ratio
from pg_class ic
join pg_index idx on idx.indexrelid = ic.oid
join pg_class t on t.oid = idx.indrelid
join pg_namespace n on n.oid = ic.relnamespace
join pg_am am on am.oid = ic.relam and am.amname = 'btree'
cross join lateral kbstatindex(ic.oid) as kbi
where ic.relkind = 'i'
  and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
  and n.nspname !~ '^sys_'
  and pg_relation_size(ic.oid) >= %(min_size)s
order by bloat_size desc;
"""

SQL_TABLE_BLOAT_ESTIMATE = """
with column_stats as (
    select schemaname, tablename, sum(avg_width) as avg_row_width
    from pg_stats
    where schemaname not in ('pg_catalog', 'information_schema', 'pg_toast')
      and schemaname !~ '^sys_'
    group by schemaname, tablename
),
table_info as (
    select
        n.nspname as schema_name,
        c.relname as object_name,
        c.oid,
        c.reltuples,
        pg_relation_size(c.oid) as real_size
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind = 'r'
      and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
      and n.nspname !~ '^sys_'
      and pg_relation_size(c.oid) >= %(min_size)s
)
select
    ti.schema_name,
    ti.object_name,
    ti.reltuples::bigint as row_estimate,
    ti.real_size,
    greatest(
        round(ti.real_size::numeric - ti.reltuples::numeric * (coalesce(cs.avg_row_width, 100)::numeric + 24) * 1.15),
        0
    )::bigint as bloat_size,
    round(
        greatest(
            ti.real_size::numeric - ti.reltuples::numeric * (coalesce(cs.avg_row_width, 100)::numeric + 24) * 1.15,
            0
        ) / nullif(ti.real_size, 0)::numeric * 100,
        1
    )::numeric as bloat_ratio
from table_info ti
left join column_stats cs
    on cs.schemaname = ti.schema_name and cs.tablename = ti.object_name
order by bloat_size desc;
"""

SQL_INDEX_BLOAT_ESTIMATE = """
with index_info as (
    select
        n.nspname as schema_name,
        ic.relname as object_name,
        t.relname as table_name,
        ic.reltuples,
        pg_relation_size(ic.oid) as real_size
    from pg_class ic
    join pg_index idx on idx.indexrelid = ic.oid
    join pg_class t on t.oid = idx.indrelid
    join pg_namespace n on n.oid = ic.relnamespace
    join pg_am am on am.oid = ic.relam and am.amname = 'btree'
    where ic.relkind = 'i'
      and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
      and n.nspname !~ '^sys_'
      and pg_relation_size(ic.oid) >= %(min_size)s
)
select
    schema_name,
    object_name,
    table_name,
    reltuples::bigint as row_estimate,
    real_size,
    greatest(round(real_size::numeric - (reltuples::numeric * 40 / 0.9)), 0)::bigint as bloat_size,
    round(
        greatest(real_size::numeric - (reltuples::numeric * 40 / 0.9), 0)
        / nullif(real_size, 0)::numeric * 100,
        1
    )::numeric as bloat_ratio
from index_info
order by bloat_size desc;
"""


# ---------------------------------------------------------------------------
# 危害阈值（与 SKILL.md Step 5 一致；用户可覆盖）
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "high_ratio": 40.0,   # bloat_ratio >= 40% -> 高危
    "high_bytes": 5 << 30,  # bloat_size >= 5GB -> 高危
    "mid_ratio": 20.0,    # 20% <= ratio < 40% -> 中危
    "mid_bytes": 1 << 30,  # 1GB <= size < 5GB -> 中危
}


def classify(row, th):
    ratio = float(row.get("bloat_ratio") or 0)
    size = int(row.get("bloat_size") or 0)
    if ratio >= th["high_ratio"] or size >= th["high_bytes"]:
        return "high"
    if ratio >= th["mid_ratio"] or size >= th["mid_bytes"]:
        return "mid"
    return "low"


def pg_pretty_size(n):
    n = float(n)
    for unit in ["B", "kB", "MB", "GB", "TB", "PB"]:
        if n < 1024.0 or unit == "PB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def connect(conn):
    import psycopg2
    if conn.get("dsn"):
        return psycopg2.connect(conn["dsn"])
    return psycopg2.connect(
        host=conn["host"],
        port=int(conn["port"]),
        dbname=conn["dbname"],
        user=conn["user"],
        password=conn["password"],
        connect_timeout=10,
    )


def fetch_databases(cur):
    cur.execute(SQL_LIST_DATABASES)
    return [r[0] for r in cur.fetchall()]


def probe_and_prepare(cur, mode, create_extension):
    """探测 kbstattuple；返回 'exact' 或 'estimate' 模式。mode='estimate' 时强制估算。"""
    if mode == "estimate":
        return "estimate"
    cur.execute(SQL_CHECK_KBSTATTUPLE)
    has = cur.fetchone()[0]
    if has:
        return "exact"
    if create_extension:
        try:
            cur.execute("create extension if not exists kbstattuple;")
            return "exact"
        except Exception:
            return "estimate"
    return "estimate"


def run_query(cur, sql, params):
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = []
    for r in cur.fetchall():
        rows.append(dict(zip(cols, r)))
    return rows


def collect_db(conn_info, dbname, mode, create_extension, min_size_bytes, thresholds):
    """在单个数据库上采集表/索引膨胀数据。返回该库的结果 dict。"""
    import psycopg2

    if conn_info.get("dsn"):
        from urllib.parse import urlparse
        p = urlparse(conn_info["dsn"])
        conn = psycopg2.connect(
            host=p.hostname or conn_info["host"],
            port=p.port or int(conn_info["port"]),
            dbname=dbname,
            user=p.username or conn_info["user"],
            password=p.password or conn_info["password"],
            connect_timeout=10,
        )
    else:
        conn = psycopg2.connect(
            host=conn_info["host"],
            port=int(conn_info["port"]),
            dbname=dbname,
            user=conn_info["user"],
            password=conn_info["password"],
            connect_timeout=10,
        )
    conn.autocommit = True
    cur = conn.cursor()
    try:
        eff_mode = probe_and_prepare(cur, mode, create_extension)
        params = {"min_size": min_size_bytes}
        if eff_mode == "exact":
            tables = run_query(cur, SQL_TABLE_BLOAT_EXACT, params)
            indexes = run_query(cur, SQL_INDEX_BLOAT_EXACT, params)
        else:
            tables = run_query(cur, SQL_TABLE_BLOAT_ESTIMATE, params)
            indexes = run_query(cur, SQL_INDEX_BLOAT_ESTIMATE, params)
        for r in tables:
            r["object_type"] = "table"
        for r in indexes:
            r["object_type"] = "index"
        objects = tables + indexes
        for r in objects:
            r["level"] = classify(r, thresholds)
        return {
            "database": dbname,
            "mode": eff_mode,
            "objects": sorted(objects, key=lambda x: (-x["bloat_size"], -x["bloat_ratio"])),
        }
    finally:
        cur.close()
        conn.close()


def build_markdown(results, thresholds, min_size_mb):
    lines = []
    total_high = 0
    total_mid = 0
    total_bloat = 0
    for db in results:
        objs = [o for o in db["objects"] if o["level"] in ("high", "mid")]
        high = [o for o in objs if o["level"] == "high"]
        mid = [o for o in objs if o["level"] == "mid"]
        total_high += len(high)
        total_mid += len(mid)
        total_bloat += sum(int(o["bloat_size"]) for o in objs)

        lines.append(f"\n## 数据库: {db['database']}（采集模式: {'精确(kbstattuple)' if db['mode'] == 'exact' else '估算'}）")
        lines.append("")
        lines.append("| 表名/索引名 | 类型 | 记录数 | 实际大小 | 膨胀大小 | 膨胀比例 | 危害程度 |")
        lines.append("|-------------|------|--------|----------|----------|----------|----------|")
        if not objs:
            lines.append("| （无高危/中危对象） | | | | | | |")
            continue
        for o in objs:
            name = f"{o['schema_name']}.{o['object_name']}"
            if o["object_type"] == "index":
                name += f" (表: {o['schema_name']}.{o['table_name']})"
            level_map = {"high": "🔴 高危", "mid": "🟡 中危"}
            lines.append(
                f"| {name} | {o['object_type']} | {o['row_estimate']:,} | "
                f"{pg_pretty_size(o['real_size'])} ({o['real_size']:,}B) | "
                f"{pg_pretty_size(o['bloat_size'])} ({o['bloat_size']:,}B) | "
                f"{o['bloat_ratio']}% | {level_map[o['level']]} |"
            )

    lines.append("")
    lines.append("## 总结")
    lines.append(f"- 巡检数据库数: {len(results)}，高危对象: {total_high}，中危对象: {total_mid}")
    lines.append(f"- 预计可回收总空间: {pg_pretty_size(total_bloat)} ({total_bloat:,}B)")
    lines.append(f"- 最小分析对象大小: {min_size_mb:.0f}MB（小于该值不纳入判定）")
    lines.append(f"- 危害阈值: 高危=膨胀比例≥{thresholds['high_ratio']:.0f}% 或 ≥{pg_pretty_size(thresholds['high_bytes'])}；"
                 f"中危=比例≥{thresholds['mid_ratio']:.0f}% 或 ≥{pg_pretty_size(thresholds['mid_bytes'])}")
    return "\n".join(lines)


def main():
    args = parse_args()
    conn = resolve_conn(args)
    if args.dsn:
        conn["dsn"] = args.dsn
    if not conn["password"]:
        print("错误：未提供密码（请用 PGPASSWORD 环境变量或 --password）", file=sys.stderr)
        sys.exit(1)

    min_size_bytes = int(args.min_size_mb * 1024 * 1024)
    thresholds = DEFAULT_THRESHOLDS

    try:
        conn_admin = connect(conn)
    except Exception as e:
        print(f"连接失败: {e}", file=sys.stderr)
        sys.exit(1)

    results = []
    try:
        cur = conn_admin.cursor()
        cur.execute("select version();")
        version = cur.fetchone()[0]
        if args.dbname:
            databases = [args.dbname]
        else:
            databases = fetch_databases(cur)
        cur.close()
    finally:
        conn_admin.close()

    for dbname in databases:
        try:
            results.append(collect_db(conn, dbname, args.mode, args.create_extension,
                                      min_size_bytes, thresholds))
        except Exception as e:
            print(f"[警告] 数据库 {dbname} 采集失败: {e}", file=sys.stderr)

    if not results:
        print("未采集到任何数据库结果", file=sys.stderr)
        sys.exit(1)

    payload = {
        "version": version,
        "min_size_bytes": min_size_bytes,
        "thresholds": thresholds,
        "databases": results,
    }
    if args.json_file:
        with open(args.json_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=json_default)
        print(f"JSON 结果已写入: {args.json_file}", file=sys.stderr)

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default))
    else:
        print(build_markdown(results, thresholds, args.min_size_mb))


if __name__ == "__main__":
    main()
