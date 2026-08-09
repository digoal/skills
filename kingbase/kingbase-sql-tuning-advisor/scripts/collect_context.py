#!/usr/bin/env python3
# collect_context.py —— 采集 KingbaseES（金仓）SQL 调优上下文（Python SDK 通道）
# 与 collect_context.sh 结果等价，psycopg2 优先，自动降级 psycopg3。
#
# 采集内容:
#   1. 实例版本 / database_mode / config_file
#   2. 关键 GUC 参数（内存/代价模型/并行/开关/JIT）
#   3. 每张表的列定义、索引、约束、relpages/reltuples、大小、pg_stat_user_tables 统计
#   4. 关心列的 pg_stats 统计
#   5. sys_stat_statements 可用性与已记录语句量
#
# 用法:
#   export PGPASSWORD='xxx'                 # 推荐；也可用 --password
#   ./collect_context.py [-h HOST] [-p PORT] [-U USER] [-d DBNAME] \
#       -t "schema1.table1,schema1.table2" [-c "col1,col2"]
#
# 连接参数解析优先级: 命令行 > 环境变量(PGHOST/PGPORT/PGUSER/PGDBNAME/PGDATABASE/PGPASSWORD 及 KINGBASE* 变体) > 缺省值
#   缺省值: 127.0.0.1:5432 kingbase/kingbase/123456

import argparse
import os
import sys

try:
    import psycopg2
    DRIVER = "psycopg2"
except ImportError:
    try:
        import psycopg as psycopg2
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

GUC_LIST = [
    "work_mem", "shared_buffers", "effective_cache_size", "maintenance_work_mem",
    "random_page_cost", "seq_page_cost", "cpu_tuple_cost", "cpu_index_tuple_cost", "effective_io_concurrency",
    "max_parallel_workers_per_gather", "max_parallel_workers", "parallel_setup_cost", "parallel_tuple_cost",
    "min_parallel_table_scan_size",
    "enable_seqscan", "enable_indexscan", "enable_indexonlyscan", "enable_bitmapscan",
    "enable_nestloop", "enable_hashjoin", "enable_mergejoin", "enable_material", "enable_sort",
    "jit", "jit_above_cost", "default_statistics_target",
    "statement_timeout", "lock_timeout", "idle_in_transaction_session_timeout", "max_connections",
]


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


def main():
    parser = argparse.ArgumentParser(description="KingbaseES SQL 调优: 采集上下文 (psycopg2/psycopg3)")
    parser.add_argument("--host", help="连接主机（或用 PGHOST 环境变量）")
    parser.add_argument("-p", "--port")
    parser.add_argument("-U", "--user")
    parser.add_argument("-d", "--dbname")
    parser.add_argument("--password", help="密码；推荐使用 PGPASSWORD 环境变量")
    parser.add_argument("-t", "--tables", default="", help='逗号分隔: "schema1.table1,schema1.table2"')
    parser.add_argument("-c", "--columns", default="", help='逗号分隔关心列（pg_stats 过滤）')
    args = parser.parse_args()

    cfg = resolve_conn(args)
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"], user=cfg["user"],
        password=cfg["password"], dbname=cfg["dbname"],
    )
    cur = conn.cursor()

    def q(query, params=None):
        cur.execute(query, params)
        rows = cur.fetchall()
        for r in rows:
            print(" | ".join("" if v is None else str(v) for v in r))

    print("===== 1. 实例信息 =====")
    q("SELECT 'version: ' || version()")
    q("SELECT 'database_mode: ' || current_setting('database_mode')")
    q("SELECT 'config_file: ' || current_setting('config_file')")
    q("SELECT 'server_version_num: ' || current_setting('server_version_num')")

    print("\n===== 2. 关键 GUC 参数 =====")
    q("SELECT name || ' = ' || setting || COALESCE(' ' || unit, '') FROM pg_settings WHERE name = ANY(%s) ORDER BY name", (GUC_LIST,))

    tables = [t.strip() for t in args.tables.split(",") if t.strip()]
    if not tables:
        print("\n(未提供 -t 参数，跳过表级上下文采集。如需要请用 -t \"schema.table1,schema.table2\")")
        return

    for t in tables:
        schema, _, table = t.partition(".")
        print(f"\n===== 3. 表上下文: {schema}.{table} =====")

        print("--- 3.1 列定义 ---")
        q("""SELECT a.attnum, a.attname, format_type(a.atttypid, a.atttypmod) AS type,
                    CASE WHEN a.attnotnull THEN 'NOT NULL' ELSE '' END AS notnull,
                    COALESCE(pg_get_expr(d.adbin, d.adrelid), '') AS default_val
               FROM pg_attribute a
               LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
              WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped
              ORDER BY a.attnum""", (f"{schema}.{table}",))

        print("--- 3.2 索引 ---")
        q("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = %s AND tablename = %s", (schema, table))

        print("--- 3.3 约束 ---")
        q("""SELECT conname, contype, pg_get_constraintdef(oid)
               FROM pg_constraint WHERE conrelid = %s::regclass ORDER BY contype, conname""", (f"{schema}.{table}",))

        print("--- 3.4 表大小 / relpages / reltuples ---")
        q("SELECT 'total_size: ' || pg_size_pretty(pg_total_relation_size(%s::regclass))", (f"{schema}.{table}",))
        q("""SELECT 'relpages: ' || relpages || ', reltuples: ' || reltuples || ', relkind: ' || relkind
               FROM pg_class WHERE oid = %s::regclass""", (f"{schema}.{table}",))

        print("--- 3.5 pg_stat_user_tables 统计 ---")
        q("""SELECT 'n_live_tup: ' || n_live_tup || ', n_dead_tup: ' || n_dead_tup ||
                    ', last_vacuum: ' || COALESCE(last_vacuum::text,'-') ||
                    ', last_autovacuum: ' || COALESCE(last_autovacuum::text,'-') ||
                    ', last_analyze: ' || COALESCE(last_analyze::text,'-') ||
                    ', last_autoanalyze: ' || COALESCE(last_autoanalyze::text,'-')
               FROM pg_stat_user_tables WHERE schemaname = %s AND relname = %s""", (schema, table))

        print("--- 3.6 pg_stats（关心列，未给 -c 则全部列） ---")
        cols = [c.strip() for c in args.columns.split(",") if c.strip()]
        if cols:
            q("""SELECT attname, null_frac, n_distinct, most_common_vals, most_common_freqs, histogram_bounds
                   FROM pg_stats WHERE schemaname = %s AND tablename = %s AND attname = ANY(%s)
                   ORDER BY attname""", (schema, table, cols))
        else:
            q("""SELECT attname, null_frac, n_distinct, most_common_vals, most_common_freqs, histogram_bounds
                   FROM pg_stats WHERE schemaname = %s AND tablename = %s ORDER BY attname""", (schema, table))

    print("\n===== 4. sys_stat_statements 可用性 =====")
    q("""SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_class WHERE relname = 'sys_stat_statements')
                     THEN 'available, rows=' || (SELECT count(*) FROM sys_stat_statements)
                     ELSE 'NOT available (请确认 sys_stat_statements 是否加载)' END""")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
