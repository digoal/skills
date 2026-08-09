#!/usr/bin/env python3
# kingbase-runtime-risk / run_scan.py
#
# KingbaseES（金仓）只读运行时风险扫描脚本（Python SDK 版，基于 psycopg2）。
# 输出与 run_scan.sh 完全一致（同名 CSV 文件），便于嵌入更大的诊断流水线。
#
# 依赖：psycopg2（pip install psycopg2-binary）
# 凭据：优先读取环境变量 PGPASSWORD；绝不把密码写入任何文件/日志。
#
# 连接参数解析优先级（与 SKILL.md「连接约定」一致）：
#   1. 命令行参数 -h/-p/-U/-d/--password
#   2. 环境变量 PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDBNAME|PGDATABASE
#   3. 缺省值 127.0.0.1 / 5432 / kingbase / kingbase / 123456
#
# 用法：
#   PGPASSWORD='xxx' ./run_scan.py [-h <host>] [-p <port>] [-U <user>] [-d <db>] [-o <outdir>]
#
# 安全说明：
#   - 所有查询都在 SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY 的
#     只读事务中执行，任何写操作都会被服务端拒绝。
#   - 每条检查项独立容错：失败只在该项 .err 中留痕并继续，不中断整体扫描。

import argparse
import csv
import os
import sys
from datetime import datetime

try:
    import psycopg2
except ImportError:
    sys.stderr.write("缺少 psycopg2 依赖，请先执行: pip install psycopg2-binary\n")
    sys.exit(1)

# 金仓内置 schema，扫描用户业务对象时统一过滤
KBUILTIN_SCHEMAS = (
    "sys_catalog", "pg_catalog", "information_schema", "sys_hm", "sysmac",
    "sysaudit", "src_restrict", "anon", "perf", "xlog_record_read",
    "dbms_job", "dbms_scheduler", "kdb_schedule", "pg_bitmapindex",
)
KBUILTIN_IN_SQL = ", ".join(f"'{s}'" for s in KBUILTIN_SCHEMAS)

