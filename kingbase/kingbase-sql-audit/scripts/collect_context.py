#!/usr/bin/env python3
# collect_context.py
# 只读方式采集金仓（KingbaseES）目标库的环境背景信息，供 SQL 上线审查使用。
# Python SDK 通道（psycopg2 优先，自动降级 psycopg3），与 collect_context.sh 结果等价。
#
# 用法:
#   export PGPASSWORD='your_password'          # 推荐；也可用 --password
#   ./collect_context.py [--host H] [--port P] [--user U] [--dbname D] [--tables "s.t1,s.t2"] [--password P]
#
# 连接参数解析优先级（与 SKILL.md 一致）:
#   1. 命令行参数 --host/--port/--user/--dbname/--password
#   2. 环境变量 PGHOST PGPORT PGDBNAME(PGDATABASE) PGUSER PGPASSWORD
#      （兼容金仓手册风格的 KINGBASEHOST/KINGBASE_HOST 等 KINGBASE_* 变体）
#   3. 缺省值: 127.0.0.1 / 5432 / kingbase / kingbase / 123456
#
# 安全约束（金仓实测要点）:
#   - 连接建立后先执行 SET default_transaction_read_only = on 作为会话兜底
#   - 每条查询包裹在 BEGIN; SET TRANSACTION READ ONLY; ...; ROLLBACK; 中执行
#   - 不执行任何 DDL/DML，不使用 EXPLAIN ANALYZE / EXPLAIN BUFFERS

import argparse
import os
import sys

try:
    import psycopg2
    DRIVER = "psycopg2"
except ImportError:
    try:
        import psycopg as psycopg2  # psycopg3 兼容层: connect/cursor/execute/commit/rollback 接口一致
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
    parser = argparse.ArgumentParser(description="KingbaseES SQL 上线审查: 环境背景只读采集 (psycopg2/psycopg3)")
    parser.add_argument("--host")
    parser.add_argument("--port")
    parser.add_argument("--user")
    parser.add_argument("--dbname")
    parser.add_argument("--password", help="密码；推荐使用 PGPASSWORD 环境变量，避免出现在 shell history")
    parser.add_argument("--tables", help="逗号分隔的表清单，如 public.t1,public.t2")
    args = parser.parse_args()

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

    def ro_exec(label, sql):
        """在只读事务中执行查询并打印结果。"""
        print(f"===== {label} =====")
        cur = conn.cursor()
        try:
            cur.execute("BEGIN")
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(sql)
            rows = cur.fetchall()
            if not rows:
                print("(0 rows)")
            for r in rows:
                print(r)
        except Exception as exc:
            print(f"[错误] {exc}")
        finally:
            try:
                cur.execute("ROLLBACK")
            except Exception:
                conn.rollback()
            cur.close()
        print()

    try:
        cur = conn.cursor()
        cur.execute("SET default_transaction_read_only = on")
        conn.commit()
        cur.close()

        print("############ kingbase-sql-audit 环境背景采集 ############")
        print(f"目标实例: {cfg['host']}:{cfg['port']}/{cfg['dbname']} (user={cfg['user']}) driver={DRIVER}")
        print()

        # 注意: psycopg2/psycopg3 单次 execute 多语句时 fetchall 只返回最后一条的结果集，
        # 因此 SELECT version() 必须单独执行，否则会被静默丢弃
        ro_exec("实例版本", "SELECT version();")
        ro_exec("兼容模式与配置文件", """
SELECT name, setting FROM pg_settings
WHERE name IN ('database_mode','server_version','hba_file','config_file');
""")

        ro_exec("关键超时参数", """
SELECT name, setting, unit
FROM pg_settings
WHERE name IN ('statement_timeout','lock_timeout','idle_in_transaction_session_timeout',
               'work_mem','maintenance_work_mem','shared_buffers','max_locks_per_transaction');
""")

        if args.tables:
            for tbl in args.tables.split(","):
                tbl = tbl.strip()
                if not tbl:
                    continue
                if "." in tbl:
                    schema_part, table_part = tbl.split(".", 1)
                else:
                    schema_part, table_part = "public", tbl

                ro_exec(f"表统计信息: {tbl}", f"""
SELECT relname, n_live_tup, n_dead_tup, last_analyze, last_autoanalyze,
       last_vacuum, last_autovacuum, seq_scan, idx_scan
FROM pg_stat_user_tables
WHERE schemaname='{schema_part}' AND relname='{table_part}';
""")
                ro_exec(f"表大小: {tbl}", f"""
SELECT pg_size_pretty(pg_total_relation_size('{schema_part}.{table_part}'::regclass)) AS total_size,
       pg_size_pretty(pg_relation_size('{schema_part}.{table_part}'::regclass)) AS table_size;
""")
                ro_exec(f"索引列表: {tbl}", f"""
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname='{schema_part}' AND tablename='{table_part}';
""")
                ro_exec(f"外键依赖: {tbl}", f"""
SELECT conname, confrelid::regclass AS references_table, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = '{schema_part}.{table_part}'::regclass AND contype='f';
""")
                ro_exec(f"被引用情况(反向外键): {tbl}", f"""
SELECT conname, conrelid::regclass AS dependent_table, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE confrelid = '{schema_part}.{table_part}'::regclass AND contype='f';
""")
                ro_exec(f"依赖的视图/物化视图: {tbl}", f"""
SELECT DISTINCT dependent_ns.nspname AS schema, dependent_view.relname AS view_name, dependent_view.relkind
FROM pg_depend
JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
JOIN pg_class AS dependent_view ON pg_rewrite.ev_class = dependent_view.oid
JOIN pg_class AS source_table ON pg_depend.refobjid = source_table.oid
JOIN pg_namespace dependent_ns ON dependent_view.relnamespace = dependent_ns.oid
WHERE source_table.relname = '{table_part}'
  AND source_table.relnamespace = '{schema_part}'::regnamespace;
""")
                ro_exec(f"触发器: {tbl}", f"""
SELECT tgname, tgenabled, pg_get_triggerdef(oid)
FROM pg_trigger
WHERE tgrelid = '{schema_part}.{table_part}'::regclass AND NOT tgisinternal;
""")

        ro_exec("sys_stat_statements(金仓版pg_stat_statements) 可用性", """
SELECT count(*) AS recorded_queries
FROM sys_stat_statements;
""")

        ro_exec("长事务/未提交事务排查", """
SELECT pid, usename, state, xact_start, now()-xact_start AS xact_age,
       left(query,120) AS query_snippet
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start ASC
LIMIT 20;
""")

        ro_exec("当前锁等待情况", """
SELECT locktype, relation::regclass, mode, granted, pid
FROM pg_locks
WHERE NOT granted;
""")

        print("############ 采集完成 ############")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
