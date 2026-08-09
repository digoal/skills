#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
kingbase-top-sql-analyze / scripts / snapshot_diff.py
============================================================
KingbaseES（金仓）TOP SQL 两阶段快照采集 + 差值分析脚本。

功能：
  1. 前置条件检查（扩展 / track / max / 版本 / 字段探测）
  2. 采集快照1 -> 等待 interval -> 采集快照2
  3. 按 queryid 做差值，识别「数据不连续」记录
  4. 输出多维度 TOP SQL 排行（总耗时/单次最慢/执行频率/总IO/写放大/单次返回行数/总扫描行数）

兼容两种连接方式（--mode 可强制指定）：
  - sdk : python SDK 直连（优先 psycopg v3，其次 psycopg2）
  - psql: 调用 psql / ksql 子进程（shell command）
  - auto: 有 SDK 用 SDK，否则退化为 psql

连接参数优先级（与 SKILL.md 一致）：
  1. --dsn 连接串（最高优先，覆盖下面所有项）
  2. 命令行参数 --host/--port/--user/--password/--dbname
  3. 环境变量 PGHOST PGPORT PGDBNAME PGUSER PGPASSWORD
  4. 内置默认值 127.0.0.1:5432/kingbase/kingbase/123456

用法示例：
  # SDK 模式（psycopg2），等待 30 秒做两次快照差值
  export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=kingbase PGPASSWORD=123456 PGDBNAME=kingbase
  python3 snapshot_diff.py --interval-seconds 30 --top 10 --output diff.json

  # 强制 psql 子进程模式
  python3 snapshot_diff.py --mode psql --interval-seconds 30 --output diff.json

  # 仅前置检查
  python3 snapshot_diff.py --precheck-only

安全说明：
  - 密码只用于建立连接，不写入任何输出文件/日志；输出中的连接信息一律脱敏。
  - 全程只读（SELECT / SHOW / information_schema），不执行任何 DDL/DML。
  - 重置模式需同时传 --reset 与 --yes 才会执行 sys_stat_statements_reset()。
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

# --------------------------------------------------------------------------
# 内置默认连接参数（兜底）
# --------------------------------------------------------------------------
DEFAULTS = {
    "host": "127.0.0.1",
    "port": 5432,
    "user": "kingbase",
    "password": "123456",
    "dbname": "kingbase",
}

# sys_stat_statements 上我们关心的累计字段（动态探测后按需选用）
CUMULATIVE_FIELDS = [
    "calls", "total_exec_time", "total_plan_time", "rows",
    "shared_blks_hit", "shared_blks_read", "shared_blks_dirtied",
    "shared_blks_written", "local_blks_hit", "local_blks_read",
    "local_blks_dirtied", "local_blks_written",
    "temp_blks_read", "temp_blks_written", "blk_read_time", "blk_write_time",
    "wal_bytes", "wal_records",  # 未来 KES 版本若提供则自动纳入
]

# 排行维度定义（field 在探测不到时自动跳过该维度）
DIMENSIONS = [
    {"name": "total_time",    "title": "总耗时 TOP",           "field": "total_exec_time",     "filter": None,             "note": ""},
    {"name": "slow_mean",     "title": "单次最慢 TOP",         "field": "mean_exec_time",      "filter": "calls>=5",       "note": "过滤 calls<5 的偶发慢查询"},
    {"name": "frequency",     "title": "执行频率 TOP",         "field": "calls",               "filter": None,             "note": ""},
    {"name": "io_read",       "title": "总 IO 消耗 TOP",       "field": "shared_blks_read",    "filter": None,             "note": "磁盘读块数，缓存命中率低"},
    {"name": "write_amp",     "title": "写放大 TOP",           "field": "shared_blks_dirtied", "filter": None,             "note": "脏块数（KES 无 wal_bytes，以此近似 WAL 生成量）"},
    {"name": "rows_per_call", "title": "单次返回行数异常 TOP", "field": "rows_per_call",       "filter": "calls>=1",       "note": "疑似全表扫描返回大量行"},
    {"name": "total_rows",    "title": "总扫描行数 TOP",       "field": "rows",                "filter": None,             "note": ""},
]


