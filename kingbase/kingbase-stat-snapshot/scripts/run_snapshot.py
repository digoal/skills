#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
kingbase-stat-snapshot / scripts / run_snapshot.py
============================================================
用途：
  1) 初始化基础设施（首次运行自动建表，重复运行安全幂等）
  2) 执行一次完整快照采集（实例级 + 遍历所有非模板库的库级视图）
  3) 输出采集报告（快照ID/时间/各视图行数/失败项/耗时）

兼容两种连接方式：
  - psycopg2 / psycopg (Python SDK)
  - psql 子进程（shell command）

连接信息优先级：
  1. 命令行参数（--host/--port/--user/--password/--dbname）
  2. 环境变量 PGHOST PGPORT PGUSER PGPASSWORD PGDBNAME
  3. 默认值 PGHOST=127.0.0.1 PGPORT=5432 PGDBNAME=kingbase PGUSER=kingbase PGPASSWORD=123456

用法：
  python run_snapshot.py init                                   # 仅初始化
  python run_snapshot.py collect                                # 初始化(若需要)+采集一次
  python run_snapshot.py --host <h> --port <p> --user <u> --password <pw> --dbname <db> collect
============================================================
"""

import argparse
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

# ----------------------- 默认参数 -----------------------
DEFAULTS = {
    "host": "127.0.0.1",
    "port": 5432,
    "user": "kingbase",
    "password": "123456",
    "dbname": "kingbase",
}

# ----------------------- 连接探测 -----------------------
def resolve_conn(args):
    """按 1.命令行 → 2.环境变量 → 3.默认值 顺序解析连接参数"""
    return {
        "host":     args.host     or os.environ.get("PGHOST")     or DEFAULTS["host"],
        "port":     args.port     or os.environ.get("PGPORT")     or DEFAULTS["port"],
        "user":     args.user     or os.environ.get("PGUSER")     or DEFAULTS["user"],
        "password": args.password or os.environ.get("PGPASSWORD") or DEFAULTS["password"],
        "dbname":   args.dbname   or os.environ.get("PGDBNAME")   or DEFAULTS["dbname"],
    }


def try_import_psycopg():
    """尝试导入 psycopg（v3）或 psycopg2，返回 (module, version_tag)"""
    try:
        import psycopg
        return psycopg, "v3"
    except ImportError:
        pass
    try:
        import psycopg2
        return psycopg2, "v2"
    except ImportError:
        return None, None


# ----------------------- 执行入口 -----------------------
def main():
    parser = argparse.ArgumentParser(description="kingbase-stat-snapshot 采集脚本")
    parser.add_argument("mode", nargs="?", default="collect", choices=["init", "collect"],
                        help="init=仅初始化, collect=初始化+采集一次")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--user")
    parser.add_argument("--password")
    parser.add_argument("--dbname")
    parser.add_argument("--no-init", action="store_true", help="跳过初始化（仅采集）")
    args = parser.parse_args()

    conn = resolve_conn(args)
    ref_dir = (Path(__file__).resolve().parent.parent / "references").resolve()
    print(f"== 连接目标: {conn['user']}@{conn['host']}:{conn['port']}/{conn['dbname']} ==")
    print(f"== references 目录: {ref_dir} ==")

    psycopg_mod, pgver = try_import_psycopg()
    if psycopg_mod is not None:
        print(f"== 使用 psycopg{pgver} (Python SDK) 连接 ==")
        runner = PsqlRunnerPsycopg(psycopg_mod, pgver, conn)
    else:
        print("== 未找到 psycopg/psycopg2，回退到 psql 子进程方式 ==")
        runner = PsqlRunnerShell(conn)

    failed_items = []
    start_ts = time.time()

    print("== Step 0: 连接探测与版本识别 ==")
    try:
        version_num = runner.scalar("SELECT current_setting('server_version_num')")
        print(f"server_version_num = {version_num}")
    except Exception as e:
        print(f"❌ 无法连接实例：{e}")
        sys.exit(1)

    # 检查 sys_stat_statements 扩展
    has_sss = runner.scalar("SELECT count(*) FROM pg_extension WHERE extname='sys_stat_statements'")
    if has_sss == 0:
        print("⚠️ sys_stat_statements 扩展未安装，请以有权限账号执行：")
        print("   CREATE EXTENSION IF NOT EXISTS sys_stat_statements;")
        print("   （需已在 shared_preload_libraries 中配置 sys_stat_statements 并重启实例，否则本命令仍会失败）")
        failed_items.append("sys_stat_statements: 扩展未安装")

    print("== Step 1: 初始化基础设施（幂等） ==")
    if not args.no_init:
        # 控制库统一使用指定 dbname（如 kingbase）
        try:
            runner.execute_script(ref_dir / "ddl_core.sql")
        except Exception as e:
            print(f"❌ 核心基础设施初始化失败：{e}")
            failed_items.append("ddl_core.sql: 初始化失败，见上方错误")

        try:
            runner.execute_script(ref_dir / "ddl_optional.sql")
        except Exception as e:
            print(f"⚠️ 可选视图初始化失败（可能实例版本不支持，属正常现象）：{e}")
            failed_items.append("ddl_optional.sql: 部分可选视图初始化失败（可能实例版本不支持，属正常现象）")

        # 遍历所有非模板数据库，初始化库级历史表
        db_list = runner.column("SELECT datname FROM pg_database WHERE datistemplate = false")
        for db in db_list:
            try:
                runner.execute_script(ref_dir / "ddl_perdb.sql", target_db=db)
            except Exception as e:
                print(f"❌ 数据库 {db} 的库级基础设施初始化失败：{e}")
                failed_items.append(f"{db}: 库级 DDL 初始化失败")

    if args.mode == "init":
        print("== 初始化完成 ==")
        print_failed(failed_items)
        return

    print("== Step 2: 执行一次快照采集 ==")

    # --- 实例级采集：sys_stat_statements + pg_stat_activity，同一事务 ---
    instance_sql = r"""
