#!/usr/bin/env python3
# kingbase-log-analyzer: csvlog 结构化日志解析器（Python 标准库，仅 csv/gzip/re 模块）
#
# KingbaseES 开启 csvlog（log_destination 含 csvlog）后，每行是一条标准 CSV 记录，
# 字段可能包含内嵌逗号/引号/换行（如 query 字段里的多行 SQL），因此【禁止用 grep/awk 按行硬切】，
# 必须用 Python csv 模块解析。
#
# 本脚本特性：
#   - 动态读取 csvlog 文件头作为列名（DictReader），兼容不同版本的 Kingbase 列布局；
#     若文件没有表头，则回退到 PG12 兼容的默认列名。
#   - 支持 .csv 与 .csv.gz 压缩轮转文件（自动识别）。
#   - 按 log_time 时间段过滤；时间字符串可带时区名（如 "2026-08-09 09:00:45.981 UTC"）。
#   - 按 skill Step 4 的分类维度统计：错误/致命、崩溃恢复、慢查询、锁死锁、连接认证、
#     checkpoint、autovacuum、临时文件、复制/WAL/归档、配置变更、金仓审计 attention。
#   - 输出 query/message 时对字面量脱敏（保留 SQL 结构）。
#
# 用法示例：
#   ./parse_csvlog.py /path/to/sys_log/kingbase-*.csv
#   ./parse_csvlog.py /path/to/sys_log --since "2026-08-09 09:00:00" --until "2026-08-09 10:00:00"
#   ./parse_csvlog.py /path/to/sys_log/kingbase-2026-08-09_090045.csv --json
#
# 配套开启 csvlog 的方法见 enable_csvlog.sql / enable_csvlog.py（psql 版 / Python 版）。

import argparse
import csv
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量：PG12 兼容的 csvlog 默认列名（Kingbase 与此高度一致；文件有表头时以表头为准）
# ---------------------------------------------------------------------------
DEFAULT_COLUMNS = [
    "log_time", "user_name", "database_name", "process_id", "session_id",
    "session_line_num", "command_tag", "session_start_time", "virtual_transaction_id",
    "transaction_id", "error_severity", "sql_state_code", "message", "detail",
    "hint", "internal_query", "internal_position", "context", "query", "query_pos",
    "location", "application_name",
]

TZ_NAME_RE = re.compile(r"\s+(UTC|GMT|CST|PDT|PST|EDT|EST|JST|[+-]\d{2}:?\d{2}|[A-Z]{2,5})$")

# skill Step 4 的分类规则（在 message 字段上做子串匹配）
RULE_CRASH = re.compile(r"database system was (interrupted|not properly shut down)|automatic recovery in progress|redo starts at|database system is ready")
RULE_SLOW = re.compile(r"^\s*duration:\s*([\d.]+)\s*ms", re.I)
RULE_DEADLOCK = re.compile(r"deadlock detected|still waiting for")
RULE_CONN = re.compile(r"connection authorized|connection received|password authentication failed|too many connections|terminating connection|unexpected EOF")
RULE_CHECKPOINT = re.compile(r"checkpoint (starting|complete)")
RULE_AUTOVACUUM = re.compile(r"automatic (vacuum|analyze) of table|to prevent wraparound")
RULE_TEMPFILE = re.compile(r"temporary file:")
RULE_WAL = re.compile(r"streaming replication|archive command failed|could not receive data from WAL stream|config the real archive_command")
RULE_CONFIG = re.compile(r"ALTER SYSTEM|received SIGHUP|parameter .* changed to|reloading configuration files")
RULE_KB_AUDIT = re.compile(r"attention:")

# ---------------------------------------------------------------------------
# 解析工具
# ---------------------------------------------------------------------------
def iter_csv_rows(path):
    """逐文件产出 (文件路径, 列名, 行字典)；自动处理 .gz 与表头。"""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            return
        # 表头判断：首行是否像列名（含 log_time 或 error_severity 等）
        if any(k in str(h) for h in header[:5]
               for k in ("log_time", "severity", "database_name", "process_id")):
            colnames = [h.strip() for h in header]
        else:
            # 无表头（或首行就是数据）→ 回退默认列名，并把首行当数据处理
            colnames = DEFAULT_COLUMNS
            yield path, colnames, dict(zip(colnames, header))
        for raw in reader:
            row = dict(zip(colnames, raw))
            yield path, colnames, row


