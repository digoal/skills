#!/usr/bin/env python3
# kingbase-parameter-tuning-advisor: KingbaseES 侧只读指标采集脚本（Python SDK 版）
#
# 用法:
#   export PGPASSWORD='your_password'          # 推荐；也可用 --password
#   ./collect_kingbase_metrics.py [--host H] [--port P] [--user U] [--dbname D] [--json]
#
# 连接参数解析优先级（与 SKILL.md 一致）:
#   1. 命令行参数 --host/--port/--user/--dbname/--password
#   2. 环境变量 PGHOST PGPORT PGDBNAME(PGDATABASE) PGUSER PGPASSWORD
#      （兼容 KingbaseES 手册的 KINGBASEHOST/KINGBASE_HOST 等 KINGBASE_* 变体）
#   3. 缺省值: 127.0.0.1 / 5432 / kingbase / kingbase / 123456
#
# 行为与 collect_kingbase_metrics.sql / .sh 一致：全部只读查询，不修改任何数据。
# 依赖: psycopg2 (pip install psycopg2-binary)

import argparse
import json
import os
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.stderr.write("缺少 psycopg2 依赖，请先执行: pip install psycopg2-binary\n")
    sys.exit(1)

DEFAULTS = {
    "host": "127.0.0.1",
    "port": "5432",
    "dbname": "kingbase",
    "user": "kingbase",
    "password": "123456",
}

# 兼容 PG 风格与 KINGBASE_* 风格环境变量
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


def q(cur, sql):
    """执行查询并返回全部行。"""
    cur.execute(sql)
    return cur.fetchall()


