#!/usr/bin/env python3
"""
kingbase_awr_collector.py — KingbaseES 两次快照做差采集器（AWR 风格报告的数据层）

针对 KingbaseES（金仓）V9R1C10 及以上，默认采用 PG 12 兼容模式。
将 Oracle AWR "两次快照做差得到速率" 思路移植过来。
Step 0: 环境探测（版本/权限/扩展/关键 GUC）
Step 1: 采集 Snapshot A
Step 2: 等待窗口 + 等待事件轮询（模拟 ASH）
Step 3: 采集 Snapshot B，计算 Delta，输出 JSON

用法:
  # 推荐：通过 PG 兼容环境变量传密码
  export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGPASSWORD=xxx \
         PGDBNAME=kingbase
  python3 kingbase_awr_collector.py --interval-seconds 900 \
    --ash-sample-interval 2 --output snapshot_diff.json

  # 或显式传 DSN
  python3 kingbase_awr_collector.py \
    --dsn "postgresql://kingbase:xxx@127.0.0.1:5432/kingbase" \
    --interval-seconds 900 --ash-sample-interval 2 --output snapshot_diff.json

安全说明:
  - 连接串中的密码只用于建立连接，脚本不会把 DSN 或密码写入输出文件/日志。
  - 输出的 JSON 中 dsn 字段会被脱敏为 postgresql://user:***@host:port/db。
  - 全程只读查询，不执行任何 DDL/DML，不调用 pg_stat_reset()，也不调用
    kingbase 内置的 kwr_snap/kwr_report/kwr_delete 等过程（避免污染 KWR 历史）。
  - 建议优先通过环境变量 PGPASSWORD/KINGBASE_PASSWORD 传递密码，
    避免密码出现在进程列表 (ps aux) 中。

连接参数解析优先级（与 SKILL.md 一致）:
  1. 命令行 --dsn / -H/-p/-d/-U/-W 显式参数
  2. PG 兼容环境变量 PGHOST/PGPORT/PGDBNAME/PGUSER/PGPASSWORD
  3. KingbaseES 专属环境变量 KINGBASE_HOST/KINGBASE_PORT/KINGBASE_DB/
     KINGBASE_USER/KINGBASE_PASSWORD
  4. 内置默认值（仅在没有以上任何环境变量时使用）

依赖:
  pip install psycopg2-binary --break-system-packages
"""

import argparse
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("缺少依赖，请先运行: pip install psycopg2-binary --break-system-packages", file=sys.stderr)
    sys.exit(1)


# ---------- 内置默认连接参数（兜底） ----------
DEFAULT_CONN_PARAMS = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "kingbase",
    "user": "kingbase",
    "password": "123456",
}


def parse_dsn(dsn):
    """使用 urllib.parse 解析 DSN，比正则更可靠。"""
    from urllib.parse import urlparse, unquote
    p = urlparse(dsn)
    params = {}
    if p.hostname:
        params["host"] = p.hostname
    if p.port:
        params["port"] = p.port
    if p.username:
        params["user"] = unquote(p.username)
    if p.password:
        params["password"] = unquote(p.password)
    if p.path and p.path != "/":
        params["dbname"] = p.path.lstrip("/")
    return params


def resolve_conn_params(args):
    """
    按优先级解析连接参数：
    命令行 > PG* 环境变量 > KINGBASE_* 环境变量 > 内置默认
    """
    # 1. 命令行 --dsn 优先级最高
    if args.dsn:
        try:
            return parse_dsn(args.dsn)
        except Exception as e:
            print(f"--dsn 解析失败 ({e})，尝试其他来源", file=sys.stderr)

    # 2. 命令行 -H/-p/-d/-U/-W
    cli_params = {}
    if args.host:
        cli_params["host"] = args.host
    if args.port:
        cli_params["port"] = int(args.port)
    if args.dbname:
        cli_params["dbname"] = args.dbname
    if args.user:
        cli_params["user"] = args.user
    if args.password:
        cli_params["password"] = args.password
    if cli_params:
        return cli_params

    # 3. PG 兼容环境变量
    pg_params = {}
    if os.environ.get("PGHOST"):
        pg_params["host"] = os.environ["PGHOST"]
    if os.environ.get("PGPORT"):
        pg_params["port"] = int(os.environ["PGPORT"])
    if os.environ.get("PGDBNAME"):
        pg_params["dbname"] = os.environ["PGDBNAME"]
    if os.environ.get("PGUSER"):
        pg_params["user"] = os.environ["PGUSER"]
    if os.environ.get("PGPASSWORD"):
        pg_params["password"] = os.environ["PGPASSWORD"]
    if pg_params:
        return pg_params

    # 4. KingbaseES 专属环境变量
    kb_params = {}
    if os.environ.get("KINGBASE_HOST"):
        kb_params["host"] = os.environ["KINGBASE_HOST"]
    if os.environ.get("KINGBASE_PORT"):
        kb_params["port"] = int(os.environ["KINGBASE_PORT"])
    if os.environ.get("KINGBASE_DB"):
        kb_params["dbname"] = os.environ["KINGBASE_DB"]
    if os.environ.get("KINGBASE_USER"):
        kb_params["user"] = os.environ["KINGBASE_USER"]
    if os.environ.get("KINGBASE_PASSWORD"):
        kb_params["password"] = os.environ["KINGBASE_PASSWORD"]
    if kb_params:
        return kb_params

    # 5. 内置默认（兜底）
    print("[WARN] 未提供任何连接参数，使用内置默认值（仅供本地测试），生产环境请通过环境变量显式指定",
          file=sys.stderr)
    return dict(DEFAULT_CONN_PARAMS)