# --------------------------------------------------------------------------
# 连接参数解析
# --------------------------------------------------------------------------
def resolve_conn(args):
    """1.命令行 -> 2.环境变量 -> 3.默认值"""
    env = os.environ
    return {
        "host": args.host or env.get("PGHOST") or DEFAULTS["host"],
        "port": int(args.port or env.get("PGPORT") or DEFAULTS["port"]),
        "user": args.user or env.get("PGUSER") or DEFAULTS["user"],
        "password": args.password or env.get("PGPASSWORD") or DEFAULTS["password"],
        "dbname": args.dbname or env.get("PGDBNAME") or DEFAULTS["dbname"],
    }


def mask_conn(c):
    return f"postgresql://{c['user']}:***@{c['host']}:{c['port']}/{c['dbname']}"


# --------------------------------------------------------------------------
# 连接后端抽象
# --------------------------------------------------------------------------
class SdkBackend:
    """python SDK 直连：优先 psycopg v3，其次 psycopg2"""

    def __init__(self, conn_params):
        self.params = conn_params
        self.psycopg = None
        self.version_tag = None
        try:
            import psycopg
            from psycopg.rows import dict_row as _dict_row
            self.psycopg = psycopg
            self._dict_row = _dict_row
            self.version_tag = "v3"
        except ImportError:
            try:
                import psycopg2
                import psycopg2.extras
                self.psycopg = psycopg2
                self.version_tag = "v2"
            except ImportError:
                raise RuntimeError(
                    "未找到 psycopg / psycopg2，请先安装：\n"
                    "  pip install psycopg2-binary --break-system-packages\n"
                    "或改用 psql 模式：--mode psql"
                )

    def query(self, sql, params=None):
        if self.version_tag == "v3":
            with self.psycopg.connect(
                host=self.params["host"], port=self.params["port"],
                user=self.params["user"], password=self.params["password"],
                dbname=self.params["dbname"], connect_timeout=10,
            ) as conn:
                with conn.cursor(row_factory=self._dict_row) as cur:
                    cur.execute(sql, params or ())
                    return [dict(r) for r in cur.fetchall()]
        else:
            conn = self.psycopg.connect(
                host=self.params["host"], port=self.params["port"],
                user=self.params["user"], password=self.params["password"],
                dbname=self.params["dbname"], connect_timeout=10,
            )
            try:
                cur = conn.cursor(cursor_factory=self.psycopg.extras.RealDictCursor)
                cur.execute(sql, params or ())
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()

    def backend_tag(self):
        return f"sdk({self.version_tag})"


class PsqlBackend:
    """psql / ksql 子进程模式（shell command）"""

    def __init__(self, conn_params):
        self.params = conn_params
        self.bin = shutil.which("ksql") or shutil.which("psql")
        if not self.bin:
            raise RuntimeError("未找到 psql / ksql 客户端，请安装后重试，或使用 --mode sdk")
        # 避免密码出现在命令行/进程列表：用 PGPASSWORD 环境变量传密码
        self.env = dict(os.environ)
        self.env["PGPASSWORD"] = conn_params["password"]
        self.env["PGHOST"] = str(conn_params["host"])
        self.env["PGPORT"] = str(conn_params["port"])
        self.env["PGUSER"] = conn_params["user"]
        self.env["PGDBNAME"] = conn_params["dbname"]

    def _run(self, sql, csv_out=False):
        if csv_out:
            full_sql = f"COPY ({sql}) TO STDOUT WITH (FORMAT csv)"
            cmd = [self.bin, "-h", self.params["host"], "-p", str(self.params["port"]),
                   "-U", self.params["user"], "-d", self.params["dbname"],
                   "-At", "-v", "ON_ERROR_STOP=1", "-c", full_sql]
        else:
            cmd = [self.bin, "-h", self.params["host"], "-p", str(self.params["port"]),
                   "-U", self.params["user"], "-d", self.params["dbname"],
                   "-At", "-v", "ON_ERROR_STOP=1", "-c", sql]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=self.env, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"psql 执行失败: {proc.stderr.strip()[:500]}")
        return proc.stdout

    def query(self, sql, params=None):
        """执行 SELECT，返回 list[dict]（用 COPY TO STDOUT CSV 保证字段内换行/逗号安全）"""
        if params:
            # 简单占位符替换（本脚本 SQL 均为静态拼好的字段列表，无外部输入，params 一般为空）
            raise RuntimeError("psql 模式不支持参数化查询")
        out = self._run(sql, csv_out=True)
        if not out.strip():
            return []
        rows = []
        for line in csv.reader(out.splitlines()):
            if len(line) == 1 and line[0] == "":
                continue
            rows.append({f"col{i}": v for i, v in enumerate(line)})
        return rows

    def scalar(self, sql):
        return self._run(sql).strip()

    def backend_tag(self):
        return "psql"