BEGIN;
INSERT INTO stat_snapshot.snapshots (snapshot_level, source_reset_time, comment)
VALUES ('instance',
        (SELECT sys_stat_statements_get_reset_time()),
        'run_snapshot.py 自动采集')
RETURNING snapshot_id
\gset

INSERT INTO stat_snapshot.stat_statements_history
SELECT :snapshot_id, now(), s.* FROM public.sys_stat_statements s;

INSERT INTO stat_snapshot.stat_activity_history
SELECT :snapshot_id, now(), a.* FROM pg_stat_activity a
WHERE a.state IS DISTINCT FROM 'idle'
   OR (SELECT count(*) FROM pg_stat_activity) <= 100;
COMMIT;

SELECT :snapshot_id AS snapshot_id;
"""
    try:
        snap_id = runner.execute_and_return_id(instance_sql)
        ss_rows = runner.scalar(
            f"SELECT count(*) FROM stat_snapshot.stat_statements_history WHERE snapshot_id={snap_id}")
        sa_rows = runner.scalar(
            f"SELECT count(*) FROM stat_snapshot.stat_activity_history WHERE snapshot_id={snap_id}")
        print(f"✅ 实例级快照 ID={snap_id}: sys_stat_statements {ss_rows} 行, pg_stat_activity {sa_rows} 行")
    except Exception as e:
        print(f"❌ 实例级采集失败：{e}")
        failed_items.append("实例级采集: 事务已回滚")

    # --- 库级采集：遍历每个非模板库 ---
    db_list = runner.column("SELECT datname FROM pg_database WHERE datistemplate = false")
    for db in db_list:
        db_sql = rf"""
BEGIN;
INSERT INTO stat_snapshot.snapshots (snapshot_level, database_name, source_reset_time)
VALUES ('database', current_database(),
        (SELECT stats_reset FROM pg_stat_database WHERE datname = current_database()))
RETURNING snapshot_id
\gset

