#!/usr/bin/env python3
"""
pg_awr_collector.py — PostgreSQL 两次快照做差采集器（AWR 风格报告的数据层）

用法:
  python3 pg_awr_collector.py --dsn "postgresql://user:password@host:5432/dbname" \
      --interval-seconds 900 --ash-sample-interval 2 --output snapshot_diff.json

安全说明:
  - 连接串中的密码只用于建立连接，脚本不会把 DSN 或密码写入输出文件/日志。
  - 输出的 JSON 中 dsn 字段会被脱敏为 postgresql://user:***@host:port/db。
  - 全程只读查询，不执行任何 DDL/DML，不调用 pg_stat_reset()。
  - 建议优先通过环境变量 PGPASSWORD 传递密码，避免密码出现在进程列表 (ps aux) 中。

依赖:
  pip install psycopg2-binary --break-system-packages
"""

import argparse
import json
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


def mask_dsn(dsn: str) -> str:
    """脱敏连接串中的密码，仅用于日志/输出展示。"""
    return re.sub(r"(://[^:/@]+:)[^@]+(@)", r"\1***\2", dsn)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_all(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]


def fetch_one(conn, sql, params=None):
    rows = fetch_all(conn, sql, params)
    return rows[0] if rows else None


def detect_environment(conn):
    """Step 0/1: 版本、角色、权限、扩展、关键 GUC 探测，决定降级矩阵。"""
    info = {}
    info["instance"] = fetch_one(conn, """
        SELECT version() AS full_version,
               current_setting('server_version_num')::int AS ver_num,
               pg_is_in_recovery() AS is_standby,
               now() AS db_time,
               pg_postmaster_start_time() AS instance_start_time
    """)
    info["role"] = fetch_one(conn, """
        SELECT rolname, rolsuper, rolreplication
        FROM pg_roles WHERE rolname = current_user
    """)
    info["has_pg_monitor"] = fetch_one(conn, """
        SELECT pg_has_role(current_user, 'pg_monitor', 'member') AS has_pg_monitor
    """)
    info["extensions"] = fetch_all(conn, "SELECT extname, extversion FROM pg_extension ORDER BY 1")
    info["key_settings"] = fetch_all(conn, """
        SELECT name, setting, unit, source
        FROM pg_settings
        WHERE name IN (
          'shared_buffers','work_mem','maintenance_work_mem','effective_cache_size',
          'max_connections','track_io_timing','track_activities','autovacuum',
          'autovacuum_vacuum_scale_factor','autovacuum_max_workers',
          'wal_level','max_wal_size','min_wal_size','checkpoint_timeout',
          'checkpoint_completion_target','random_page_cost','shared_preload_libraries'
        )
    """)
    has_pgss = any(e["extname"] == "pg_stat_statements" for e in info["extensions"])
    info["capabilities"] = {
        "pg_stat_statements": has_pgss,
        "is_superuser_or_monitor": bool(info["role"]["rolsuper"]) or bool(info["has_pg_monitor"]["has_pg_monitor"]),
        "ver_num": info["instance"]["ver_num"],
    }
    return info