# 每条检查项: (输出文件名, SQL)
CHECKS = [
    ("00_version_uptime.csv", """
        SELECT version() AS kdb_version,
               pg_postmaster_start_time() AS start_time,
               now() - pg_postmaster_start_time() AS uptime,
               pg_is_in_recovery() AS is_standby;
    """),
    ("00_key_settings.csv", """
        SELECT name, setting, unit, context
        FROM pg_settings
        WHERE name IN ('max_connections','max_wal_size','wal_keep_size','wal_keep_segments',
                       'archive_mode','archive_command','archive_timeout',
                       'autovacuum_freeze_max_age','vacuum_freeze_min_age','vacuum_freeze_table_age',
                       'autovacuum_max_workers','synchronous_commit','synchronous_standby_names',
                       'shared_preload_libraries');
    """),
    ("00_replication_slots.csv", """
        SELECT slot_name, slot_type, database, active, restart_lsn,
               pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) AS restart_lag_bytes,
               confirmed_flush_lsn
        FROM pg_replication_slots;
    """),
    ("00_wal_receiver.csv", """
        SELECT status, receive_start_lsn, received_lsn, last_msg_send_time,
               last_msg_receipt_time, latest_end_lsn, latest_end_time, slot_name, sender_host
        FROM pg_stat_wal_receiver;
    """),
    ("01_database_xid_age.csv", """
        SELECT datname, age(datfrozenxid) AS xid_age,
               pg_size_pretty(pg_database_size(datname)) AS db_size
        FROM pg_database
        WHERE datistemplate = false
        ORDER BY xid_age DESC;
    """),
    ("01_table_xid_age_top20.csv", f"""
        SELECT c.oid::regclass AS table_name,
               age(c.relfrozenxid) AS table_xid_age,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
        FROM pg_class c
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE c.relkind IN ('r','m','p')
          AND n.nspname NOT IN ({KBUILTIN_IN_SQL})
        ORDER BY table_xid_age DESC
        LIMIT 20;
    """),
    ("01_vacuum_progress.csv", """
        SELECT p.pid, p.datname, p.relid::regclass AS relation,
               p.phase, p.heap_blks_total, p.heap_blks_scanned, p.heap_blks_vacuumed,
               a.query_start, now() - a.query_start AS running_time
        FROM pg_stat_progress_vacuum p
        JOIN pg_stat_activity a ON p.pid = a.pid;
    """),
    ("03_freeze_storm_buckets.csv", f"""
        SELECT width_bucket(age(c.relfrozenxid), 0, 2000000000, 20) AS age_bucket,
               count(*) AS table_count,
               pg_size_pretty(sum(pg_total_relation_size(c.oid))) AS total_size,
               sum(pg_total_relation_size(c.oid)) AS total_size_bytes
        FROM pg_class c
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE c.relkind IN ('r','m','p')
          AND n.nspname NOT IN ({KBUILTIN_IN_SQL})
        GROUP BY age_bucket
        ORDER BY age_bucket DESC;
    """),
    ("04_physical_replication.csv", """
        SELECT application_name, client_addr, state, sync_state,
               pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) AS send_lag_bytes,
               pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn) AS write_lag_bytes,
               pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) AS flush_lag_bytes,
               pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes,
               write_lag, flush_lag, replay_lag
        FROM pg_stat_replication;
    """),
    ("04_logical_slots.csv", """
        SELECT s.slot_name, s.slot_type, s.database, s.active, s.restart_lsn,
               pg_wal_lsn_diff(pg_current_wal_lsn(), s.restart_lsn) AS restart_lag_bytes,
               s.confirmed_flush_lsn,
               CASE WHEN s.confirmed_flush_lsn IS NOT NULL
                    THEN pg_wal_lsn_diff(pg_current_wal_lsn(), s.confirmed_flush_lsn)
                    ELSE NULL END AS confirmed_flush_lag_bytes,
               r.application_name, r.client_addr, r.state
        FROM pg_replication_slots s
        LEFT JOIN pg_stat_replication r ON s.slot_name = r.application_name
        ORDER BY restart_lag_bytes DESC NULLS LAST;
    """),
    ("05_archiver_status.csv", """
        SELECT archived_count, failed_count,
               last_archived_wal, last_archived_time,
               last_failed_wal, last_failed_time
        FROM pg_stat_archiver;
    """),
    ("05_wal_dir.csv", """
        SELECT count(*) AS wal_file_count,
               pg_size_pretty(sum(size)) AS total_wal_size,
               sum(size) AS total_wal_size_bytes,
               pg_size_pretty(avg(size)::bigint) AS avg_file_size
        FROM pg_ls_waldir();
    """),
    ("06_connection_saturation.csv", """
        SELECT (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_connections,
               (SELECT setting::int FROM pg_settings WHERE name = 'superuser_reserved_connections') AS superuser_reserved,
               count(*) AS current_total,
               count(*) FILTER (WHERE state = 'active') AS active_count,
               count(*) FILTER (WHERE state = 'idle') AS idle_count,
               count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx_count,
               count(*) FILTER (WHERE state = 'idle in transaction (aborted)') AS idle_in_tx_aborted_count,
               count(*) FILTER (WHERE wait_event_type = 'Lock') AS waiting_on_lock_count,
               round(
                 100.0 * count(*) /
                 NULLIF((SELECT setting::int FROM pg_settings WHERE name = 'max_connections'), 0)
               , 1) AS usage_pct
        FROM pg_stat_activity
        WHERE backend_type = 'client backend';
    """),
    ("06_connection_by_database.csv", """
        SELECT datname, count(*) AS conn_count,
               count(*) FILTER (WHERE state = 'active') AS active_count,
               count(*) FILTER (WHERE state LIKE 'idle in transaction%') AS idle_in_tx_count
        FROM pg_stat_activity
        WHERE backend_type = 'client backend' AND datname IS NOT NULL
        GROUP BY datname
        ORDER BY conn_count DESC;
    """),
    ("06_connection_by_user.csv", """
        SELECT usename, count(*) AS conn_count,
               count(*) FILTER (WHERE state = 'active') AS active_count
        FROM pg_stat_activity
        WHERE backend_type = 'client backend' AND usename IS NOT NULL
        GROUP BY usename
        ORDER BY conn_count DESC;
    """),
    ("06_long_idle_in_transaction.csv", """
        SELECT pid, usename, datname, application_name, client_addr, state,
               now() - state_change AS idle_duration,
               now() - xact_start AS xact_duration,
               left(query, 200) AS last_query
        FROM pg_stat_activity
        WHERE state LIKE 'idle in transaction%'
        ORDER BY state_change ASC
        LIMIT 20;
    """),
    ("08_large_object_summary.csv", """
        SELECT count(DISTINCT loid) AS lo_count,
               pg_size_pretty(sum(octet_length(data))) AS total_lo_size,
               sum(octet_length(data)) AS total_lo_size_bytes
        FROM pg_largeobject;
    """),
    ("08_lo_reference_columns.csv", f"""
        SELECT n.nspname, c.relname, a.attname,
               format_type(a.atttypid, a.atttypmod) AS data_type
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE (a.atttypid = 'oid'::regtype OR a.atttypid = to_regtype('lo'))
          AND a.attnum > 0
          AND NOT a.attisdropped
          AND n.nspname NOT IN ({KBUILTIN_IN_SQL}, 'pg_toast')
          AND n.nspname NOT LIKE 'pg_toast_temp_%'
          AND n.nspname NOT LIKE 'pg_temp_%'
          AND c.relname NOT LIKE 'sys_stat_statements%';
    """),
    ("09_stats_staleness.csv", f"""
        SELECT
          n.nspname || '.' || c.relname AS table_name,
          pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
          c.reltuples::bigint AS reltuples_estimate,
          t.n_live_tup,
          t.n_dead_tup,
          t.n_mod_since_analyze,
          round(100.0 * t.n_dead_tup / NULLIF(t.n_live_tup + t.n_dead_tup, 0), 2) AS dead_tuple_pct,
          t.last_analyze,
          t.last_autoanalyze,
          eff.autovacuum_enabled,
          eff.scale_factor AS effective_scale_factor,
          eff.threshold AS effective_threshold,
          round((eff.scale_factor * c.reltuples + eff.threshold)::numeric) AS analyze_trigger_rows,
          round(
            (100.0 * t.n_mod_since_analyze /
             NULLIF(eff.scale_factor * c.reltuples + eff.threshold, 0))::numeric
          , 1) AS pct_of_trigger,
          CASE WHEN t.last_analyze IS NULL AND t.last_autoanalyze IS NULL
               THEN '从未分析过' ELSE NULL END AS never_analyzed_flag
        FROM pg_stat_user_tables t
        JOIN pg_class c ON c.oid = t.relid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        CROSS JOIN LATERAL (
          SELECT
            COALESCE(
              (SELECT (regexp_match(opt, 'autovacuum_analyze_scale_factor=([0-9.]+)'))[1]::numeric
               FROM unnest(COALESCE(c.reloptions, ARRAY[]::text[])) opt
               WHERE opt LIKE 'autovacuum_analyze_scale_factor=%'),
              current_setting('autovacuum_analyze_scale_factor')::numeric
            ) AS scale_factor,
            COALESCE(
              (SELECT (regexp_match(opt, 'autovacuum_analyze_threshold=([0-9]+)'))[1]::numeric
               FROM unnest(COALESCE(c.reloptions, ARRAY[]::text[])) opt
               WHERE opt LIKE 'autovacuum_analyze_threshold=%'),
              current_setting('autovacuum_analyze_threshold')::numeric
            ) AS threshold,
            COALESCE(
              (SELECT (regexp_match(opt, 'autovacuum_enabled=(true|false)'))[1]
               FROM unnest(COALESCE(c.reloptions, ARRAY[]::text[])) opt
               WHERE opt LIKE 'autovacuum_enabled=%'),
              'true'
            ) AS autovacuum_enabled
        ) eff
        WHERE c.relkind IN ('r','m','p')
          AND n.nspname NOT IN ({KBUILTIN_IN_SQL})
        ORDER BY pct_of_trigger DESC NULLS FIRST;
    """),
    ("09_never_analyzed.csv", f"""
        SELECT n.nspname || '.' || c.relname AS table_name,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
               t.n_live_tup
        FROM pg_stat_user_tables t
        JOIN pg_class c ON c.oid = t.relid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE t.last_analyze IS NULL
          AND t.last_autoanalyze IS NULL
          AND c.relkind IN ('r','m','p')
          AND n.nspname NOT IN ({KBUILTIN_IN_SQL})
        ORDER BY pg_total_relation_size(c.oid) DESC;
    """),
]

