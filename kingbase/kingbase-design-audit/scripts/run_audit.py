#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_audit.py :: kingbase-design-audit 编排脚本 (Python 版)

用法:
    PGPASSWORD='xxx' python3 run_audit.py -h <host> -p <port> -U <user> [-d <db1,db2>] [-o <outdir>]
    # 或
    python3 run_audit.py --conn-str "host=127.0.0.1 port=5432 dbname=kingbase user=kingbase password=xxx"

说明:
    - 通过 psycopg2 / psycopg3 连接 KingbaseES（兼容 PG 协议），支持任一驱动。
    - 密码通过 PGPASSWORD 环境变量或 --password 参数传入，不在命令行回显。
    - 若不指定 -d/--databases，将自动发现实例内所有非模板数据库。
    - 每个数据库的每个检查项输出为独立文本文件，便于审阅。

依赖: psycopg2-binary 或 psycopg (psycopg3) 二选一
"""

from __future__ import annotations

import argparse
import contextlib
import os
import pathlib
import sys
import time
from typing import Iterator, List, Optional

QUERY_DIR = pathlib.Path(__file__).resolve().parent / "queries"
QUERY_NAMES = [
    "01_naming",
    "02_data_types",
    "03_comments",
    "04_large_tables_partition",
    "05_index_design",
    "06_constraints_defaults",
    "07_db_config",
]


class Driver:
    """psycopg2 / psycopg3 统一封装"""

    def __init__(self, lib: str):
        self.lib = lib
        if lib == "psycopg2":
            import psycopg2  # type: ignore
            # psycopg2.extras 是子模块, 需显式导入后才能作为属性访问
            import psycopg2.extras  # type: ignore  # noqa: F401

            self.psycopg2 = psycopg2
            self.extras = psycopg2.extras
            self.psycopg = None
        elif lib in ("psycopg3", "psycopg"):
            import psycopg  # type: ignore

            self.psycopg = psycopg
            self.psycopg2 = None
            self.extras = None
        else:
            raise RuntimeError(f"未知驱动: {lib}")

    def connect(self, **kwargs):
        if self.lib == "psycopg2":
            # psycopg2 用 password 字段名
            if "password" not in kwargs and "PGPASSWORD" in os.environ:
                kwargs["password"] = os.environ["PGPASSWORD"]
            return self.psycopg2.connect(**kwargs)
        else:
            # psycopg3 同名参数
            if "password" not in kwargs and "PGPASSWORD" in os.environ:
                kwargs["password"] = os.environ["PGPASSWORD"]
            return self.psycopg.connect(**kwargs, autocommit=True)

    @contextlib.contextmanager
    def cursor(self, conn):
        if self.lib == "psycopg2":
            cur = conn.cursor()
            try:
                yield cur
            finally:
                cur.close()
        else:
            with conn.cursor() as cur:
                yield cur


def select_driver(prefer: Optional[str] = None) -> Driver:
    """优先使用 psycopg2 (驱动存在), 否则回退 psycopg3"""
    if prefer in (None, "psycopg2"):
        try:
            import psycopg2  # type: ignore

            return Driver("psycopg2")
        except Exception:
            pass
    if prefer in (None, "psycopg", "psycopg3"):
        try:
            import psycopg  # type: ignore

            return Driver("psycopg3")
        except Exception:
            pass
    raise RuntimeError("未找到可用的 PG 驱动，请安装 psycopg2-binary 或 psycopg")


def detect_driver() -> Driver:
    return select_driver()


def list_databases(driver: Driver, host: str, port: int, user: str, dbname: str) -> List[str]:
    """通过 'postgres' 库执行 00_list_databases.sql, 拿到 db 列表"""
    sql = (QUERY_DIR / "00_list_databases.sql").read_text()
    dbs: List[str] = []
    with driver.connect(host=host, port=port, user=user, dbname=dbname) as conn:
        with driver.cursor(conn) as cur:
            cur.execute(sql)
            for (name,) in cur.fetchall():
                nm = (name or "").strip()
                if nm and nm not in ("template0", "template1", "template2"):
                    dbs.append(nm)
    return dbs


def run_query(driver: Driver, host: str, port: int, user: str, dbname: str, qfile: pathlib.Path) -> str:
    """执行单条查询, 返回 pipe-delimited 文本输出 (无 stderr)"""
    sql = qfile.read_text()
    # psql 客户端元命令 (\\pset / \\set / \\echo) 不能通过 libpq 发送,
    # Python 路径下需过滤掉这些行. SQL 主体不受影响.
    sql = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("\\")
    ).strip()
    if not sql:
        return ""
    out_lines: List[str] = []
    with driver.connect(host=host, port=port, user=user, dbname=dbname) as conn:
        with driver.cursor(conn) as cur:
            cur.execute(sql)
            try:
                while True:
                    rows = cur.fetchmany(500)
                    if not rows:
                        break
                    for row in rows:
                        out_lines.append("|".join("" if v is None else str(v) for v in row))
                    if len(rows) < 500:
                        break
            except Exception:
                # 部分查询 (如 SHOW) 不返回行集
                pass
    return "\n".join(out_lines) + ("\n" if out_lines else "")


def run_audit(
    host: str,
    port: int,
    user: str,
    databases: Optional[List[str]],
    outdir: pathlib.Path,
    driver: Driver,
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    if not databases:
        print("[info] 自动发现非模板数据库...", file=sys.stderr)
        # 先尝试 postgres (PG 习惯), 失败则用 kingbase 默认库
        boot_db = None
        for try_db in ("postgres", "kingbase"):
            try:
                with driver.connect(host=host, port=port, user=user, dbname=try_db) as conn:
                    with driver.cursor(conn) as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                boot_db = try_db
                break
            except Exception as e:
                print(f"[warn] 引导库 {try_db} 不可用: {e}", file=sys.stderr)
        if not boot_db:
            raise RuntimeError("无法连接引导库 postgres/kingbase 任何一个，请用 -d 指定数据库列表")
        databases = list_databases(driver, host, port, user, boot_db)
    print(f"[info] 待扫描数据库: {databases}", file=sys.stderr)

    for db in databases:
        db_outdir = outdir / db
        db_outdir.mkdir(parents=True, exist_ok=True)
        print(f"== 正在扫描数据库: {db} ==", file=sys.stderr)
        for qname in QUERY_NAMES:
            qfile = QUERY_DIR / f"{qname}.sql"
            outpath = db_outdir / f"{qname}.txt"
            errpath = db_outdir / f"{qname}.err"
            start = time.time()
            err = ""
            text = ""
            try:
                text = run_query(driver, host, port, user, db, qfile)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
            elapsed_ms = int((time.time() - start) * 1000)
            outpath.write_text(text)
            errpath.write_text(err)
            if err:
                print(f"  [{qname}] FAIL ({elapsed_ms}ms): {err}", file=sys.stderr)
            else:
                print(f"  [{qname}] OK ({elapsed_ms}ms, {len(text)} bytes)", file=sys.stderr)

    print(f"[info] 全部扫描完成，原始结果已保存至: {outdir}", file=sys.stderr)
    print("[info] 下一步：由 Agent 读取该目录下各文件，按 SKILL.md 中的规则生成 Markdown 报告。", file=sys.stderr)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="KingbaseES 设计审查 - Python 编排脚本")
    p.add_argument("-H", "--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    p.add_argument("-p", "--port", type=int, default=int(os.environ.get("PGPORT", "5432")))
    p.add_argument("-U", "--user", default=os.environ.get("PGUSER", "kingbase"))
    p.add_argument("-d", "--databases", default="", help="逗号分隔数据库列表，留空自动发现")
    p.add_argument("-o", "--outdir", default="./kb_audit_output")
    p.add_argument("--driver", choices=["psycopg2", "psycopg3"], default=None,
                   help="强制使用指定驱动 (默认自动检测)")
    p.add_argument("--password", default=None,
                   help="数据库密码 (推荐通过 PGPASSWORD 环境变量传入)")
    args = p.parse_args(argv)

    driver = select_driver(args.driver) if args.driver else detect_driver()
    print(f"[info] 已选用驱动: {driver.lib}", file=sys.stderr)

    if args.password:
        os.environ["PGPASSWORD"] = args.password

    if not os.environ.get("PGPASSWORD"):
        print("[warn] 未设置 PGPASSWORD / --password，将依赖 .pgpass 或交互输入",
              file=sys.stderr)

    dbs: Optional[List[str]] = None
    if args.databases.strip():
        dbs = [d.strip() for d in args.databases.split(",") if d.strip()]

    outdir = pathlib.Path(args.outdir)
    run_audit(
        host=args.host,
        port=args.port,
        user=args.user,
        databases=dbs,
        outdir=outdir,
        driver=driver,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