def collect_snapshot(conn, ver_num, has_pgss):
    """采集一次完整快照（Step 1 / Step 3 复用同一份逻辑）。"""
    snap = {"collected_at": now_iso()}

    snap["pg_stat_database"] = fetch_all(conn, """
        SELECT datname, numbackends, xact_commit, xact_rollback,
               blks_read, blks_hit,
               tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
               conflicts, temp_files, temp_bytes, deadlocks,
               blk_read_time, blk_write_time, stats_reset
        FROM pg_stat_database
        WHERE datname IS NOT NULL
    """)

    if ver_num >= 170000:
        snap["checkpointer"] = fetch_one(conn, """
            SELECT num_timed AS checkpoints_timed, num_requested AS checkpoints_req,
                   write_time AS checkpoint_write_time, sync_time AS checkpoint_sync_time,
                   buffers_written AS buffers_checkpoint, stats_reset
            FROM pg_stat_checkpointer
        """)
        snap["bgwriter"] = fetch_one(conn, """
            SELECT buffers_clean, maxwritten_clean, buffers_alloc, stats_reset
            FROM pg_stat_bgwriter
        """)
    else:
        snap["bgwriter"] = fetch_one(conn, """
            SELECT checkpoints_timed, checkpoints_req, checkpoint_write_time, checkpoint_sync_time,
                   buffers_checkpoint, buffers_clean, maxwritten_clean,
                   buffers_backend, buffers_backend_fsync, buffers_alloc, stats_reset
            FROM pg_stat_bgwriter
        """)
        snap["checkpointer"] = None

    if has_pgss:
        snap["pg_stat_statements"] = fetch_all(conn, """
            SELECT queryid, LEFT(query, 200) AS query_sample,
                   calls, total_exec_time, mean_exec_time, min_exec_time, max_exec_time,
                   rows, shared_blks_hit, shared_blks_read, shared_blks_dirtied, shared_blks_written,
                   temp_blks_read, temp_blks_written, wal_records, wal_bytes
            FROM pg_stat_statements
            ORDER BY total_exec_time DESC
            LIMIT 50
        """)
    else:
        snap["pg_stat_statements"] = None

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
               LEFT(a.query, 200) AS query_sample, a.state, a.wait_event_type, a.wait_event,
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
        snap["wal_position"] = fetch_one(conn, "SELECT pg_last_wal_replay_lsn() AS lsn")
        snap["replay_delay"] = fetch_one(conn, "SELECT now() - pg_last_xact_replay_timestamp() AS replay_delay")
    else:
        snap["wal_position"] = fetch_one(conn, "SELECT pg_current_wal_lsn() AS lsn")
        snap["replay_delay"] = None

    snap["database_sizes"] = fetch_all(conn, "SELECT datname, pg_database_size(datname) AS size_bytes FROM pg_database")

    snap["table_sizes"] = fetch_all(conn, """
        SELECT schemaname, relname, pg_total_relation_size(relid) AS size_bytes
        FROM pg_stat_user_tables
        ORDER BY size_bytes DESC
        LIMIT 20
    """)

    return snap


def ash_sampler(dsn, interval_seconds, sample_interval, stop_event, results):
    """在采样窗口内周期性采集 pg_stat_activity 的等待事件，模拟 ASH。"""
    counter = Counter()
    samples_taken = 0
    conn = psycopg2.connect(dsn)
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


def main():
    ap = argparse.ArgumentParser(description="PostgreSQL AWR 风格两次快照采集器")
    ap.add_argument("--dsn", required=True, help="postgresql://user:password@host:port/dbname")
    ap.add_argument("--interval-seconds", type=int, default=900, help="两次快照的间隔秒数，默认 900 秒 (15 分钟)")
    ap.add_argument("--ash-sample-interval", type=float, default=2.0, help="等待事件采样间隔秒数，默认 2 秒")
    ap.add_argument("--output", default="snapshot_diff.json", help="输出 JSON 路径")
    args = ap.parse_args()

    masked = mask_dsn(args.dsn)
    print(f"[{now_iso()}] 连接数据库: {masked}")

    conn = psycopg2.connect(args.dsn)
    conn.autocommit = True

    env = detect_environment(conn)
    ver_num = env["capabilities"]["ver_num"]
    has_pgss = env["capabilities"]["pg_stat_statements"]

    print(f"[{now_iso()}] 环境探测完成: PG version_num={ver_num}, "
          f"pg_stat_statements={'可用' if has_pgss else '不可用'}, "
          f"权限级别={'superuser/pg_monitor' if env['capabilities']['is_superuser_or_monitor'] else '受限账号'}")

    print(f"[{now_iso()}] 采集 Snapshot A ...")
    snap_a = collect_snapshot(conn, ver_num, has_pgss)

    print(f"[{now_iso()}] 开始等待窗口 {args.interval_seconds} 秒，期间同步采样等待事件 (间隔 {args.ash_sample_interval}s) ...")
    ash_results = {}
    stop_event = threading.Event()
    ash_thread = threading.Thread(
        target=ash_sampler,
        args=(args.dsn, args.interval_seconds, args.ash_sample_interval, stop_event, ash_results),
        daemon=True,
    )
    ash_thread.start()
    ash_thread.join()

    print(f"[{now_iso()}] 采集 Snapshot B ...")
    try:
        snap_b = collect_snapshot(conn, ver_num, has_pgss)
        snapshot_b_ok = True
    except Exception as e:
        print(f"[{now_iso()}] Snapshot B 采集失败: {e}，报告将降级为仅基于 Snapshot A 的静态健康检查", file=sys.stderr)
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