SEQUENCE_META_SQL = f"""
    SELECT n.nspname, c.relname, s.seqmax, s.seqincrement, s.seqcycle,
           format_type(s.seqtypid, null) AS data_type
    FROM pg_sequence s
    JOIN pg_class c ON s.seqrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname NOT IN ({KBUILTIN_IN_SQL})
    ORDER BY n.nspname, c.relname;
"""


def resolve_conn_args(args):
    """命令行参数 > 环境变量 > 默认值。"""
    return {
        "host": args.host or os.environ.get("PGHOST", "127.0.0.1"),
        "port": args.port or int(os.environ.get("PGPORT", "5432")),
        "user": args.user or os.environ.get("PGUSER", "kingbase"),
        "dbname": args.dbname
        or os.environ.get("PGDBNAME")
        or os.environ.get("PGDATABASE", "kingbase"),
        "password": args.password
        or os.environ.get("PGPASSWORD", "123456"),
    }


def set_session_readonly(conn):
    """连接后立即把会话默认事务设为只读（此后所有事务一律只读）。

    实测金仓 V9 只读事务对 DML 与 DDL（含超级用户）均会拒绝。
    autocommit 打开期间执行 SET，避免该 SET 自身开启一个读写事务。
    """
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
    finally:
        conn.autocommit = False