def main():
    parser = argparse.ArgumentParser(description="KingbaseES 参数调优只读指标采集（psycopg2 版）")
    parser.add_argument("--host")
    parser.add_argument("--port")
    parser.add_argument("--user")
    parser.add_argument("--dbname")
    parser.add_argument("--password", help="密码；推荐使用 PGPASSWORD 环境变量，避免出现在 shell history")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON，便于程序化解析")
    args = parser.parse_args()

    cfg = resolve_conn(args)
    if not args.json and not os.environ.get("PGPASSWORD") and not args.password:
        sys.stderr.write("警告: 未提供密码，将依赖 ~/.pgpass 或触发交互式输入\n")

    # 人类可读输出只在非 --json 模式打印；JSON 模式保持 stdout 纯净
    def out(*a, **k):
        if not args.json:
            print(*a, **k)

    def section(title):
        out(f"\n===== {title} =====")

    try:
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"], user=cfg["user"],
            dbname=cfg["dbname"], password=cfg["password"],
            connect_timeout=10,
        )
    except Exception as exc:
        sys.stderr.write(
            f"无法连接 KingbaseES host={cfg['host']} port={cfg['port']} "
            f"dbname={cfg['dbname']} user={cfg['user']}: {exc}\n"
        )
        sys.exit(2)

    result = {}
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # ---- 1. 实例基础信息 ----
            section("1. 实例基础信息")
            result["version"] = q(cur, "SELECT version();")
            result["database_mode"] = q(cur, "SHOW database_mode;")
            result["config_file"] = q(cur, "SHOW config_file;")
            result["data_directory"] = q(cur, "SHOW data_directory;")
            result["postmaster_start"] = q(cur, "SELECT pg_postmaster_start_time();")
            for k in ("version", "database_mode", "config_file", "data_directory", "postmaster_start"):
                out(f"{k}: {result[k]}")

            # ---- 2. 关键参数 ----
            section("2. 关键参数")
            params = [
                "shared_buffers", "work_mem", "maintenance_work_mem", "effective_cache_size",
                "huge_pages", "max_connections", "superuser_reserved_connections",
                "wal_buffers", "min_wal_size", "max_wal_size", "checkpoint_timeout",
                "checkpoint_completion_target", "wal_compression", "max_worker_processes",
                "max_parallel_workers", "max_parallel_workers_per_gather", "max_wal_senders",
                "autovacuum_max_workers", "autovacuum_vacuum_cost_limit", "autovacuum_naptime",
                "autovacuum_vacuum_scale_factor", "autovacuum_analyze_scale_factor",
                "random_page_cost", "effective_io_concurrency", "default_statistics_target",
                "synchronous_commit", "synchronous_standby_names", "track_io_timing",
                "shared_preload_libraries",
            ]
            result["params"] = {}
            for p in params:
                try:
                    # SHOW 的列名即参数名；RealDictRow 只支持按列名索引（不支持整数下标）
                    row = q(cur, f"SHOW {p};")
                    result["params"][p] = row[0][p] if row else None
                except Exception as exc:
                    result["params"][p] = f"ERROR: {exc}"
            for k, v in result["params"].items():
                out(f"{k} = {v}")

            # 非默认参数
            result["non_default_settings"] = q(
                cur,
                "SELECT name, setting, unit, source, context FROM pg_settings "
                "WHERE source NOT IN ('default','override') ORDER BY name;",
            )

            # ---- 3. 缓存命中率 ----
            section("3. 缓存命中率（数据库级）")
            result["cache_hit"] = q(
                cur,
                "SELECT datname, blks_hit, blks_read, "
                "round(100.0*blks_hit/nullif(blks_hit+blks_read,0),2) AS cache_hit_ratio, "
                "temp_files, temp_bytes, deadlocks, xact_commit, xact_rollback "
                "FROM pg_stat_database WHERE datname NOT IN ('template0','template1') "
                "ORDER BY blks_read DESC;",
            )
            out(result["cache_hit"])

            # ---- 4. Checkpoint / bgwriter ----
            section("4. Checkpoint / bgwriter")
            result["bgwriter"] = q(
                cur,
                "SELECT checkpoints_timed, checkpoints_req, "
                "round(100.0*checkpoints_req/nullif(checkpoints_timed+checkpoints_req,0),2) "
                "AS req_checkpoint_ratio, checkpoint_write_time, checkpoint_sync_time, "
                "buffers_checkpoint, buffers_clean, buffers_backend, buffers_alloc, stats_reset "
                "FROM pg_stat_bgwriter;",
            )
            out(result["bgwriter"])

            # ---- 5. 连接状态 ----
            section("5. 连接状态分布")
            result["conn_state"] = q(
                cur,
                "SELECT state, count(*) AS cnt FROM pg_stat_activity "
                "WHERE pid <> pg_backend_pid() GROUP BY state ORDER BY cnt DESC;",
            )
            result["conn_total"] = q(
                cur,
                "SELECT count(*) AS current_connections, "
                "(SELECT setting::int FROM pg_settings WHERE name='max_connections') AS max_connections "
                "FROM pg_stat_activity;",
            )
            out("state 分布:", result["conn_state"])
            out("连接数:", result["conn_total"])

            # ---- 6. 锁等待 ----
            section("6. 锁等待")
            result["locks_waiting"] = q(
                cur,
                "SELECT locktype, relation::regclass, mode, granted, count(*) "
                "FROM pg_locks WHERE NOT granted "
                "GROUP BY locktype, relation, mode, granted;",
            )
            out(result["locks_waiting"] or "无未授予锁")

            # ---- 7. 表级扫描方式与膨胀信号 ----
            section("7. 表级扫描方式与膨胀信号 Top20")
            result["user_tables"] = q(
                cur,
                "SELECT schemaname, relname, seq_scan, idx_scan, n_live_tup, n_dead_tup, "
                "round(100.0*n_dead_tup/nullif(n_live_tup+n_dead_tup,0),2) AS dead_tup_ratio, "
                "last_autovacuum, last_autoanalyze "
                "FROM pg_stat_user_tables "
                "WHERE schemaname NOT IN "
                "('sys_catalog','sys_hm','sysaudit','sysmac','src_restrict','xlog_record_read',"
                "'dbms_job','dbms_scheduler','kdb_schedule','anon') "
                "ORDER BY (seq_scan+idx_scan) DESC LIMIT 20;",
            )
            out(result["user_tables"])

            # ---- 8. 慢查询 / 高频查询（sys_stat_statements） ----
            section("8. 慢查询 / 高频查询（sys_stat_statements）")
            try:
                result["top_sql"] = q(
                    cur,
                    "SELECT round(total_exec_time::numeric,2) AS total_exec_time_ms, calls, "
                    "round(mean_exec_time::numeric,2) AS mean_exec_time_ms, "
                    "round((100*total_exec_time/sum(total_exec_time) OVER())::numeric,2) AS pct_of_total, "
                    "left(query,120) AS query_snippet "
                    "FROM sys_stat_statements ORDER BY total_exec_time DESC LIMIT 20;",
                )
                out(result["top_sql"])
            except Exception as exc:
                result["top_sql"] = f"ERROR: {exc}"
                out(f"sys_stat_statements 不可用: {exc}")
                out("提示: 需在 kingbase.conf 的 shared_preload_libraries 中加入 "
                    "sys_stat_statements 并重启实例；当前降级为仅系统视图结论。")

            # ---- 9. 库大小 ----
            section("9. 数据库大小")
            result["db_sizes"] = q(
                cur,
                "SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size "
                "FROM pg_database ORDER BY pg_database_size(datname) DESC;",
            )
            out(result["db_sizes"])
    finally:
        conn.close()

    if args.json:
        # 转成可 JSON 序列化的结构（datetime 等转 str）
        def _conv(o):
            if hasattr(o, "isoformat"):
                return o.isoformat()
            if isinstance(o, (list, tuple)):
                return [_conv(x) for x in o]
            if isinstance(o, dict):
                return {k: _conv(v) for k, v in o.items()}
            return o

        print(json.dumps(_conv(result), ensure_ascii=False, indent=2, default=str))
    else:
        out("\n===== 采集完成 =====")


if __name__ == "__main__":
    main()
