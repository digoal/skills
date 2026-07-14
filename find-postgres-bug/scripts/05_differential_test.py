#!/usr/bin/env python3
"""
阶段5：差分测试
- 模式 A（--mode cross-version）：对比两个不同 PostgreSQL 实例（如 master vs REL_16_STABLE）
  对同一批 SQL 的执行结果/错误码。
- 模式 B（--mode planner-flags）：同一实例内，切换 enable_hashjoin/enable_indexscan 等参数，
  对同一条复杂查询做结果集哈希对比。

用法:
  python3 05_differential_test.py --mode cross-version \
      --dsn-a "host=localhost port=5501 dbname=fuzzdb user=postgres" \
      --dsn-b "host=localhost port=5502 dbname=fuzzdb user=postgres" \
      --sql-file queries.sql

  python3 05_differential_test.py --mode planner-flags \
      --dsn "host=localhost port=5501 dbname=fuzzdb user=postgres" \
      --sql-file queries.sql

依赖: pip install --break-system-packages psycopg2-binary
密码统一从环境变量 PGPASSWORD 读取，不接受命令行传参。
"""
import argparse
import hashlib
import itertools
import os
import sys

try:
    import psycopg2
except ImportError:
    print("需要 psycopg2: pip install --break-system-packages psycopg2-binary", file=sys.stderr)
    sys.exit(1)

PLANNER_FLAGS = [
    "enable_hashjoin", "enable_mergejoin", "enable_nestloop",
    "enable_indexscan", "enable_indexonlyscan", "enable_seqscan", "enable_bitmapscan",
]


def run_query(dsn, sql, flag_settings=None):
    conn = psycopg2.connect(dsn, password=os.environ.get("PGPASSWORD"))
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        if flag_settings:
            for k, v in flag_settings.items():
                cur.execute(f"SET {k} = {v}")
        cur.execute(sql)
        rows = cur.fetchall()
        return "OK", rows
    except Exception as e:
        return "ERROR", str(e)
    finally:
        conn.close()


def hash_rows(rows):
    h = hashlib.sha256()
    for row in sorted(rows, key=lambda r: str(r)):
        h.update(repr(row).encode())
    return h.hexdigest()


def cross_version(dsn_a, dsn_b, queries, out_path):
    diffs = []
    for i, sql in enumerate(queries):
        status_a, res_a = run_query(dsn_a, sql)
        status_b, res_b = run_query(dsn_b, sql)
        mismatch = False
        if status_a != status_b:
            mismatch = True
        elif status_a == "OK" and hash_rows(res_a) != hash_rows(res_b):
            mismatch = True
        if mismatch:
            diffs.append({
                "index": i, "sql": sql,
                "a": (status_a, res_a), "b": (status_b, res_b),
            })
    write_report(out_path, "跨版本差分测试", diffs)


def planner_flags(dsn, queries, out_path):
    diffs = []
    combos = list(itertools.product([True, False], repeat=min(3, len(PLANNER_FLAGS))))
    for i, sql in enumerate(queries):
        results = {}
        for combo in combos:
            settings = {PLANNER_FLAGS[j]: ("on" if combo[j] else "off") for j in range(len(combo))}
            status, res = run_query(dsn, sql, settings)
            key = tuple(sorted(settings.items()))
            results[key] = (status, hash_rows(res) if status == "OK" else res)
        distinct = set(v[1] for v in results.values())
        if len(distinct) > 1:
            diffs.append({"index": i, "sql": sql, "variants": results})
    write_report(out_path, "优化器参数组合差分测试", diffs)


def write_report(out_path, title, diffs):
    with open(out_path, "w") as f:
        f.write(f"# {title}\n\n")
        f.write(f"发现 {len(diffs)} 处不一致\n\n")
        f.write("> 注意：提交为 bug 前请先核实是否为已知的、文档化的行为差异（如未定义排序顺序）\n\n")
        for d in diffs:
            f.write(f"## 查询 #{d['index']}\n\n```sql\n{d['sql']}\n```\n\n")
            f.write(f"详情: {d}\n\n")
    print(f"差分测试完成，报告写入 {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["cross-version", "planner-flags"], required=True)
    ap.add_argument("--dsn-a")
    ap.add_argument("--dsn-b")
    ap.add_argument("--dsn")
    ap.add_argument("--sql-file", required=True)
    ap.add_argument("--out", default="find-bug-artifacts/diff_findings.md")
    args = ap.parse_args()

    with open(args.sql_file) as f:
        queries = [line.strip() for line in f if line.strip() and not line.strip().startswith("--")]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    if args.mode == "cross-version":
        if not (args.dsn_a and args.dsn_b):
            print("cross-version 模式需要 --dsn-a 和 --dsn-b", file=sys.stderr)
            sys.exit(1)
        cross_version(args.dsn_a, args.dsn_b, queries, args.out)
    else:
        if not args.dsn:
            print("planner-flags 模式需要 --dsn", file=sys.stderr)
            sys.exit(1)
        planner_flags(args.dsn, queries, args.out)


if __name__ == "__main__":
    main()
