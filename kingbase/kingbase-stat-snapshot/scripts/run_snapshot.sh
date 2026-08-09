#!/usr/bin/env bash
# ============================================================
# kingbase-stat-snapshot / scripts / run_snapshot.sh
#
# 用途：
#   1) 初始化基础设施（首次运行自动建表，重复运行安全幂等）
#   2) 执行一次完整快照采集（实例级 + 遍历所有非模板库的库级视图）
#   3) 输出采集报告（快照ID/时间/各视图行数/失败项/耗时）
#
# 连接信息通过环境变量传入，不在命令行明文拼接密码：
#   PGHOST PGPORT PGUSER PGPASSWORD PGDBNAME
# 未设置时使用默认值（127.0.0.1:5432/kingbase/kingbase/123456）。
#
# 用法：
#   ./run_snapshot.sh init      # 仅初始化
#   ./run_snapshot.sh collect   # 初始化(若需要)+采集一次
# ============================================================
set -uo pipefail

PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-kingbase}"
PGPASSWORD="${PGPASSWORD:-123456}"
PGDBNAME="${PGDBNAME:-kingbase}"

: "${PGHOST:?必须设置 PGHOST 或使用默认值}"
: "${PGUSER:?必须设置 PGUSER 或使用默认值}"
: "${PGPASSWORD:?必须设置 PGPASSWORD 或使用默认值}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REF_DIR="$(dirname "$SCRIPT_DIR")/references"
MODE="${1:-collect}"

CONN_MAIN="host=${PGHOST} port=${PGPORT} user=${PGUSER} dbname=${PGDBNAME}"
export PGPASSWORD

psql_main() { psql "$CONN_MAIN" -v ON_ERROR_STOP=1 "$@"; }

FAILED_ITEMS=()
START_TS=$(date +%s)

echo "== Step 0: 连接探测与版本识别 =="
VERSION_NUM=$(psql_main -Atc "SELECT current_setting('server_version_num');") || { echo "无法连接实例，请检查连接信息"; exit 1; }
echo "server_version_num = ${VERSION_NUM}"

HAS_SSS=$(psql_main -Atc "SELECT count(*) FROM pg_extension WHERE extname='sys_stat_statements';")
if [[ "$HAS_SSS" -eq 0 ]]; then
    echo "⚠️ sys_stat_statements 扩展未安装，请以有权限账号执行："
    echo "   CREATE EXTENSION IF NOT EXISTS sys_stat_statements;"
    echo "   （需已在 shared_preload_libraries 中配置 sys_stat_statements 并重启实例，否则本命令仍会失败）"
    FAILED_ITEMS+=("sys_stat_statements: 扩展未安装")
fi

echo "== Step 1: 初始化基础设施（幂等） =="
if ! psql_main -f "${REF_DIR}/ddl_core.sql" 2>/tmp/kingbase_stat_snapshot_init_core.err; then
    echo "❌ 核心基础设施初始化失败，详情："
    cat /tmp/kingbase_stat_snapshot_init_core.err
    FAILED_ITEMS+=("ddl_core.sql: 初始化失败，见上方错误")
fi

# 探测并按需初始化可选扩展视图（结果与失败均不阻断主流程）
psql_main -f "${REF_DIR}/ddl_optional.sql" 2>/tmp/kingbase_stat_snapshot_init_optional.err \
    || FAILED_ITEMS+=("ddl_optional.sql: 部分可选视图初始化失败（可能实例版本不支持，属正常现象）")

# 遍历所有非模板数据库，初始化库级历史表
DB_LIST=$(psql_main -Atc "SELECT datname FROM pg_database WHERE datistemplate = false;")
for DB in $DB_LIST; do
    CONN_DB="host=${PGHOST} port=${PGPORT} user=${PGUSER} dbname=${DB}"
    if ! psql "$CONN_DB" -v ON_ERROR_STOP=1 -f "${REF_DIR}/ddl_perdb.sql" 2>/tmp/kingbase_stat_snapshot_init_perdb.err; then
        echo "❌ 数据库 ${DB} 的库级基础设施初始化失败："
        cat /tmp/kingbase_stat_snapshot_init_perdb.err
        FAILED_ITEMS+=("${DB}: 库级 DDL 初始化失败")
    fi
done

