#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLup PG streaming-replication cluster creation tool (Claude Code skill).
Stdlib + pycryptodome. See ~/.claude/skills/pg-create-cluster/SKILL.md."""
import argparse
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# ---------------- constants ----------------
DEFAULT_URL = "http://127.0.0.1:8090"
CONF_PATH = "/home/clup/clup-all/clup-server/conf/clup.conf"

# ToDbText — mirrors clup-ui/src/common/util.js
AES_KEY = b"3743535544415441"
S1 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
S2 = "5k12IuKPrThB3t9LoYU8g*nW4pJGvi7eSs-yQNcaEHA6fDVjRdMlqzwbm+F0xCZXO"
D1 = {S1[i]: S2[i] for i in range(len(S1))}
D2 = {S2[i]: S1[i] for i in range(len(S2))}

# probe defaults — mirrors CreateStreamReplicationCluster.vue createSrClusterProbeForm
PROBE_DEFAULTS = {
    "auto_failback": False,
    "probe_db_name": "cs_sys_ha",
    "probe_interval": "10",
    "probe_timeout": "10",
    "probe_retry_cnt": "2",
    "probe_retry_interval": "5",
    "probe_pri_sql": "UPDATE cs_sys_heartbeat SET hb_time = now()",
    "probe_stb_sql": "SELECT 1",
    "trigger_db_name": "",
    "trigger_db_func": "",
    "remark": "",
}
WAL_SEGSIZE_MB_DEFAULT = 16
ROOM_NAME_DEFAULT = "Default Data Center"
CLUSTER_TYPE_PG_SR = 1
TEMPLATE_TYPE_PG = 1

EP_GET_SESSION = "/api/v1/get_session"
EP_LOGIN = "/api/v1/login"
EP_GET_CREATE_DB_HOST_LIST = "/api/v1/db/get_create_db_host_list"
EP_GET_VIP_POOL = "/api/v1/network/vip/get_vip_pool"
EP_GET_PG_BIN_PATH_LIST = "/api/v1/db/pg/get_pg_bin_path_list"
EP_GET_PG_BIN_VERSION = "/api/v1/db/pg/get_pg_bin_version"
EP_GET_INIT_DB_CONF = "/api/v1/db/pg/get_init_db_conf"
EP_GET_CREATE_DB_TEMPLATE = "/api/v1/db/get_create_db_template"
EP_CHECK_THE_DIR_IS_EMPTY = "/api/v1/db/check_the_dir_is_empty"
EP_CHECK_PORT_IS_USED = "/api/v1/host/check_port_is_used"
EP_CHECK_VIP_IN_POOL = "/api/v1/network/vip/check_vip_in_pool"
EP_GET_FREE_VIP_LIST = "/api/v1/network/vip/get_free_vip_list"
EP_CREATE_SR_CLUSTER = "/api/v1/db/cluster/pg/create_sr_cluster"
EP_GET_GENERAL_TASK_STATE = "/api/v1/task/get_general_task_state"
EP_GET_CLUSTER_DB_LIST = "/api/v1/db/cluster/get_cluster_db_list"
EP_STOP_DB = "/api/v1/db/pg/stop_db"
EP_DELETE_DB = "/api/v1/db/delete_db"
EP_DELETE_CLUSTER = "/api/v1/db/cluster/delete_cluster"


# ---------------- pure functions ----------------
def compute_hash_value(user, password, sid):
    return hashlib.sha256((user + password + sid).encode("utf-8")).hexdigest()


def to_db_text(s):
    """Mirror clup-ui DataProcessing.ToDbText: AES-ECB(PKCS7) -> base64 -> D1 per-char -> append 'A'."""
    if s is None:
        s = ""
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    ct = cipher.encrypt(pad(s.encode("utf-8"), AES.block_size))
    es = base64.b64encode(ct).decode("ascii")
    return "".join(D1[c] for c in es) + "A"


def from_db_text(t):
    if t is None:
        return ""
    body = t[:-1] if t.endswith("A") else t
    es = "".join(D2[c] for c in body)
    ct = base64.b64decode(es)
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    return unpad(cipher.decrypt(ct), AES.block_size).decode("utf-8")


def parse_response(text):
    """Normalize a CLup HTTP-200 body -> (ok, data, err_msg).
    _post already raises on non-200, so any body here is from a 200 response.
    JSON with err_code: check it. JSON without err_code / arrays: success with data.
    Non-JSON: a plain-text success message (e.g. check_vip_in_pool) -> success, raw text."""
    try:
        j = json.loads(text)
    except ValueError:
        return True, text, ""
    if isinstance(j, dict) and "err_code" in j:
        if j.get("err_code") == 0:
            return True, j, ""
        return False, j, j.get("err_msg") or ("err_code=%s" % j.get("err_code"))
    return True, j, ""


def pick_bin_path_for_version(path_versions, target_version):
    for pv in path_versions:
        if pv.get("version") == target_version:
            return pv["pg_bin_path"]
    avail = ", ".join(pv.get("version", "?") for pv in path_versions)
    raise ValueError("no pg_bin_path with version %s; available: %s" % (target_version, avail))


def build_db_list(primary, standbys, pgdata, bin_path_map, os_user, os_uid, version,
                  db_user, db_pass, repl_user, repl_pass):
    """Per-node db_list entries mirroring the frontend ClusterDbRows shape.
    version/major_version are required by the backend task
    (long_term_task_pg.create_sr_cluster); resource defaults mirror createSrClusterDbForm.
    Per-node db_user/db_pass/repl_user/repl_pass are PLAINTEXT — the frontend only ToDbText's
    the top-level fields; the backend reads per-node creds to connect when creating the
    replication user, so without these it fails with 'database not connected!'."""
    db_list = []
    major = version.split(".")[0]
    for idx, ip in enumerate([primary] + list(standbys)):
        if ip not in bin_path_map:
            raise ValueError("no pg_bin_path resolved for host %s" % ip)
        db_list.append({
            "host": ip,
            "repl_ip": ip,
            "pgdata": pgdata,
            "pg_bin_path": bin_path_map[ip],
            "version": version,
            "major_version": major,
            "os_user": os_user,
            "os_uid": os_uid,
            "db_user": db_user,
            "db_pass": db_pass,
            "repl_user": repl_user,
            "repl_pass": repl_pass,
            "scores": idx,
            "create_os_user": True,
            "max_connections": 200,
            "memory_size": "512MB",
            "storage_size": "10GB",
            "wal_segsize": "16MB",
            "storage_medium": "固态硬盘",
        })
    return db_list


def init_conf_to_setting_list(conf_items):
    """Convert get_init_db_conf()['setting_list'] items to the create_sr_cluster
    setting_list format: [{setting_name, val[, unit]}]. This is the version-specific
    PG config template straight from clup_init_db_conf — it includes listen_addresses='*',
    shared_preload_libraries, max_connections, etc. Using it is REQUIRED: without
    listen_addresses the new PG listens on localhost only, so the CLup server's TCP
    connection at create_replication_user is refused ('database not connected!')."""
    out = []
    for it in conf_items or []:
        item = {"setting_name": it.get("setting_name"), "val": it.get("val")}
        if it.get("unit"):
            item["unit"] = it.get("unit")
        out.append(item)
    return out


def build_create_body(cluster_name, vip, pool_id, port, pgdata, db_user, db_pass,
                      repl_user, repl_pass, db_list, setting_list, wal_segsize_mb,
                      cluster_type=CLUSTER_TYPE_PG_SR, is_check_plugs=1,
                      read_vip="", cstlb_list="", room_name=ROOM_NAME_DEFAULT):
    body = {
        "cluster_name": cluster_name,
        "vip": vip,
        "pool_id": int(pool_id),
        "port": int(port),
        "pgdata": pgdata,
        "db_user": db_user,
        "db_pass": to_db_text(db_pass),
        "repl_user": repl_user,
        "repl_pass": to_db_text(repl_pass),
        "cstlb_list": cstlb_list,
        "read_vip": read_vip,
        "room_name": room_name,
        "db_list": db_list,
        "setting_list": setting_list,
        "wal_segsize": wal_segsize_mb,
        "cluster_type": cluster_type,
        "is_check_plugs": is_check_plugs,
    }
    body.update(PROBE_DEFAULTS)
    return body


# ---------------- HTTP client ----------------
def resolve_url(cli_url=None):
    if cli_url:
        return cli_url.rstrip("/")
    env = os.environ.get("CLUP_URL")
    if env:
        return env.rstrip("/")
    port = None
    try:
        with open(CONF_PATH) as f:
            for line in f:
                line = line.strip()
                if line.startswith("http_port") and "=" in line:
                    port = line.split("=", 1)[1].strip()
                    break
    except OSError:
        pass
    if port:
        return "http://127.0.0.1:%s" % port
    return DEFAULT_URL


class ClupError(RuntimeError):
    pass


class ClupClient:
    def __init__(self, url, user=None, password=None):
        self.url = url.rstrip("/")
        self.user = user
        self.password = password
        self.sid = None

    def _post(self, path, payload=None):
        body = json.dumps(payload or {}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.sid:
            headers["Cookie"] = "session_id=%s" % self.sid
        req = urllib.request.Request(self.url + path, data=body, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise ClupError("HTTP %s on %s: %s" % (e.code, path, e.read()[:200]))
        except urllib.error.URLError as e:
            raise ClupError("connect %s failed: %s" % (self.url, e))

    def call(self, path, payload=None):
        ok, data, err = parse_response(self._post(path, payload))
        if not ok:
            raise ClupError("%s: %s" % (path, err))
        return data

    def login(self):
        sid_text = self._post(EP_GET_SESSION, {"user_name": self.user})
        sid = sid_text.strip().strip('"')
        if not sid or sid[0] in "{[":
            try:
                j = json.loads(sid_text)
                sid = (j.get("session_id") or j.get("sid") or "") if isinstance(j, dict) else ""
            except ValueError:
                sid = ""
        if not sid:
            raise ClupError("get_session returned no sid: %s" % sid_text[:200])
        self.sid = sid
        hv = compute_hash_value(self.user, self.password, sid)
        return self.call(EP_LOGIN, {"user_name": self.user, "hash_value": hv})

    # discovery
    def get_create_db_host_list(self):
        return self.call(EP_GET_CREATE_DB_HOST_LIST, {})

    def get_vip_pool(self):
        return self.call(EP_GET_VIP_POOL, {"page_num": 1, "page_size": 999})

    def get_pg_bin_path_list(self, host):
        return self.call(EP_GET_PG_BIN_PATH_LIST, {"host": host})

    def get_pg_bin_version(self, host, pg_bin_path):
        return self.call(EP_GET_PG_BIN_VERSION, {"host": host, "pg_bin_path": pg_bin_path})

    def get_create_db_template(self, template_type=TEMPLATE_TYPE_PG):
        return self.call(EP_GET_CREATE_DB_TEMPLATE, {"template_type": template_type})

    def get_init_db_conf(self, version):
        return self.call(EP_GET_INIT_DB_CONF, {"version": version})

    def list_path_versions(self, host):
        paths = self.get_pg_bin_path_list(host) or []
        out = []
        for p in paths:
            bp = p.get("pg_bin_path") or p.get("path") if isinstance(p, dict) else p
            ver = self.get_pg_bin_version(host, bp)
            out.append({"pg_bin_path": bp,
                        "version": ver.get("version") if isinstance(ver, dict) else ver,
                        "major_version": ver.get("major_version") if isinstance(ver, dict) else None})
        return out

    # checks
    def check_the_dir_is_empty(self, host, pgdata):
        return self.call(EP_CHECK_THE_DIR_IS_EMPTY, {"host": host, "pgdata": pgdata})

    def check_port_is_used(self, host, port):
        return self.call(EP_CHECK_PORT_IS_USED, {"host": host, "port": int(port)})

    def check_vip_in_pool(self, pool_id, vip):
        return self.call(EP_CHECK_VIP_IN_POOL, {"pool_id": int(pool_id), "vip": vip})

    def get_free_vip_list(self, pool_id):
        """Free VIPs of a pool as concrete IPs — CLup already excludes those occupied
        by any cluster (unlike get_vip_pool's pool-level `free` count, which is a number
        only and does not say WHICH IPs are free). Mirrors frontend getFreeVipList
        (AvaiableIP.vue): {pool_id, page_num, page_size} -> {rows: [<ip>, ...], total}."""
        data = self.call(EP_GET_FREE_VIP_LIST, {"pool_id": int(pool_id), "page_num": 1, "page_size": 999})
        rows = data.get("rows", data) if isinstance(data, dict) else data
        return rows or []

    # create + task
    def create_sr_cluster(self, body):
        return self.call(EP_CREATE_SR_CLUSTER, body)

    def get_general_task_state(self, task_id):
        return self.call(EP_GET_GENERAL_TASK_STATE, {"task_id": int(task_id)})

    # cluster lifecycle (teardown)
    def get_cluster_db_list(self, cluster_id):
        data = self.call(EP_GET_CLUSTER_DB_LIST, {"cluster_id": int(cluster_id), "page_num": 1, "page_size": 999})
        rows = data.get("rows", data) if isinstance(data, dict) else data
        return rows or []

    def stop_db(self, db_id):
        return self.call(EP_STOP_DB, {"db_id": int(db_id)})

    def delete_db(self, db_id, rm_pgdata=1):
        return self.call(EP_DELETE_DB, {"db_id": int(db_id), "rm_pgdata": rm_pgdata})

    def delete_cluster(self, cluster_id, vip_delete_flag=1):
        return self.call(EP_DELETE_CLUSTER, {"cluster_id": int(cluster_id), "vip_delete_flag": vip_delete_flag})


# ---------------- CLI ----------------
def make_client(args):
    url = resolve_url(getattr(args, "url", None))
    user = getattr(args, "user", None) or os.environ.get("CLUP_USER")
    password = getattr(args, "pass", None) or os.environ.get("CLUP_PASS")
    if not user or not password:
        raise ClupError("missing credentials: set --user/--pass or CLUP_USER/CLUP_PASS")
    return ClupClient(url, user, password)


def cmd_hosts(args):
    c = make_client(args); c.login()
    rows = c.get_create_db_host_list() or []
    print("hid\tip\tstate\tmem(MB)\thostname")
    for h in rows:
        print("%s\t%s\t%s\t%s\t%s" % (
            h.get("hid"), h.get("ip"), h.get("state"),
            (h.get("data") or {}).get("mem_size") or h.get("mem_size"),
            h.get("hostname")))


def cmd_vips(args):
    """List each pool's VIPs that are actually selectable = free (not used by any
    cluster, per CLup get_free_vip_list) AND not a host IP. The pool-level `free` from
    get_vip_pool is a count only and never says WHICH IPs are free, and a free IP that
    happens to equal a host IP is unusable (ARP conflict on failover) — so picking from
    the raw pool led to 'vip already used' / host-IP collisions. This resolves both and
    prints a ready-to-pick recommended list."""
    c = make_client(args); c.login()
    host_ips = set()
    for h in (c.get_create_db_host_list() or []):
        ip = h.get("ip")
        if ip:
            host_ips.add(ip)
    data = c.get_vip_pool()
    pools = data.get("rows", data) if isinstance(data, dict) else data
    only_pool = args.pool_id
    recommended = []
    print("VIP pools — selectable = free (unused) AND not a host IP")
    for p in (pools or []):
        pid = p.get("pool_id")
        if only_pool and pid != only_pool:
            continue
        name = p.get("pool_name")
        total = p.get("total") or 0
        free_ips = [str(x) for x in (c.get_free_vip_list(pid) or [])]
        selectable = [ip for ip in free_ips if ip not in host_ips]
        host_conflict = [ip for ip in free_ips if ip in host_ips]
        occupied = total - len(free_ips)
        print("pool %s (%s): total=%s free=%s selectable=%s occupied=%s"
              % (pid, name, total, len(free_ips), len(selectable), occupied))
        if selectable:
            print("  [selectable]   " + " ".join(selectable))
        if host_conflict:
            print("  [host-ip, N/A] " + " ".join(host_conflict))
        if not selectable:
            print("  (no selectable VIP)")
        for ip in selectable:
            recommended.append((ip, pid, name))
    print("=== recommended selectable VIPs (pick one) ===")
    if recommended:
        for ip, pid, name in recommended:
            print("%s\t(pool %s %s)" % (ip, pid, name))
    else:
        print("(none)")


def cmd_binpaths(args):
    c = make_client(args); c.login()
    for pv in c.list_path_versions(args.host):
        print("%s\t%s\t%s" % (pv["pg_bin_path"], pv["version"], pv["major_version"]))


def cmd_template(args):
    c = make_client(args); c.login()
    print(json.dumps(c.get_create_db_template(args.type), ensure_ascii=False, indent=2))


def cmd_check(args):
    c = make_client(args); c.login()
    fail = []
    r = c.check_the_dir_is_empty(args.host, args.pgdata)
    is_empty = r.get("is_empty") if isinstance(r, dict) else r
    print("dir_empty\t%s:%s\t-> %s" % (args.host, args.pgdata, is_empty))
    if not is_empty:
        fail.append("dir not empty on %s" % args.host)
    if args.port:
        r = c.check_port_is_used(args.host, args.port)
        used = r.get("is_used") if isinstance(r, dict) else r
        print("port_used\t%s:%s\t-> %s" % (args.host, args.port, used))
        if used:
            fail.append("port %s used on %s" % (args.port, args.host))
    if args.pool_id and args.vip:
        c.check_vip_in_pool(args.pool_id, args.vip)
        print("vip_in_pool\t%s in pool %s -> OK" % (args.vip, args.pool_id))
    if fail:
        print("CHECK FAILED:", "; ".join(fail), file=sys.stderr)
        sys.exit(1)
    print("CHECK OK")


def _confirm_create_task(c, task_id, timeout=1800, interval=5):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = c.get_general_task_state(task_id)
        last = r.get("state") if isinstance(r, dict) else r
        print("task %s state=%s" % (task_id, last))
        if last is not None and last != 0:   # 0=in-progress; 1=success, -1=failed
            return last
        time.sleep(interval)
    return last


def cmd_task(args):
    c = make_client(args); c.login()
    r = c.get_general_task_state(args.task_id)
    print("task %s state=%s" % (args.task_id, r.get("state") if isinstance(r, dict) else r))


def cmd_delete(args):
    """Full teardown for a clean redo: stop each DB, remove its data dir, delete the
    cluster and free the VIP. delete_cluster alone only drops CLup metadata (it leaves
    the PG processes running and the data dirs on disk), so to actually wipe a failed
    cluster you must stop+delete_db each node first."""
    c = make_client(args); c.login()
    cluster_id = args.cluster_id
    dbs = c.get_cluster_db_list(cluster_id)
    primary = [d for d in dbs if d.get("is_primary") == 1]
    standbys = [d for d in dbs if d.get("is_primary") != 1]
    print("cluster %s: %d primary, %d standby" % (cluster_id, len(primary), len(standbys)))
    for d in dbs:
        try:
            c.stop_db(d["db_id"]); print("  stopped db %s (%s)" % (d["db_id"], d.get("host")))
        except ClupError as e:
            print("  warn: stop db %s: %s" % (d["db_id"], e))
    for d in standbys + primary:
        try:
            c.delete_db(d["db_id"], rm_pgdata=1)
            print("  deleted db %s (%s, pgdata removed)" % (d["db_id"], d.get("host")))
        except ClupError as e:
            print("  warn: delete db %s: %s" % (d["db_id"], e))
    c.delete_cluster(cluster_id, vip_delete_flag=1)
    print("deleted cluster %s" % cluster_id)


def _major_version(full_version):
    return full_version.split(".")[0]


def cmd_create(args):
    c = make_client(args); c.login()
    standbys = [s.strip() for s in args.standby.split(",") if s.strip()]
    nodes = [args.primary] + standbys
    if len(nodes) < 2:
        raise ClupError("need at least 1 primary + 1 standby")

    tmpl = c.get_create_db_template(args.type)
    db_user = args.db_user or tmpl.get("db_user", "postgres")
    db_pass = args.db_pass or tmpl.get("db_pass", "postgres")
    os_user = args.os_user or tmpl.get("os_user", "postgres")
    os_uid = args.os_uid or tmpl.get("os_uid", 701)
    port = args.port or tmpl.get("port", 5432)
    # Frontend default: repl_user = db_user, repl_pass = db_pass (see CreateStreamReplicationCluster.vue).
    # Using a separate repl user makes the backend's create_replication_user create a new role and
    # test-connect as it, which fails with "database not connected!" in this CLup build — so default
    # to the superuser unless the user explicitly overrides.
    repl_user = args.repl_user or db_user
    repl_pass = args.repl_pass or db_pass
    pgdata = args.pgdata or ("/pgdata/%s/data" % _major_version(args.version))
    init_conf = c.get_init_db_conf(args.version)
    conf_items = init_conf.get("setting_list", init_conf) if isinstance(init_conf, dict) else init_conf
    setting_list = init_conf_to_setting_list(conf_items)

    bin_path_map = {}
    for ip in nodes:
        pvs = c.list_path_versions(ip)
        bin_path_map[ip] = pick_bin_path_for_version(pvs, args.version)
        print("matched %s -> %s" % (ip, bin_path_map[ip]))

    db_list = build_db_list(args.primary, standbys, pgdata, bin_path_map, os_user, os_uid, args.version,
                            db_user, db_pass, repl_user, repl_pass)

    for ip in nodes:
        r = c.check_the_dir_is_empty(ip, pgdata)
        if not (r.get("is_empty") if isinstance(r, dict) else r):
            raise ClupError("pgdata not empty on %s: %s" % (ip, pgdata))
        rp = c.check_port_is_used(ip, port)
        if (rp.get("is_used") if isinstance(rp, dict) else rp):
            raise ClupError("port %s used on %s" % (port, ip))
    c.check_vip_in_pool(args.pool_id, args.vip)

    body = build_create_body(
        cluster_name=args.cluster_name, vip=args.vip, pool_id=args.pool_id, port=port,
        pgdata=pgdata, db_user=db_user, db_pass=db_pass, repl_user=repl_user, repl_pass=repl_pass,
        db_list=db_list, setting_list=setting_list, wal_segsize_mb=args.wal_segsize,
        is_check_plugs=(0 if args.no_check_plugs else 1))

    print("CREATE BODY:\n" + json.dumps(body, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("DRY-RUN: preflight passed, not submitting.")
        return

    res = c.create_sr_cluster(body)
    task_id = res.get("task_id")
    print("created, task_id=%s" % task_id)
    if args.wait and task_id:
        state = _confirm_create_task(c, task_id)
        if state == 1:
            print("SUCCESS: cluster created (task %s)" % task_id)
        else:
            print("FAILED: task %s final state=%s (see CLup task log)" % (task_id, state))


def main(argv=None):
    parser = argparse.ArgumentParser(description="CLup PG streaming-replication cluster tool")
    parser.add_argument("--url", help="CLup base URL (default: $CLUP_URL or conf http_port)")
    parser.add_argument("--user", help="CLup user (default: $CLUP_USER)")
    parser.add_argument("--pass", dest="pass", help="CLup password (default: $CLUP_PASS)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="establish and verify session")
    sub.add_parser("hosts", help="list online agent hosts")
    p_vips = sub.add_parser("vips", help="list VIP pools with selectable (free, non-host-IP) VIPs")
    p_vips.add_argument("--pool-id", dest="pool_id", type=int)
    p_bp = sub.add_parser("binpaths", help="list PG bin paths + versions on a host")
    p_bp.add_argument("--host", required=True)
    p_tmpl = sub.add_parser("template", help="show create-db template defaults")
    p_tmpl.add_argument("--type", type=int, default=TEMPLATE_TYPE_PG)
    p_chk = sub.add_parser("check", help="preflight: dir empty / port / vip in pool")
    p_chk.add_argument("--host", required=True)
    p_chk.add_argument("--pgdata", required=True)
    p_chk.add_argument("--port", type=int)
    p_chk.add_argument("--pool-id", dest="pool_id", type=int)
    p_chk.add_argument("--vip")
    p_cr = sub.add_parser("create", help="create PG streaming-replication cluster (existing hosts)")
    p_cr.add_argument("--cluster-name", dest="cluster_name", required=True)
    p_cr.add_argument("--primary", required=True, help="primary host IP")
    p_cr.add_argument("--standby", required=True, help="comma-separated standby IPs")
    p_cr.add_argument("--version", required=True, help="full PG version, e.g. 16.10")
    p_cr.add_argument("--vip", required=True)
    p_cr.add_argument("--pool-id", dest="pool_id", type=int, required=True)
    p_cr.add_argument("--repl-user", dest="repl_user")
    p_cr.add_argument("--repl-pass", dest="repl_pass")
    p_cr.add_argument("--db-user", dest="db_user")
    p_cr.add_argument("--db-pass", dest="db_pass")
    p_cr.add_argument("--port", type=int)
    p_cr.add_argument("--pgdata")
    p_cr.add_argument("--os-user", dest="os_user")
    p_cr.add_argument("--os-uid", dest="os_uid", type=int)
    p_cr.add_argument("--wal-segsize", dest="wal_segsize", type=int, default=WAL_SEGSIZE_MB_DEFAULT)
    p_cr.add_argument("--type", type=int, default=TEMPLATE_TYPE_PG)
    p_cr.add_argument("--no-check-plugs", dest="no_check_plugs", action="store_true")
    p_cr.add_argument("--dry-run", dest="dry_run", action="store_true")
    p_cr.add_argument("--wait", action="store_true", help="poll task until terminal")
    p_tk = sub.add_parser("task", help="query a task's state")
    p_tk.add_argument("--task-id", dest="task_id", type=int, required=True)
    p_del = sub.add_parser("delete", help="full teardown: stop DBs, remove data dirs, delete cluster + free VIP")
    p_del.add_argument("--cluster-id", dest="cluster_id", type=int, required=True)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "login":
            c = make_client(args); c.login(); print("login OK:", c.user)
        elif args.cmd == "hosts":
            cmd_hosts(args)
        elif args.cmd == "vips":
            cmd_vips(args)
        elif args.cmd == "binpaths":
            cmd_binpaths(args)
        elif args.cmd == "template":
            cmd_template(args)
        elif args.cmd == "check":
            cmd_check(args)
        elif args.cmd == "create":
            cmd_create(args)
        elif args.cmd == "task":
            cmd_task(args)
        elif args.cmd == "delete":
            cmd_delete(args)
        else:
            parser.error("unknown command")
    except ClupError as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