# --------------------------------------------------------------------------
# 探测与快照
# --------------------------------------------------------------------------
def probe_columns(bk):
    """动态探测 public.sys_stat_statements 的可用列"""
    sql = ("SELECT column_name FROM information_schema.columns "
           "WHERE table_schema='public' AND table_name='sys_stat_statements' "
           "ORDER BY ordinal_position")
    if isinstance(bk, SdkBackend):
        rows = bk.query(sql)
        return [r["column_name"] for r in rows]
    out = bk._run(sql)
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def precheck(bk):
    """返回元信息 dict；扩展缺失时抛出错误"""
    meta = {}
    if isinstance(bk, SdkBackend):
        r = bk.query("SHOW server_version_num")
        meta["server_version_num"] = r[0]["server_version_num"]
        r = bk.query("SELECT version() AS v")
        meta["server_version"] = r[0]["v"]
        ext = bk.query("SELECT extname, extversion FROM pg_extension WHERE extname='sys_stat_statements'")
        meta["extension"] = [dict(e) for e in ext]
        if not ext:
            raise RuntimeError(
                "检测到 sys_stat_statements 未启用。请在目标库执行：\n"
                "  1. kingbase.conf 中添加：shared_preload_libraries = 'sys_stat_statements'\n"
                "  2. 重启实例后执行：CREATE EXTENSION sys_stat_statements;\n"
                "  3. 建议同时设置：sys_stat_statements.track = 'all'\n"
                "完成后重新运行本次分析。")
        meta["track"] = bk.query("SHOW sys_stat_statements.track")[0]["sys_stat_statements.track"]
        meta["track_parse"] = bk.query("SHOW sys_stat_statements.track_parse")[0]["sys_stat_statements.track_parse"]
        meta["track_plan"] = bk.query("SHOW sys_stat_statements.track_plan")[0]["sys_stat_statements.track_plan"]
        meta["track_utility"] = bk.query("SHOW sys_stat_statements.track_utility")[0]["sys_stat_statements.track_utility"]
        meta["max"] = bk.query("SHOW sys_stat_statements.max")[0]["sys_stat_statements.max"]
        meta["track_io_timing"] = bk.query("SHOW track_io_timing")[0]["track_io_timing"]
        can = bk.query("SELECT (rolsuper OR rolreplication) AS c FROM pg_roles WHERE rolname=current_user")
        meta["likely_can_reset"] = bool(can[0]["c"]) if can else False
    else:
        def show(name):
            return bk.scalar(f"SHOW {name}")
        meta["server_version_num"] = show("server_version_num")
        meta["server_version"] = bk.scalar("SELECT version()")
        ext_out = bk.scalar("SELECT coalesce(string_agg(extname||' '||extversion, ','),'') FROM pg_extension WHERE extname='sys_stat_statements'")
        meta["extension"] = [{"extname": "sys_stat_statements", "extversion": ext_out.split()[-1]}] if ext_out else []
        if not ext_out:
            raise RuntimeError(
                "检测到 sys_stat_statements 未启用。请在目标库执行：\n"
                "  1. kingbase.conf 中添加：shared_preload_libraries = 'sys_stat_statements'\n"
                "  2. 重启实例后执行：CREATE EXTENSION sys_stat_statements;\n"
                "  3. 建议同时设置：sys_stat_statements.track = 'all'\n"
                "完成后重新运行本次分析。")
        meta["track"] = show("sys_stat_statements.track")
        meta["track_parse"] = show("sys_stat_statements.track_parse")
        meta["track_plan"] = show("sys_stat_statements.track_plan")
        meta["track_utility"] = show("sys_stat_statements.track_utility")
        meta["max"] = show("sys_stat_statements.max")
        meta["track_io_timing"] = show("track_io_timing")
        meta["likely_can_reset"] = bk.scalar("SELECT (rolsuper OR rolreplication) FROM pg_roles WHERE rolname=current_user") == "t"
    meta["columns"] = probe_columns(bk)
    meta["skipped_dimensions"] = []
    # 从完整 version() 串中提取简短标签，如 "KingbaseES V009R001C010"
    v = meta.get("server_version") or ""
    meta["server_version_short"] = " ".join(v.split(",")[0].split(" on ")[0].split()[:2])
    return meta