INSERT INTO stat_snapshot.stat_user_tables_history SELECT :snapshot_id, now(), t.* FROM pg_stat_user_tables t;
INSERT INTO stat_snapshot.stat_user_indexes_history SELECT :snapshot_id, now(), i.* FROM pg_stat_user_indexes i;
INSERT INTO stat_snapshot.statio_user_tables_history SELECT :snapshot_id, now(), t.* FROM pg_statio_user_tables t;
INSERT INTO stat_snapshot.statio_user_indexes_history SELECT :snapshot_id, now(), i.* FROM pg_statio_user_indexes i;
COMMIT;
"""
        try:
            db_snap_id = runner.execute_and_return_id(db_sql, target_db=db)
            t_rows = runner.scalar(
                f"SELECT count(*) FROM stat_snapshot.stat_user_tables_history WHERE snapshot_id={db_snap_id}",
                target_db=db)
            i_rows = runner.scalar(
                f"SELECT count(*) FROM stat_snapshot.stat_user_indexes_history WHERE snapshot_id={db_snap_id}",
                target_db=db)
            print(f"✅ 库 {db} 快照 ID={db_snap_id}: pg_stat_user_tables {t_rows} 行, pg_stat_user_indexes {i_rows} 行")
        except Exception as e:
            print(f"❌ 数据库 {db} 采集失败：{e}")
            failed_items.append(f"{db}: 库级采集失败，事务已回滚")

    end_ts = time.time()
    print(f"== 采集完成，总耗时 {int(end_ts - start_ts)} 秒 ==")
    print_failed(failed_items)


def print_failed(items):
    if items:
        print("失败项:")
        for it in items:
            print(f"  - {it}")
    else:
        print("失败项: 无")


# ============================================================
# 抽象接口：两种实现
# ============================================================
class BaseRunner:
    def __init__(self, conn):
        self.conn = conn

    def scalar(self, sql, target_db=None):
        raise NotImplementedError

    def column(self, sql, target_db=None):
        raise NotImplementedError

    def execute_script(self, path, target_db=None):
        raise NotImplementedError

    def execute_and_return_id(self, sql, target_db=None):
        raise NotImplementedError


# ------------------------------------------------------------
# 实现 1: psycopg (Python SDK)
# ------------------------------------------------------------
class PsqlRunnerPsycopg(BaseRunner):
    def __init__(self, mod, version, conn):
        super().__init__(conn)
        self.mod = mod
        self.version = version
        self.conn_params = conn

    def _connect(self, target_db=None):
        kwargs = dict(self.conn_params)
        if target_db:
            kwargs["dbname"] = target_db
        if self.version == "v3":
            kwargs.pop("password", None)
            kwargs["password"] = kwargs.pop("password")
            return self.mod.connect(**kwargs, autocommit=False)
        else:
            # psycopg2 需要密码参数 + dbname
            return self.mod.connect(**kwargs)

    @contextmanager
    def _cursor(self, target_db=None):
        conn = self._connect(target_db)
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def scalar(self, sql, target_db=None):
        with self._cursor(target_db) as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return row[0] if row else None

    def column(self, sql, target_db=None):
        with self._cursor(target_db) as cur:
            cur.execute(sql)
            return [r[0] for r in cur.fetchall()]

    def execute_script(self, path, target_db=None):
        with open(path, "r", encoding="utf-8") as f:
            sql_text = f.read()
        with self._cursor(target_db) as cur:
            cur.execute(sql_text)

    def execute_and_return_id(self, sql, target_db=None):
        # 实例级 / 库级采集 SQL 包含 RETURNING snapshot_id \\gset 等 psql 元命令，
        # psycopg2 不支持多语句 execute，且无法处理 \\gset 元命令。处理策略：
        #   1) 用正则解析 SQL 拆为 4 部分：
        #      a) BEGIN;  (跳过，由 Python 连接事务接管)
        #      b) INSERT INTO snapshots ... RETURNING snapshot_id;  (提取出实际 snapshot_id)
        #      c) 中间的所有 INSERT INTO *_history SELECT :snapshot_id, ...;  (替换为真实 ID)
        #      d) COMMIT; (跳过)
        #   2) 用单一 cursor 串行执行 (b) 和 (c)，由外层 _cursor() 上下文负责 commit
        import re
        with self._cursor(target_db) as cur:
            # 去掉 psql 元命令
            sql_clean = sql
            sql_clean = re.sub(r"\\gset", "", sql_clean, flags=re.IGNORECASE)
            # 关键：给 RETURNING snapshot_id [AS snapshot_id] 末尾补 ;
            # （\\gset 在原 SQL 中会吞掉末尾的 ;，因此拆 ; 前必须补回）
            sql_clean = re.sub(
                r"(RETURNING\s+snapshot_id(\s+AS\s+snapshot_id)?)",
                r"\1;",
                sql_clean,
                flags=re.IGNORECASE,
            )

            # 拆分 BEGIN; ... ; COMMIT; 块（粗略：以 BEGIN 开始，到 COMMIT; 结束）
            m_begin = re.search(r"\bBEGIN\s*;", sql_clean, flags=re.IGNORECASE)
            m_commit = re.search(r"\bCOMMIT\s*;", sql_clean, flags=re.IGNORECASE)
            if not (m_begin and m_commit):
                raise RuntimeError("采集 SQL 未找到 BEGIN/COMMIT 事务边界")
            body = sql_clean[m_begin.end():m_commit.start()]

            # 按 ; 切分得到多条 SQL
            statements = [s.strip() for s in body.split(";") if s.strip()]

            snapshot_id = None
            for stmt in statements:
                # 如果是 INSERT INTO snapshots（含 RETURNING snapshot_id）
                if re.search(r"INSERT\s+INTO\s+stat_snapshot\.snapshots", stmt, flags=re.IGNORECASE):
                    # 把 RETURNING snapshot_id [AS snapshot_id] 保留，让 cursor.fetchone() 拿 ID
                    cur.execute(stmt)
                    row = cur.fetchone()
                    if row is None:
                        raise RuntimeError("INSERT INTO snapshots 未返回 snapshot_id")
                    snapshot_id = row[0]
                else:
                    # 其它 INSERT：把 :snapshot_id 替换为实际 ID
                    if snapshot_id is None:
                        raise RuntimeError("采集 SQL 中 :snapshot_id 出现在快照元数据行之前")
                    stmt_real = re.sub(r":snapshot_id", str(snapshot_id), stmt)
                    cur.execute(stmt_real)
            return snapshot_id


# ------------------------------------------------------------
# 实现 2: psql shell command
# ------------------------------------------------------------
class PsqlRunnerShell(BaseRunner):
    def __init__(self, conn):
        super().__init__(conn)

    def _cmd(self, sql, target_db=None, file=None):
        db = target_db or self.conn["dbname"]
        env = os.environ.copy()
        env["PGPASSWORD"] = str(self.conn["password"])
        cmd = [
            "psql",
            f"host={self.conn['host']}",
            f"port={self.conn['port']}",
            f"user={self.conn['user']}",
            f"dbname={db}",
            "-At",
            "-v", "ON_ERROR_STOP=1",
        ]
        if file:
            cmd.extend(["-f", str(file)])
        else:
            cmd.extend(["-c", sql])
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"psql 执行失败：{r.stderr.strip()}")
        return r.stdout.strip()

    def scalar(self, sql, target_db=None):
        out = self._cmd(sql, target_db=target_db)
        if not out:
            return None
        try:
            return int(out.splitlines()[0])
        except ValueError:
            try:
                return float(out.splitlines()[0])
            except ValueError:
                return out.splitlines()[0]

    def column(self, sql, target_db=None):
        out = self._cmd(sql, target_db=target_db)
        return [line for line in out.splitlines() if line]

    def execute_script(self, path, target_db=None):
        self._cmd("", target_db=target_db, file=path)

    def execute_and_return_id(self, sql, target_db=None):
        out = self._cmd(sql, target_db=target_db)
        # 最后一行通常是 SELECT :snapshot_id AS snapshot_id 的输出
        lines = [l for l in out.splitlines() if l.strip()]
        if not lines:
            raise RuntimeError("采集脚本未返回 snapshot_id")
        try:
            return int(lines[-1])
        except ValueError:
            raise RuntimeError(f"无法解析 snapshot_id: {lines[-1]!r}")


if __name__ == "__main__":
    main()