def mask_conn_params(params):
    """脱敏连接参数，仅用于日志/输出展示。"""
    user = params.get("user", "?")
    host = params.get("host", "?")
    port = params.get("port", "?")
    db = params.get("dbname", "?")
    return f"postgresql://{user}:***@{host}:{port}/{db}"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def fetch_all(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]


def fetch_one(conn, sql, params=None):
    rows = fetch_all(conn, sql, params)
    return rows[0] if rows else None


def detect_environment(conn):
    """
    Step 0: 版本、角色、权限、扩展、关键 GUC 探测，决定降级矩阵。
    KingbaseES 兼容 PG12 视图体系，但 sys_stat_statements 替代 pg_stat_statements。
    """
    info = {}
    info["instance"] = fetch_one(conn, """
        SELECT version() AS full_version,
               current_setting('server_version_num')::int AS ver_num,
               current_setting('server_version') AS ver_str,
               pg_is_in_recovery() AS is_standby,
               now() AS db_time,
               pg_postmaster_start_time() AS instance_start_time
    """)
    info["role"] = fetch_one(conn, """
        SELECT rolname, rolsuper, rolreplication
        FROM pg_roles WHERE rolname = current_user
    """)
    info["extensions"] = fetch_all(conn, """
        SELECT extname, extversion FROM pg_extension ORDER BY 1
    """)
    info["key_settings"] = fetch_all(conn, """
        SELECT name, setting, unit, source
        FROM pg_settings
        WHERE name IN (
          'shared_buffers','work_mem','maintenance_work_mem','effective_cache_size',
          'max_connections','track_io_timing','track_activities','autovacuum',
          'autovacuum_vacuum_scale_factor','autovacuum_max_workers',
          'wal_level','max_wal_size','min_wal_size','checkpoint_timeout',
          'checkpoint_completion_target','random_page_cost','shared_preload_libraries',
          'syskwr_enable','sys_stat_statements_max'
        )
    """)

    # 关键能力探测
    has_sysss = any(e["extname"] == "sys_stat_statements" for e in info["extensions"])
    has_syskwr = any(e["extname"] == "sys_kwr" for e in info["extensions"])
    has_pg_blocking = fetch_one(conn,
        "SELECT 1 FROM pg_proc WHERE proname = 'pg_blocking_pids'") is not None
    has_wal_lsn_diff = fetch_one(conn,
        "SELECT 1 FROM pg_proc WHERE proname = 'pg_wal_lsn_diff'") is not None

    info["capabilities"] = {
        "sys_stat_statements": has_sysss,
        "sys_kwr": has_syskwr,
        "is_superuser": bool(info["role"]["rolsuper"]),
        "pg_blocking_pids": has_pg_blocking,
        "pg_wal_lsn_diff": has_wal_lsn_diff,
        "ver_num": info["instance"]["ver_num"],
    }
    return info