def build_snapshot_sql(columns):
    """按探测到的列动态构造采集 SQL（psql 模式列名 col0.. 由调用方映射）"""
    sel = [
        "s.queryid", "LEFT(s.query, 500) AS query_text", "a.rolname AS username",
    ]
    for f in CUMULATIVE_FIELDS:
        if f in columns:
            sel.append(f"s.{f}")
    sel.append("s.total_exec_time / NULLIF(s.calls, 0) AS mean_exec_time_raw")
    return (
        "SELECT " + ", ".join(sel) + "\n"
        "FROM public.sys_stat_statements s\n"
        "JOIN pg_authid a ON a.oid = s.userid\n"
        "WHERE s.queryid IS NOT NULL\n"
        "ORDER BY s.total_exec_time DESC"
    )


def snapshot(bk, columns):
    """采集一次快照，返回 (list[dict], snapshot_time)
    SDK 模式返回 3 元组 (rows, t, 0) 保持签名一致。"""
    sql = build_snapshot_sql(columns)
    if isinstance(bk, SdkBackend):
        rows = bk.query(sql)
        t = datetime.now().isoformat(timespec="seconds")
        return rows, t, 0
    # psql 模式：先取时间戳，再取数据（COPY CSV，列顺序由 SQL 固定）
    t = bk.scalar("SELECT clock_timestamp()::text")
    out = bk._run(sql, csv_out=True)
    # 列名与 SQL 中 SELECT 列表对应
    headers = ["queryid", "query_text", "username"] + [f for f in CUMULATIVE_FIELDS if f in columns] + ["mean_exec_time_raw"]
    rows = []
    malformed = 0
    if out.strip():
        for line in csv.reader(out.splitlines()):
            if len(line) == len(headers):
                rows.append(dict(zip(headers, line)))
            elif len(line) == len(headers) - 1:  # 容忍尾部空列被裁剪（CSV 尾列为空时常见）
                rows.append(dict(zip(headers, line + [None])))
            else:
                malformed += 1
    if malformed:
        print(f"    ⚠️  psql 模式解析出 {malformed} 行字段数与列头不一致，已跳过（请留意 query 文本中的特殊字符）", file=sys.stderr)
    return rows, t, malformed


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def compute_diff(snap1, snap2, columns):
    """按 queryid 做差值，返回 diff 行列表与统计信息"""
    s1 = {r["queryid"]: r for r in snap1}
    s2 = {r["queryid"]: r for r in snap2}
    diff_rows, non_continuous, only_in_1, only_in_2 = [], [], [], 0
    for qid, r2 in s2.items():
        r1 = s1.get(qid)
        if r1 is None:
            only_in_2 += 1
            continue
        d = {"queryid": qid, "query_text": r2.get("query_text") or r1.get("query_text"),
             "username": r2.get("username") or r1.get("username")}
        for f in CUMULATIVE_FIELDS:
            if f not in columns:
                continue
            v1, v2 = to_float(r1.get(f)), to_float(r2.get(f))
            d[f + "_delta"] = v2 - v1
            d[f] = v2  # 保留快照2绝对值
        # 数据不连续判定：核心累计字段倒退
        if d.get("calls_delta", 0) < 0 or d.get("total_exec_time_delta", 0) < 0:
            non_continuous.append(qid)
            continue
        if d.get("calls_delta", 0) == 0:
            continue
        d["mean_exec_time"] = d["total_exec_time_delta"] / d["calls_delta"]
        d["rows_per_call"] = d["rows_delta"] / d["calls_delta"]
        hit = d.get("shared_blks_hit_delta", 0)
        read = d.get("shared_blks_read_delta", 0)
        d["cache_hit_ratio"] = hit / (hit + read) if (hit + read) > 0 else None
        diff_rows.append(d)
    for qid in s1:
        if qid not in s2:
            only_in_1.append(qid)
    stats = {
        "snapshot1_rows": len(s1),
        "snapshot2_rows": len(s2),
        "diff_rows": len(diff_rows),
        "non_continuous": len(non_continuous),
        "disappeared_in_snapshot2": len(only_in_1),
        "new_in_snapshot2": only_in_2,
    }
    return diff_rows, stats


