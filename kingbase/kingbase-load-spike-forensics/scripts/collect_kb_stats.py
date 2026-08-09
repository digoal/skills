#!/usr/bin/env python3
# kingbase-load-spike-forensics: 数据库侧只读取证脚本（Python SDK 版）
#
# 用法:
#   export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGPASSWORD=123456 PGDATABASE=kingbase
#   ./collect_kb_stats.py [output_dir]
#
# 依赖: psycopg2 (pip install psycopg2-binary)
#
# 行为与 collect_kb_stats.sql 等价：把脚本里的每段 \echo ... SELECT 输出
# 单独写到 output_dir 下的 *.txt 文件，便于在大型取证场景下分文件存档与 diff。

import argparse
import os
import sys
from datetime import datetime

try:
    import psycopg2
except ImportError:
    sys.stderr.write("缺少 psycopg2 依赖，请先执行: pip install psycopg2-binary\n")
    sys.exit(1)


# 与 collect_kb_stats.sql 中每节 \echo ... SELECT 一一对应
SECTIONS = [
    ("00_env_image", """
        SELECT version();
    """, "环境画像: version()"),
    ("00_settings", """
        SELECT name, setting FROM pg_settings
        WHERE name IN ('timezone','log_timezone','shared_buffers','work_mem',
                       'max_connections','checkpoint_timeout','max_wal_size',
                       'autovacuum','track_io_timing','log_destination',
                       'log_directory','log_filename','logging_collector',
                       'log_min_duration_statement');
    """, "关键 GUC 参数"),
    ("00_extensions", """
        SELECT extname, extversion FROM pg_extension
        WHERE extname IN ('sys_stat_statements','sys_kwr','sys_ksh','sysaudit',
                          'sysmac','sys_hm','auto_explain')
        ORDER BY extname;
    """, "已装扩展"),
    ("01_session_state_distribution", """
        SELECT state, wait_event_type, wait_event, count(*)
        FROM pg_stat_activity
        GROUP BY 1,2,3
        ORDER BY count(*) DESC;
    """, "会话状态 × 等待事件分布"),
    ("02_active_sessions", """
        SELECT pid, usename, datname, state, wait_event_type, wait_event,
               now() - query_start AS running_for,
               now() - xact_start  AS xact_running_for,
               left(query, 150) AS query
        FROM pg_stat_activity
        WHERE state <> 'idle'
        ORDER BY running_for DESC NULLS LAST
        LIMIT 50;
    """, "活跃/长事务会话"),
    ("03_lock_chain", """
        SELECT blocked_locks.pid       AS blocked_pid,
               blocking_locks.pid      AS blocking_pid,
               blocked_activity.usename AS blocked_user,
               blocking_activity.usename AS blocking_user,
               left(blocked_activity.query, 100)  AS blocked_query,
               left(blocking_activity.query, 100) AS blocking_query,
               now() - blocked_activity.query_start AS blocked_duration
        FROM pg_catalog.pg_locks blocked_locks
        JOIN pg_catalog.pg_locks blocking_locks
          ON blocking_locks.locktype = blocked_locks.locktype
         AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
         AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
         AND blocking_locks.pid != blocked_locks.pid
        JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
        JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
        WHERE NOT blocked_locks.granted;
    """, "阻塞锁链"),
    ("04_db_throughput", """
        SELECT datname, numbackends, xact_commit, xact_rollback,
               blks_read, blks_hit,
               round(blks_hit::numeric / nullif(blks_hit + blks_read, 0), 4) AS hit_ratio,
               tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
               temp_files, temp_bytes, deadlocks, conflicts, stats_reset
        FROM pg_stat_database
        ORDER BY numbackends DESC;
    """, "数据库级吞吐"),
    ("05_bgwriter", "SELECT * FROM pg_stat_bgwriter;", "后台写/检查点"),
    ("06_replication", """
        SELECT client_addr, state, sync_state,
               sent_lsn, write_lsn, flush_lsn, replay_lsn,
               write_lag, flush_lag, replay_lag
        FROM pg_stat_replication;
    """, "复制状态"),
    ("07_table_bloat_top", """
        SELECT schemaname, relname, n_dead_tup, n_live_tup,
               round(n_dead_tup::numeric / nullif(n_live_tup + n_dead_tup, 0), 4) AS dead_ratio,
               last_autovacuum, last_autoanalyze, autovacuum_count, analyze_count
        FROM pg_stat_user_tables
        ORDER BY n_dead_tup DESC
        LIMIT 20;
    """, "表膨胀 Top 20"),
    ("08_progress_vacuum", "SELECT * FROM pg_stat_progress_vacuum;", "正在进行的 vacuum"),
    ("09_kbextra_sys_stat_sql_top", """
        SELECT s.datname, s.username, s.queryid,
               left(s.query, 120) AS query,
               s.calls,
               round(s.db_time::numeric/1000, 1) AS db_time_ms,
               round(s.db_cpu::numeric/1000, 1)  AS db_cpu_ms,
               round(s.db_wait::numeric/1000, 1) AS db_wait_ms,
               s.total_db_time_pct, s.cpu_time_pct, s.wait_time_pct,
               s.wait_event_1, s.wait_calls_1,
               round(s.wait_time_1::numeric/1000, 1) AS wait_time_1_ms,
               s.wait_event_2,
               round(s.parse_time::numeric/1000, 1) AS parse_time_ms,
               round(s.plan_time::numeric/1000, 1)  AS plan_time_ms,
               round(s.exec_time::numeric/1000, 1)  AS exec_time_ms,
               s.wal_size,
               s.shared_blks_read_size, s.shared_blks_write_size,
               s.temp_blks_read_size, s.temp_blks_write_size,
               s.shared_blks_hit
        FROM sys_catalog.sys_stat_sql s
        ORDER BY s.db_time DESC
        LIMIT 20;
    """, "KB-extra: sys_stat_sql 全维度 SQL 画像 Top 20"),
    ("10_kbextra_sys_stat_wait_top", """
        SELECT event_type, wait_event, calls, total_time,
               round(avg_time::numeric, 2) AS avg_time,
               round(dbtime_pct::numeric, 2) AS dbtime_pct
        FROM sys_catalog.sys_stat_wait
        ORDER BY total_time DESC
        LIMIT 20;
    """, "KB-extra: sys_stat_wait 等待事件分布"),
    ("11_kbextra_sys_stat_sqlwait_matrix", """
        SELECT s.username, s.datname::text AS datname, s.queryid,
               left(s.query, 80) AS query,
               w.wait_event_type, w.wait_event, w.calls,
               round(w.times::numeric/1000, 1) AS times_ms
        FROM sys_catalog.sys_stat_sqlwait w
        JOIN sys_catalog.sys_stat_sql s USING (userid, datid, queryid)
        WHERE w.calls > 0
        ORDER BY w.calls DESC
        LIMIT 30;
    """, "KB-extra: SQL × 等待事件 矩阵"),
    ("12_kbextra_wal_buffer", """
        SELECT name, bytes, utilization_rate, write_rate,
               written_to_lsn, written_to_lsn - copied_to_lsn AS unwritten_lsn
        FROM sys_catalog.sys_stat_wal_buffer;
    """, "KB-extra: WAL buffer 状态"),
    ("13_kbextra_sqlcount", """
        SELECT datid::text, sql_type, background, sum(calls) AS calls, sum(times) AS times
        FROM sys_catalog.sys_stat_sqlcount
        GROUP BY 1,2,3
        ORDER BY calls DESC
        LIMIT 20;
    """, "KB-extra: SQL 类型 × 调用次数"),
    ("14_pg_stat_statements_top", """
        SELECT left(query, 120) AS query, calls, total_exec_time, mean_exec_time, rows,
               shared_blks_hit, shared_blks_read, temp_blks_written
        FROM sys_stat_statements
        ORDER BY total_exec_time DESC
        LIMIT 20;
    """, "PG 兼容 sys_stat_statements Top 20"),
    ("15_awr_history_avail", """
        SELECT
          (SELECT count(*) FROM sys_catalog.sys_stat_sysmetric_history) AS sysmetric_history_rows,
          (SELECT count(*) FROM sys_catalog.sys_stat_metric_history)     AS metric_history_rows,
          (SELECT min(begin_time) FROM sys_catalog.sys_stat_sysmetric_history) AS sysmetric_min_time,
          (SELECT max(begin_time) FROM sys_catalog.sys_stat_sysmetric_history) AS sysmetric_max_time;
    """, "AWR 风格历史仓库可用性"),
    ("16_awr_sysmetric_recent", """
        SELECT begin_time, metric_name, metric_unit, metric_value, abs_value
        FROM sys_catalog.sys_stat_sysmetric_history
        ORDER BY begin_time DESC
        LIMIT 5;
    """, "AWR sysmetric 最近 5 行"),
]