def collect_snapshot(conn, ver_num, has_sysss):
    """采集一次完整快照（Step 1 / Step 3 复用同一份逻辑）。"""
    snap = {"collected_at": now_iso()}

    # pg_stat_database —— KES V9R1C10 基于 PG12，字段完整
    snap["pg_stat_database"] = fetch_all(conn, """
        SELECT datname, numbackends, xact_commit, xact_rollback,
               blks_read, blks_hit,
               tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
               conflicts, temp_files, temp_bytes, deadlocks,
               blk_read_time, blk_write_time, stats_reset
        FROM pg_stat_database
        WHERE datname IS NOT NULL
    """)

    # pg_stat_bgwriter —— KES V9R1C10 基于 PG12，无 pg_stat_checkpointer 拆分
    snap["bgwriter"] = fetch_one(conn, """
        SELECT checkpoints_timed, checkpoints_req, checkpoint_write_time,
               checkpoint_sync_time, buffers_checkpoint, buffers_clean,
               maxwritten_clean, buffers_backend, buffers_backend_fsync,
               buffers_alloc, stats_reset
        FROM pg_stat_bgwriter
    """)

    # sys_stat_statements —— KES 特有，替代 pg_stat_statements
    # 差异：多 parses/plans/total_parse_time/total_plan_time，少 wal_records/wal_bytes
    if has_sysss:
        snap["sys_stat_statements"] = fetch_all(conn, """
            SELECT queryid, LEFT(query, 200) AS query_sample,
                   parses, total_parse_time, mean_parse_time,
                   plans, total_plan_time, mean_plan_time,
                   calls, total_exec_time, mean_exec_time,
                   min_exec_time, max_exec_time, rows,
                   shared_blks_hit, shared_blks_read,
                   shared_blks_dirtied, shared_blks_written,
                   temp_blks_read, temp_blks_written,
                   blk_read_time, blk_write_time
            FROM sys_stat_statements
            ORDER BY total_exec_time DESC
            LIMIT 50
        """)
    else:
        snap["sys_stat_statements"] = None

    # sys_stat_statements_all —— KES 特有跨库视图（仅记录是否存在，不强制采集）
    if has_sysss:
        snap["sys_stat_statements_all"] = fetch_all(conn, """
            SELECT queryid, LEFT(query, 200) AS query_sample,
                   calls, total_exec_time, mean_exec_time,
                   shared_blks_hit, shared_blks_read
            FROM sys_stat_statements_all
            ORDER BY total_exec_time DESC
            LIMIT 30
        """)
    else:
        snap["sys_stat_statements_all"] = None

    snap["user_tables"] = fetch_all(conn, """
        SELECT schemaname, relname,
               n_tup_ins, n_tup_upd, n_tup_del, n_live_tup, n_dead_tup,
               last_vacuum, last_autovacuum, last_analyze, last_autoanalyze,
               vacuum_count, autovacuum_count, analyze_count, autoanalyze_count
        FROM pg_stat_user_tables
        ORDER BY n_dead_tup DESC
        LIMIT 30
    """)

    snap["statio_user_tables"] = fetch_all(conn, """
        SELECT schemaname, relname,
               heap_blks_read, heap_blks_hit, idx_blks_read, idx_blks_hit,
               toast_blks_read, toast_blks_hit
        FROM pg_statio_user_tables
        ORDER BY heap_blks_read DESC
        LIMIT 30
    """)

    snap["locks_waiting"] = fetch_all(conn, """
        SELECT l.pid, l.locktype, l.mode, l.granted,
               LEFT(a.query, 200) AS query_sample, a.state,
               a.wait_event_type, a.wait_event,
               pg_blocking_pids(l.pid) AS blocked_by
        FROM pg_locks l
        JOIN pg_stat_activity a ON a.pid = l.pid
        WHERE NOT l.granted
    """)

    snap["replication"] = fetch_all(conn, """
        SELECT application_name, client_addr, state,
               pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) AS sent_lag_bytes,
               pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes,
               write_lag, flush_lag, replay_lag
        FROM pg_stat_replication
    """)

    is_standby = fetch_one(conn, "SELECT pg_is_in_recovery() AS is_standby")["is_standby"]
    if is_standby:
        snap["wal_position"] = fetch_one(conn,
            "SELECT pg_last_wal_replay_lsn() AS lsn")
        snap["replay_delay"] = fetch_one(conn,
            "SELECT now() - pg_last_xact_replay_timestamp() AS replay_delay")
    else:
        snap["wal_position"] = fetch_one(conn,
            "SELECT pg_current_wal_lsn() AS lsn")
        snap["replay_delay"] = None

    snap["database_sizes"] = fetch_all(conn,
        "SELECT datname, pg_database_size(datname) AS size_bytes FROM pg_database")

    snap["table_sizes"] = fetch_all(conn, """
        SELECT schemaname, relname, pg_total_relation_size(relid) AS size_bytes
        FROM pg_stat_user_tables
        ORDER BY size_bytes DESC
        LIMIT 20
    """)

    return snap