def parse_log_time(value):
    """解析 csvlog 的 log_time（形如 '2026-08-09 09:00:45.981 UTC'）。
    返回 naive datetime（时区名被忽略，由 --tz 决定如何解释），失败返回 None。"""
    if not value:
        return None
    s = str(value).strip()
    s = TZ_NAME_RE.sub("", s)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def mask_literal(text, max_len=200):
    """对 SQL/消息脱敏：替换单引号字符串字面量、密码类片段，保留结构。"""
    if not text:
        return text
    t = str(text)
    # 字符串字面量 'xxx' → '***'
    t = re.sub(r"'[^']*'", "'***'", t)
    # 密码显式出现在消息里（如连接串 /user:pass@host）
    t = re.sub(r"(://[^:/@]+):[^@/]+@", r"\1:***@", t)
    t = re.sub(r"\s+", " ", t)
    return t[:max_len]


# ---------------------------------------------------------------------------
# 分类与统计
# ---------------------------------------------------------------------------
def classify(message):
    """返回事件所属类别；慢查询额外返回时长 ms。"""
    m = (message or "").strip()
    cats = []
    slow_ms = None
    sm = RULE_SLOW.match(m)
    if sm:
        slow_ms = float(sm.group(1))
        cats.append("慢查询")
    for name, rule in [
        ("崩溃恢复", RULE_CRASH), ("锁与死锁", RULE_DEADLOCK),
        ("连接认证", RULE_CONN), ("checkpoint", RULE_CHECKPOINT),
        ("autovacuum", RULE_AUTOVACUUM), ("临时文件", RULE_TEMPFILE),
        ("复制/WAL/归档", RULE_WAL), ("配置变更", RULE_CONFIG),
        ("金仓审计", RULE_KB_AUDIT),
    ]:
        if rule.search(m):
            cats.append(name)
    return cats, slow_ms