def build_rankings(diff_rows, columns, top_n):
    """7 个维度各取 TOP N；字段缺失的维度跳过"""
    result, skipped = [], []
    for dim in DIMENSIONS:
        field = dim["field"]
        if field in ("rows_per_call", "mean_exec_time"):
            key = lambda r: r.get(field) or 0  # noqa: E731
        else:
            if field not in columns:
                skipped.append({"name": dim["name"], "title": dim["title"],
                                "reason": f"字段 {field} 不存在于本实例 sys_stat_statements"})
                continue
            key = lambda r, f=field + "_delta": r.get(f) or 0  # noqa: E731
        items = [r for r in diff_rows if key(r) > 0]
        if dim["filter"] == "calls>=5":
            items = [r for r in items if (r.get("calls_delta") or 0) >= 5]
        elif dim["filter"] == "calls>=1":
            items = [r for r in items if (r.get("calls_delta") or 0) >= 1]
        items.sort(key=key, reverse=True)
        out = []
        for i, r in enumerate(items[:top_n], 1):
            out.append({
                "rank": i,
                "queryid": r["queryid"],
                "query_text": (r.get("query_text") or "")[:500],
                "username": r.get("username"),
                "calls_delta": int(r.get("calls_delta") or 0),
                "mean_exec_time_ms": round(r.get("mean_exec_time") or 0, 3),
                "total_exec_time_ms": round(r.get("total_exec_time_delta") or 0, 3),
                "rows_delta": int(r.get("rows_delta") or 0),
                "rows_per_call": round(r.get("rows_per_call") or 0, 1),
                "cache_hit_ratio": round(r["cache_hit_ratio"], 4) if r.get("cache_hit_ratio") is not None else None,
                "shared_blks_hit_delta": int(r.get("shared_blks_hit_delta") or 0),
                "shared_blks_read_delta": int(r.get("shared_blks_read_delta") or 0),
                "shared_blks_dirtied_delta": int(r.get("shared_blks_dirtied_delta") or 0),
                "temp_blks_written_delta": int(r.get("temp_blks_written_delta") or 0),
                "blk_read_time_ms": round(r.get("blk_read_time_delta") or 0, 3),
                "blk_write_time_ms": round(r.get("blk_write_time_delta") or 0, 3),
            })
        result.append({"name": dim["name"], "title": dim["title"], "top_n": top_n, "items": out, "note": dim["note"]})
    return result, skipped


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="KingbaseES TOP SQL 两阶段快照差值分析")
    ap.add_argument("--host"); ap.add_argument("--port", type=int)
    ap.add_argument("--user"); ap.add_argument("--password"); ap.add_argument("--dbname")
    ap.add_argument("--dsn", help="postgresql:// 形式连接串（可选，优先级最高）")
    ap.add_argument("--interval-seconds", type=int, default=600, help="两次快照间隔秒数，默认 600")
    ap.add_argument("--top", type=int, default=10, help="每个维度 TOP N，默认 10")
    ap.add_argument("--mode", choices=["auto", "sdk", "psql"], default="auto")
    ap.add_argument("--output", help="输出 JSON 文件路径（缺省仅打印摘要）")
    ap.add_argument("--precheck-only", action="store_true", help="仅执行前置检查")
    ap.add_argument("--reset", action="store_true", help="采集快照1后执行 sys_stat_statements_reset()（危险，需配合 --yes）")
    ap.add_argument("--yes", action="store_true", help="确认执行危险操作")
    args = ap.parse_args()

    params = resolve_conn(args)
    if args.dsn:
        from urllib.parse import urlparse, unquote
        p = urlparse(args.dsn)
        if p.hostname: params["host"] = p.hostname
        if p.port: params["port"] = p.port
        if p.username: params["user"] = unquote(p.username)
        if p.password: params["password"] = unquote(p.password)
        if p.path and p.path != "/": params["dbname"] = p.path.lstrip("/")

    # 选择后端
    if args.mode == "sdk":
        bk = SdkBackend(params)
    elif args.mode == "psql":
        bk = PsqlBackend(params)
    else:
        try:
            bk = SdkBackend(params)
        except RuntimeError:
            bk = PsqlBackend(params)

    print(f"== 连接: {mask_conn(params)}  后端: {bk.backend_tag()} ==")

    meta = precheck(bk)
    print(f"== 预检通过: {meta['server_version_short']} (server_version_num={meta['server_version_num']}) "
          f"track={meta['track']} max={meta['max']} track_io_timing={meta['track_io_timing']}")
    if meta["track"] != "all":
        print(f"⚠️  sys_stat_statements.track = {meta['track']}（非 all），函数/存储过程内部的非顶层语句可能采集不到")
    if meta["track_io_timing"] == "off":
        print("⚠️  track_io_timing = off，blk_read_time / blk_write_time 恒为 0（IO 耗时维度不可用）")

    if args.precheck_only:
        print("== 可用列: " + ", ".join(meta["columns"]))
        sys.exit(0)

    if args.reset and not args.yes:
        print("⚠️  --reset 会清空该实例全局 sys_stat_statements 统计历史，必须同时加 --yes 确认。已中止。")
        sys.exit(2)

    # 快照 1
    print(f"== 采集快照 1 ...")
    snap1, t1, malformed1 = snapshot(bk, meta["columns"])
    print(f"   快照 1 完成：{len(snap1)} 条记录 @ {t1}")

    if args.reset:
        print("⚠️  执行 sys_stat_statements_reset() ...")
        if isinstance(bk, SdkBackend):
            bk.query("SELECT public.sys_stat_statements_reset()")
        else:
            bk.scalar("SELECT public.sys_stat_statements_reset()")

    if args.interval_seconds > 0:
        print(f"== 等待 {args.interval_seconds} 秒后采集快照 2 ...")
        time.sleep(args.interval_seconds)

    snap2, t2, malformed2 = snapshot(bk, meta["columns"])
    print(f"   快照 2 完成：{len(snap2)} 条记录 @ {t2}")

    diff_rows, stats = compute_diff(snap1, snap2, meta["columns"])
    stats["malformed_psql_rows"] = malformed1 + malformed2
    rankings, skipped = build_rankings(diff_rows, meta["columns"], args.top)
    meta["skipped_dimensions"] = skipped

    if stats["non_continuous"] > 0:
        print(f"⚠️  剔除数据不连续记录 {stats['non_continuous']} 条（期间发生过 reset 或语句被淘汰）")

    result = {
        "skill": "kingbase-top-sql-analyze",
        "backend": bk.backend_tag(),
        "connection": mask_conn(params),
        "metadata": {
            "server_version": meta["server_version"],
            "server_version_short": meta["server_version_short"],
            "server_version_num": meta["server_version_num"],
            "extension": meta["extension"],
            "track": meta["track"],
            "track_parse": meta["track_parse"],
            "track_plan": meta["track_plan"],
            "track_utility": meta["track_utility"],
            "track_io_timing": meta["track_io_timing"],
            "sys_stat_statements_max": meta["max"],
            "snapshot1_time": t1,
            "snapshot2_time": t2,
            "interval_seconds": args.interval_seconds,
            "stats": stats,
            "skipped_dimensions": skipped,
        },
        "dimensions": rankings,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"== 结果已写入: {args.output}")

    # 打印摘要
    print("\n===== TOP SQL 排行摘要 =====")
    for dim in rankings:
        print(f"\n--- {dim['title']} (TOP {dim['top_n']}) {dim['note']} ---")
        if not dim["items"]:
            print("   (无数据)")
        for it in dim["items"]:
            txt = (it["query_text"] or "").replace("\n", " ")[:70]
            print(f"  #{it['rank']:<2} calls={it['calls_delta']:<8} mean={it['mean_exec_time_ms']:>10.2f}ms "
                  f"total={it['total_exec_time_ms']:>12.2f}ms rows={it['rows_delta']:<8} | {txt}")
    if skipped:
        print("\n== 跳过的维度 ==")
        for s in skipped:
            print(f"  - {s['title']}: {s['reason']}")


if __name__ == "__main__":
    main()