def ash_sampler(conn_params, interval_seconds, sample_interval, stop_event, results):
    """
    在采样窗口内周期性采集 pg_stat_activity 的等待事件，模拟 ASH。
    使用独立短连接，避免与主采集连接互相阻塞。
    """
    counter = Counter()
    samples_taken = 0
    conn = psycopg2.connect(**conn_params)
    conn.autocommit = True
    try:
        deadline = time.time() + interval_seconds
        while time.time() < deadline and not stop_event.is_set():
            rows = fetch_all(conn, """
                SELECT wait_event_type, wait_event
                FROM pg_stat_activity
                WHERE state != 'idle' AND pid != pg_backend_pid()
            """)
            samples_taken += 1
            for r in rows:
                key = f"{r['wait_event_type'] or 'CPU/Running'}:{r['wait_event'] or '-'}"
                counter[key] += 1
            time.sleep(sample_interval)
    finally:
        conn.close()
    results["wait_event_histogram"] = counter.most_common(30)
    results["ash_samples_taken"] = samples_taken


def build_arg_parser():
    ap = argparse.ArgumentParser(
        description="KingbaseES AWR 风格两次快照采集器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
连接参数解析优先级:
  1. --dsn / -H/-p/-d/-U/-W 命令行参数
  2. PG* 环境变量 (PGHOST/PGPORT/PGDBNAME/PGUSER/PGPASSWORD)
  3. KINGBASE_* 环境变量 (KINGBASE_HOST/KINGBASE_PORT/KINGBASE_DB/
     KINGBASE_USER/KINGBASE_PASSWORD)
  4. 内置默认值 (仅供本地测试)
        """,
    )
    ap.add_argument("--dsn", help="postgresql://user:password@host:port/dbname")
    ap.add_argument("-H", "--host", help="数据库主机")
    ap.add_argument("-p", "--port", help="数据库端口")
    ap.add_argument("-d", "--dbname", help="数据库名")
    ap.add_argument("-U", "--user", help="用户名")
    ap.add_argument("-W", "--password", help="密码（建议通过环境变量传）")
    ap.add_argument("--interval-seconds", type=int, default=900,
                    help="两次快照的间隔秒数，默认 900 秒 (15 分钟)")
    ap.add_argument("--ash-sample-interval", type=float, default=2.0,
                    help="等待事件采样间隔秒数，默认 2 秒")
    ap.add_argument("--output", default="snapshot_diff.json",
                    help="输出 JSON 路径")
    return ap


def main():
    ap = build_arg_parser()
    args = ap.parse_args()

    conn_params = resolve_conn_params(args)
    masked = mask_conn_params(conn_params)

    print(f"[{now_iso()}] 连接数据库: {masked}")

    # 主采集连接
    conn = psycopg2.connect(**conn_params)
    conn.autocommit = True

    env = detect_environment(conn)
    ver_num = env["capabilities"]["ver_num"]
    has_sysss = env["capabilities"]["sys_stat_statements"]
    has_syskwr = env["capabilities"]["sys_kwr"]

    print(f"[{now_iso()}] 环境探测完成: KingbaseES ver={env['instance']['ver_str']} "
          f"(num={ver_num}), "
          f"sys_stat_statements={'可用' if has_sysss else '不可用'}, "
          f"sys_kwr={'已启用' if has_syskwr else '未启用'}, "
          f"权限级别={'superuser' if env['capabilities']['is_superuser'] else '受限账号'}")

    print(f"[{now_iso()}] 采集 Snapshot A ...")
    snap_a = collect_snapshot(conn, ver_num, has_sysss)

    print(f"[{now_iso()}] 开始等待窗口 {args.interval_seconds} 秒，"
          f"期间同步采样等待事件 (间隔 {args.ash_sample_interval}s) ...")
    ash_results = {}
    stop_event = threading.Event()
    ash_thread = threading.Thread(
        target=ash_sampler,
        args=(conn_params, args.interval_seconds, args.ash_sample_interval,
              stop_event, ash_results),
        daemon=True,
    )
    ash_thread.start()
    ash_thread.join()

    print(f"[{now_iso()}] 采集 Snapshot B ...")
    try:
        snap_b = collect_snapshot(conn, ver_num, has_sysss)
        snapshot_b_ok = True
    except Exception as e:
        print(f"[{now_iso()}] Snapshot B 采集失败: {e}，"
              f"报告将降级为仅基于 Snapshot A 的静态健康检查", file=sys.stderr)
        snap_b = None
        snapshot_b_ok = False

    conn.close()

    output = {
        "dsn_masked": masked,
        "environment": env,
        "snapshot_a": snap_a,
        "snapshot_b": snap_b,
        "snapshot_b_ok": snapshot_b_ok,
        "ash": ash_results,
        "interval_seconds_requested": args.interval_seconds,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print(f"[{now_iso()}] 完成，已写入 {args.output}")
    print("下一步：按 SKILL.md 的 Step 4 章节结构，读取该 JSON 计算增量指标并撰写 Markdown 报告。")


if __name__ == "__main__":
    main()