def aggregate(rows, since=None, until=None):
    """rows: (path, colnames, row) 迭代器；返回统计结果字典。"""
    stats = {
        "总事件数": 0,
        "级别分布": Counter(),
        "错误Top": Counter(),
        "慢查询Top": [],          # (ms, masked_query_or_message, 次数聚合)
        "慢查询聚合": defaultdict(lambda: {"count": 0, "max_ms": 0.0, "total_ms": 0.0}),
        "分类计数": Counter(),
        "认证失败": Counter(),
        "时间线": [],             # (time, severity, category, masked)
        "死亡/崩溃次数": 0,
        "死锁次数": 0,
        "临时文件次数": 0,
        "归档失败次数": 0,
    }
    for path, colnames, row in rows:
        t = parse_log_time(row.get("log_time"))
        if t is not None:
            if since is not None and t < since:
                continue
            if until is not None and t > until:
                continue
        elif since is not None or until is not None:
            # 时间不可解析但指定了时间范围 → 无法判定，跳过统计但保留计数不精确
            continue

        severity = (row.get("error_severity") or "").strip() or "LOG"
        message = row.get("message") or ""
        query = row.get("query") or ""
        sqlstate = row.get("sql_state_code") or ""
        user = row.get("user_name") or ""

        stats["总事件数"] += 1
        stats["级别分布"][severity] += 1

        cats, slow_ms = classify(message)
        for c in cats:
            stats["分类计数"][c] += 1

        # 错误聚类（message 模板）
        if severity in ("FATAL", "ERROR", "PANIC"):
            tmpl = re.sub(r"\s+", " ", message)[:160]
            tmpl = re.sub(r"'[^']*'", "'***'", tmpl)
            stats["错误Top"][tmpl] += 1
            if t is not None:
                stats["时间线"].append((t, severity, "|".join(cats) or "错误", mask_literal(message)))

        # 慢查询
        if slow_ms is not None:
            key = mask_literal(query) if query else mask_literal(message)
            agg = stats["慢查询聚合"][key]
            agg["count"] += 1
            agg["max_ms"] = max(agg["max_ms"], slow_ms)
            agg["total_ms"] += slow_ms

        # 认证失败
        if "password authentication failed" in message:
            stats["认证失败"][f'user={user or "?"}'] += 1

        # 崩溃/死锁/临时文件/归档 计数
        if "database system was interrupted" in message or "automatic recovery in progress" in message:
            stats["死亡/崩溃次数"] += 1
        if "deadlock detected" in message:
            stats["死锁次数"] += 1
        if re.search(r"temporary file:", message):
            stats["临时文件次数"] += 1
        if "archive command failed" in message:
            stats["归档失败次数"] += 1

        # 时间线补充：所有 FATAL/ERROR/PANIC 之外的关键 LOG（崩溃、断连）
        if severity not in ("FATAL", "ERROR", "PANIC") and t is not None:
            if RULE_CRASH.search(message) or "unexpected EOF" in message or RULE_CONFIG.search(message) \
               or RULE_KB_AUDIT.search(message) or RULE_CHECKPOINT.search(message) or RULE_AUTOVACUUM.search(message):
                stats["时间线"].append((t, severity, "|".join(cats) or "LOG", mask_literal(message)))

    # 慢查询 Top（按 max_ms 降序）
    stats["慢查询Top"] = sorted(stats["慢查询聚合"].items(), key=lambda kv: -kv[1]["max_ms"])[:10]
    return stats


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def render_text(stats, files):
    out = []
    out.append(f"===== KingbaseES csvlog 解析结果 =====")
    out.append(f"输入文件 ({len(files)}): {', '.join(str(p) for p in files)}")
    out.append(f"总事件数: {stats['总事件数']}")
    out.append(f"级别分布: {dict(stats['级别分布'])}")
    out.append(f"崩溃/自动恢复次数: {stats['死亡/崩溃次数']}  死锁: {stats['死锁次数']}  "
               f"临时文件: {stats['临时文件次数']}  归档失败: {stats['归档失败次数']}")

    out.append(f"\n[分类计数]")
    for k, v in stats["分类计数"].most_common():
        out.append(f"  {k}: {v}")

    out.append(f"\n[认证失败]")
    for k, v in stats["认证失败"].most_common():
        out.append(f"  {k}: {v}")

    out.append(f"\n[错误/致命 Top]")
    for k, v in stats["错误Top"].most_common(15):
        out.append(f"  {v:>3}  {k}")

    out.append(f"\n[慢查询 Top 10（按最大耗时）]")
    if not stats["慢查询Top"]:
        out.append("  （无慢查询记录；确认 log_min_duration_statement 已开启且非 -1）")
    for key, agg in stats["慢查询Top"]:
        out.append(f"  max={agg['max_ms']:>10.1f}ms avg={agg['total_ms']/agg['count']:>8.1f}ms "
                   f"count={agg['count']:>4}  {key}")

    out.append(f"\n[时间线（关键事件）]")
    if not stats["时间线"]:
        out.append("  （无关键事件）")
    for t, sev, cat, msg in sorted(stats["时间线"]):
        out.append(f"  {t.isoformat(' ', 'seconds')} [{sev}] ({cat}) {msg}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="KingbaseES csvlog 解析器（只读，标准库）")
    ap.add_argument("input", nargs="+", help="csvlog 文件或目录（支持 .csv / .csv.gz，目录递归扫描）")
    ap.add_argument("--since",
                    help="起始时间，如 '2026-08-09 09:00:00'（naive 时间，与日志 log_time 同基准，"
                         "金仓日志通常为 UTC，按 log_timezone 解释）")
    ap.add_argument("--until", help="结束时间")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    def parse_bound(s):
        if not s:
            return None
        v = str(s).strip()
        v = TZ_NAME_RE.sub("", v)
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            sys.stderr.write(f"无法解析时间: {s}\n")
            sys.exit(2)

    since, until = parse_bound(args.since), parse_bound(args.until)

    files = []
    for p in args.input:
        pp = Path(p)
        if pp.is_dir():
            files.extend(sorted(pp.glob("kingbase-*.csv*")))
        elif pp.is_file():
            files.append(pp)
        else:
            sys.stderr.write(f"路径不存在: {p}\n")
    if not files:
        sys.stderr.write("未找到 csvlog 文件（目录下应有 kingbase-*.csv 或 *.csv.gz）\n")
        sys.exit(1)

    rows = (r for f in files for r in iter_csv_rows(f))
    stats = aggregate(rows, since, until)

    if args.json:
        print(json.dumps({
            "files": [str(p) for p in files],
            "total_events": stats["总事件数"],
            "severity_dist": dict(stats["级别分布"]),
            "crash_count": stats["死亡/崩溃次数"],
            "deadlock_count": stats["死锁次数"],
            "tempfile_count": stats["临时文件次数"],
            "archive_fail_count": stats["归档失败次数"],
            "category_counts": dict(stats["分类计数"]),
            "auth_failures": dict(stats["认证失败"]),
            "error_top": [{"msg": k, "count": v} for k, v in stats["错误Top"].most_common(15)],
            "slow_query_top": [
                {"max_ms": a["max_ms"], "avg_ms": round(a["total_ms"] / a["count"], 1),
                 "count": a["count"], "query": k}
                for k, a in stats["慢查询Top"]
            ],
            "timeline": [
                {"time": t.isoformat(" ", "seconds"), "severity": sev, "category": cat, "msg": m}
                for t, sev, cat, m in sorted(stats["时间线"])
            ],
        }, ensure_ascii=False, indent=2))
    else:
        print(render_text(stats, files))


if __name__ == "__main__":
    main()