def fetch_dict(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return cols, rows


def format_table(cols, rows, max_col_width=40):
    # 计算每列宽度：当 rows 为空时必须走"只考虑列名"的分支，否则
    # max(len(c), *<empty>) 在 Python 解释器层面会变成 max(len(c))，
    # 进而被当作 max(iterable) 触发 'int is not iterable'。
    if rows:
        widths = {c: min(max_col_width,
                         max([len(c)] + [len(str(r[i])) if r[i] is not None else 0 for r in rows]))
                  for i, c in enumerate(cols)}
    else:
        widths = {c: min(max_col_width, len(c)) for c in cols}
    sep = "+" + "+".join("-" * (widths[c] + 2) for c in cols) + "+"
    lines = [sep]
    lines.append("| " + " | ".join(c.ljust(widths[c]) for c in cols) + " |")
    lines.append(sep)
    for r in rows:
        lines.append("| " + " | ".join(
            (str(v) if v is not None else "").replace("\n", " ")[:widths[c]].ljust(widths[c])
            for c, v in zip(cols, r)
        ) + " |")
    lines.append(sep)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="KingbaseES 取证快照采集（psycopg2）")
    parser.add_argument("output_dir", nargs="?", default=None,
                        help="输出目录；默认 ./kb_forensic_<时间戳>/")
    parser.add_argument("--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PGPORT", "5432")))
    parser.add_argument("--user", default=os.environ.get("PGUSER", "kingbase"))
    parser.add_argument("--password",
                        default=os.environ.get("PGPASSWORD", "123456"),
                        help="PGPASSWORD 环境变量或显式传入")
    parser.add_argument("--dbname",
                        default=os.environ.get("PGDATABASE", "kingbase"))
    args = parser.parse_args()

    out_dir = args.output_dir or f"kb_forensic_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(out_dir, exist_ok=True)
    print(f"==> 输出目录: {out_dir}")

    conn = psycopg2.connect(
        host=args.host, port=args.port, user=args.user,
        password=args.password, dbname=args.dbname, connect_timeout=10,
    )
    conn.autocommit = True

    for name, sql, title in SECTIONS:
        path = os.path.join(out_dir, f"{name}.txt")
        try:
            with conn.cursor() as cur:
                cols, rows = fetch_dict(cur, sql)
            with open(path, "w") as f:
                f.write(f"=== {title} ===\n")
                f.write(format_table(cols, rows))
                f.write("\n")
            print(f"  [ok] {title} -> {path}  ({len(rows)} rows)")
        except Exception as exc:
            with open(path, "w") as f:
                f.write(f"=== {title} ===\n[ERROR] {exc}\n")
            print(f"  [!!] {title} -> {path}  ERROR: {exc}", file=sys.stderr)

    conn.close()
    print()
    print("==> 采集完成。请结合 OS 层 collect_os_metrics.sh 输出做时间线对齐分析。")


if __name__ == "__main__":
    main()