def run_readonly_query(conn, sql):
    """在只读事务中执行查询，返回 (列名列表, 行列表)。

    会话默认已是只读（见 set_session_readonly）；这里再显式 SET TRANSACTION
    READ ONLY 作为第一语句（当前事务的第一条语句，合法），双重保险。
    """
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SET statement_timeout = '30s'")
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return cols, rows


def write_csv(outdir, fname, cols, rows):
    path = os.path.join(outdir, fname)
    # lineterminator='\n' 与 psql --csv 输出保持一致（LF），便于 .sh/.py 两版输出逐字节对比
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
    return path


def run_sequence_risk(conn, outdir):
    """序列回卷：枚举用户 schema 的序列，取 last_value 并计算剩余调用次数与风险等级。"""
    seqs = []
    with conn.cursor() as cur:
        cur.execute(SEQUENCE_META_SQL)
        seqs = cur.fetchall()

    if not seqs:
        write_csv(outdir, "02_sequence_risk.csv", ["note"], [["当前实例(用户 schema)没有序列对象"]])
        return

    # 一次性取所有序列的 last_value（只读，不调用 nextval/setval）
    from psycopg2 import sql as psql

    union_parts = []
    for nsp, rel, _m, _i, _c, _t in seqs:
        full_name = f"{nsp}.{rel}"
        ident = psql.Identifier(nsp, rel)
        # seq_full_name 用字符串字面量（Literal），FROM 用限定标识符（Identifier）
        union_parts.append(
            psql.SQL("SELECT {name} AS seq_full_name, last_value FROM {rel}").format(
                name=psql.Literal(full_name), rel=ident
            )
        )
    combined = psql.SQL(" UNION ALL ").join(union_parts)

    last_values = {}
    try:
        with conn.cursor() as cur:
            cur.execute(combined)  # 会话默认已是只读（见 set_session_readonly）
            for row in cur.fetchall():
                last_values[row[0]] = row[1]
    except Exception as exc:  # 优雅降级：序列读取失败不影响整体扫描
        with open(os.path.join(outdir, "02_sequence_risk.csv.err"), "w", encoding="utf-8") as f:
            f.write(f"序列 last_value 读取失败: {exc}\n")
        return

    rows = []
    for nsp, rel, seqmax, seqincrement, seqcycle, data_type in seqs:
        full_name = f"{nsp}.{rel}"
        last_value = last_values.get(full_name)
        seqmax = int(seqmax)
        seqincrement = int(seqincrement)
        if seqcycle:
            risk = "循环序列(不回卷但可能重复)"
            remaining = None
        elif seqincrement < 0:
            # 递减序列的剩余次数需按 seqmin 人工评估，不参与自动判级
            risk = "降序序列(需人工评估)"
            remaining = None
        elif last_value is None or seqincrement == 0:
            risk = "未知(从未调用)"
            remaining = None
        else:
            remaining = (seqmax - int(last_value)) // seqincrement
            if remaining < 1000:
                risk = "🔴严重: 即将耗尽"
            elif remaining < 10000:
                risk = "🟠警告: 需尽快处理"
            elif remaining < 100000:
                risk = "🟡关注: 建议规划"
            else:
                risk = "🟢正常"
        rows.append([full_name, "t" if seqcycle else "f", last_value, remaining, risk, data_type])

    write_csv(outdir, "02_sequence_risk.csv",
              ["seq_full_name", "is_cycle", "last_value", "remaining_calls", "risk_level", "data_type"],
              rows)