if [[ "$MODE" == "init" ]]; then
    echo "== 初始化完成 =="
    if [[ ${#FAILED_ITEMS[@]} -gt 0 ]]; then
        printf '失败项:\n'; printf '  - %s\n' "${FAILED_ITEMS[@]}"
    else
        echo "失败项: 无"
    fi
    exit 0
fi

echo "== Step 2: 执行一次快照采集 =="

# --- 实例级采集：sys_stat_statements + pg_stat_activity，同一事务 ---
# \gset 是 psql 元命令，必须通过 -f 文件方式传入（-c 不支持）
INSTANCE_SQL_FILE=$(mktemp -t kingbase_snapshot_instance.XXXXXX.sql)
cat > "$INSTANCE_SQL_FILE" <<'EOF'
BEGIN;
INSERT INTO stat_snapshot.snapshots (snapshot_level, source_reset_time, comment)
VALUES ('instance',
        (SELECT sys_stat_statements_get_reset_time()),
        'run_snapshot.sh 自动采集')
RETURNING snapshot_id AS snapshot_id \gset

INSERT INTO stat_snapshot.stat_statements_history
SELECT :snapshot_id, now(), s.* FROM public.sys_stat_statements s;

INSERT INTO stat_snapshot.stat_activity_history
SELECT :snapshot_id, now(), a.* FROM pg_stat_activity a
WHERE a.state IS DISTINCT FROM 'idle'
   OR (SELECT count(*) FROM pg_stat_activity) <= 100;
COMMIT;

SELECT :snapshot_id AS snapshot_id;
EOF

if ! psql_main -v ON_ERROR_STOP=1 -f "$INSTANCE_SQL_FILE" 2>/tmp/kingbase_stat_snapshot_collect.err; then
    echo "❌ 实例级采集失败："
    cat /tmp/kingbase_stat_snapshot_collect.err
    FAILED_ITEMS+=("实例级采集: 事务已回滚")
else
    SNAPSHOT_ID=$(psql_main -Atc "SELECT max(snapshot_id) FROM stat_snapshot.snapshots WHERE snapshot_level='instance';")
    SS_ROWS=$(psql_main -Atc "SELECT count(*) FROM stat_snapshot.stat_statements_history WHERE snapshot_id=${SNAPSHOT_ID};")
    SA_ROWS=$(psql_main -Atc "SELECT count(*) FROM stat_snapshot.stat_activity_history WHERE snapshot_id=${SNAPSHOT_ID};")
    echo "✅ 实例级快照 ID=${SNAPSHOT_ID}: sys_stat_statements ${SS_ROWS} 行, pg_stat_activity ${SA_ROWS} 行"
fi
rm -f "$INSTANCE_SQL_FILE"

# --- 库级采集：遍历每个非模板库 ---
for DB in $DB_LIST; do
    CONN_DB="host=${PGHOST} port=${PGPORT} user=${PGUSER} dbname=${DB}"
    DB_SQL_FILE=$(mktemp -t kingbase_snapshot_db.XXXXXX.sql)
    cat > "$DB_SQL_FILE" <<EOF
BEGIN;
INSERT INTO stat_snapshot.snapshots (snapshot_level, database_name, source_reset_time)
VALUES ('database', current_database(),
        (SELECT stats_reset FROM pg_stat_database WHERE datname = current_database()))
RETURNING snapshot_id AS snapshot_id \gset

INSERT INTO stat_snapshot.stat_user_tables_history SELECT :snapshot_id, now(), t.* FROM pg_stat_user_tables t;
INSERT INTO stat_snapshot.stat_user_indexes_history SELECT :snapshot_id, now(), i.* FROM pg_stat_user_indexes i;
INSERT INTO stat_snapshot.statio_user_tables_history SELECT :snapshot_id, now(), t.* FROM pg_statio_user_tables t;
INSERT INTO stat_snapshot.statio_user_indexes_history SELECT :snapshot_id, now(), i.* FROM pg_statio_user_indexes i;
COMMIT;
EOF
    if ! psql "$CONN_DB" -v ON_ERROR_STOP=1 -f "$DB_SQL_FILE" 2>/tmp/kingbase_stat_snapshot_collect_db.err; then
        echo "❌ 数据库 ${DB} 采集失败："
        cat /tmp/kingbase_stat_snapshot_collect_db.err
        FAILED_ITEMS+=("${DB}: 库级采集失败，事务已回滚")
        rm -f "$DB_SQL_FILE"
        continue
    fi
    DB_SNAP_ID=$(psql "$CONN_DB" -Atc "SELECT max(snapshot_id) FROM stat_snapshot.snapshots WHERE database_name='${DB}';")
    T_ROWS=$(psql "$CONN_DB" -Atc "SELECT count(*) FROM stat_snapshot.stat_user_tables_history WHERE snapshot_id=${DB_SNAP_ID};")
    I_ROWS=$(psql "$CONN_DB" -Atc "SELECT count(*) FROM stat_snapshot.stat_user_indexes_history WHERE snapshot_id=${DB_SNAP_ID};")
    echo "✅ 库 ${DB} 快照 ID=${DB_SNAP_ID}: pg_stat_user_tables ${T_ROWS} 行, pg_stat_user_indexes ${I_ROWS} 行"
    rm -f "$DB_SQL_FILE"
done

END_TS=$(date +%s)
echo "== 采集完成，总耗时 $((END_TS - START_TS)) 秒 =="
if [[ ${#FAILED_ITEMS[@]} -gt 0 ]]; then
    echo "失败项:"; printf '  - %s\n' "${FAILED_ITEMS[@]}"
else
    echo "失败项: 无"
fi