def main():
    # -h 已被本脚本用作 --host，因此关闭 argparse 内置的 -h help（改用 --help）
    parser = argparse.ArgumentParser(description="KingbaseES 运行时风险只读扫描（psycopg2 版）",
                                     add_help=False)
    parser.add_argument("-h", "--host", help="主机（默认取 PGHOST / 127.0.0.1）")
    parser.add_argument("-p", "--port", type=int, help="端口（默认取 PGPORT / 5432）")
    parser.add_argument("-U", "--user", help="用户名（默认取 PGUSER / kingbase）")
    parser.add_argument("-d", "--dbname", help="数据库（默认取 PGDBNAME/PGDATABASE / kingbase）")
    parser.add_argument("--password", default=None,
                        help="密码（推荐使用 PGPASSWORD 环境变量，避免出现在命令行历史）")
    parser.add_argument("-o", "--outdir", help="输出目录（默认 ./kingbase_runtime_risk_output_<时间戳>）")
    parser.add_argument("--help", action="help", help="显示帮助")
    args = parser.parse_args()

    conn_args = resolve_conn_args(args)
    if not os.environ.get("PGPASSWORD") and not args.password:
        sys.stderr.write("[提示] 未设置 PGPASSWORD 环境变量，使用默认密码（仅适用于本地开发实例）\n")

    outdir = args.outdir or f"./kingbase_runtime_risk_output_{datetime.now():%Y%m%d_%H%M%S}"
    os.makedirs(outdir, exist_ok=True)

    print(f"==> 连接: host={conn_args['host']} port={conn_args['port']} "
          f"user={conn_args['user']} db={conn_args['dbname']}")
    print(f"==> 输出目录: {outdir}")

    try:
        conn = psycopg2.connect(connect_timeout=10, **conn_args)
    except Exception as exc:
        sys.stderr.write(f"无法连接 KingbaseES 实例: {exc}\n")
        sys.exit(2)

    set_session_readonly(conn)  # 会话默认只读（后续所有事务强制只读）

    try:
        for fname, sql in CHECKS:
            try:
                cols, rows = run_readonly_query(conn, sql)
                write_csv(outdir, fname, cols, rows)
            except Exception as exc:
                with open(os.path.join(outdir, f"{fname}.err"), "w", encoding="utf-8") as f:
                    f.write(f"{exc}\n")
                print(f"[提示] {fname} 执行时有告警/错误（常见原因：权限不足、扩展未安装，属预期内的优雅降级）", file=sys.stderr)

        try:
            run_sequence_risk(conn, outdir)
        except Exception as exc:
            with open(os.path.join(outdir, "02_sequence_risk.csv.err"), "w", encoding="utf-8") as f:
                f.write(f"{exc}\n")
            print("[提示] 02_sequence_risk 执行时有告警/错误（属预期内的优雅降级）", file=sys.stderr)
    finally:
        conn.close()

    print("==> 扫描完成，结果已保存至 " + outdir)
    print("==> 请检查各 *.err 文件，非空说明该检查项因权限/版本/扩展缺失被跳过（属正常优雅降级）")


if __name__ == "__main__":
    main()
