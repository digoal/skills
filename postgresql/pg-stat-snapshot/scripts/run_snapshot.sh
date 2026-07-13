#!/usr/bin/env bash
# ============================================================
# pg-stat-snapshot / scripts / run_snapshot.sh
#
# 用途：
#   1) 初始化基础设施（首次运行自动建表，重复运行安全幂等）
#   2) 执行一次完整快照采集（实例级 + 遍历所有非模板库的库级视图）
#   3) 输出采集报告（快照ID/时间/各视图行数/失败项/耗时）
#
# 连接信息通过环境变量传入，不在命令行明文拼接密码：
#   PGHOST PGPORT PGUSER PGPASSWORD（或提前配置 .pgpass）
#
# 用法：
#   PGHOST=xx PGPORT=5432 PGUSER=xx PGPASSWORD=xx ./run_snapshot.sh init      # 仅初始化
#   PGHOST=xx PGPORT=5432 PGUSER=xx PGPASSWORD=xx ./run_snapshot.sh collect  # 初始化(若需要)+采集一次
# ============================================================
set -uo pipefail

: "${PGHOST:?必须设置 PGHOST}"
: "${PGPORT:=5432}"
: "${PGUSER:?必须设置 PGUSER}"
: "${PGPASSWORD:?必须设置 PGPASSWORD 或提前配置 .pgpass}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REF_DIR="$(dirname "$SCRIPT_DIR")/references"
MODE="${1:-collect}"

CONN_MAIN="host=${PGHOST} port=${PGPORT} user=${PGUSER} dbname=postgres"
export PGPASSWORD

psql_main() { psql "$CONN_MAIN" -v ON_ERROR_STOP=1 "$@"; }

FAILED_ITEMS=()
START_TS=$(date +%s)

echo "== Step 0: 连接探测与版本识别 =="
VERSION_NUM=$(psql_main -Atc "SELECT current_setting('server_version_num');") || { echo "无法连接实例，请检查连接信息"; exit 1; }
echo "server_version_num = ${VERSION_NUM}"

HAS_PSS=$(psql_main -Atc "SELECT count(*) FROM pg_extension WHERE extname='pg_stat_statements';")
if [[ "$HAS_PSS" -eq 0 ]]; then
    echo "⚠️ pg_stat_statements 扩展未安装，请以有权限账号执行："
    echo "   CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
    echo "   （需已在 shared_preload_libraries 中配置并重启实例，否则本命令仍会失败）"
    FAILED_ITEMS+=("pg_stat_statements: 扩展未安装")
fi

echo "== Step 1: 初始化基础设施（幂等） =="
if ! psql_main -f "${REF_DIR}/ddl_core.sql" 2>/tmp/pg_stat_snapshot_init_core.err; then
    echo "❌ 核心基础设施初始化失败，详情："
    cat /tmp/pg_stat_snapshot_init_core.err
    FAILED_ITEMS+=("ddl_core.sql: 初始化失败，见上方错误")
fi

# 探测并按需初始化可选扩展视图（结果与失败均不阻断主流程）
psql_main -f "${REF_DIR}/ddl_optional.sql" 2>/tmp/pg_stat_snapshot_init_optional.err \
    || FAILED_ITEMS+=("ddl_optional.sql: 部分可选视图初始化失败（可能实例版本不支持，属正常现象）")

# 遍历所有非模板数据库，初始化库级历史表
DB_LIST=$(psql_main -Atc "SELECT datname FROM pg_database WHERE datistemplate = false;")
for DB in $DB_LIST; do
    CONN_DB="host=${PGHOST} port=${PGPORT} user=${PGUSER} dbname=${DB}"
    if ! psql "$CONN_DB" -v ON_ERROR_STOP=1 -f "${REF_DIR}/ddl_perdb.sql" 2>/tmp/pg_stat_snapshot_init_perdb.err; then
        echo "❌ 数据库 ${DB} 的库级基础设施初始化失败："
        cat /tmp/pg_stat_snapshot_init_perdb.err
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

# --- 实例级采集：pg_stat_statements + pg_stat_activity，同一事务 ---
INSTANCE_SQL=$(cat <<'EOF'
BEGIN;
INSERT INTO stat_snapshot.snapshots (snapshot_level, source_reset_time, comment)
VALUES ('instance', (SELECT stats_reset FROM pg_stat_statements_info), 'run_snapshot.sh 自动采集')
RETURNING snapshot_id \gset

INSERT INTO stat_snapshot.stat_statements_history
SELECT :snapshot_id, now(), s.* FROM pg_stat_statements s;

INSERT INTO stat_snapshot.stat_activity_history
SELECT :snapshot_id, now(), a.* FROM pg_stat_activity a
WHERE a.state IS DISTINCT FROM 'idle'
   OR (SELECT count(*) FROM pg_stat_activity) <= 100;
COMMIT;

\echo SNAPSHOT_ID::snapshot_id
SELECT :snapshot_id AS snapshot_id;
EOF
)

if ! INSTANCE_OUT=$(psql_main -v ON_ERROR_STOP=1 -c "$INSTANCE_SQL" 2>/tmp/pg_stat_snapshot_collect.err); then
    echo "❌ 实例级采集失败："
    cat /tmp/pg_stat_snapshot_collect.err
    FAILED_ITEMS+=("实例级采集: 事务已回滚")
else
    SNAPSHOT_ID=$(psql_main -Atc "SELECT max(snapshot_id) FROM stat_snapshot.snapshots WHERE snapshot_level='instance';")
    SS_ROWS=$(psql_main -Atc "SELECT count(*) FROM stat_snapshot.stat_statements_history WHERE snapshot_id=${SNAPSHOT_ID};")
    SA_ROWS=$(psql_main -Atc "SELECT count(*) FROM stat_snapshot.stat_activity_history WHERE snapshot_id=${SNAPSHOT_ID};")
    echo "✅ 实例级快照 ID=${SNAPSHOT_ID}: pg_stat_statements ${SS_ROWS} 行, pg_stat_activity ${SA_ROWS} 行"
fi

# --- 库级采集：遍历每个非模板库 ---
for DB in $DB_LIST; do
    CONN_DB="host=${PGHOST} port=${PGPORT} user=${PGUSER} dbname=${DB}"
    DB_SQL=$(cat <<EOF
BEGIN;
INSERT INTO stat_snapshot.snapshots (snapshot_level, database_name, source_reset_time)
VALUES ('database', current_database(),
        (SELECT stats_reset FROM pg_stat_database WHERE datname = current_database()))
RETURNING snapshot_id \gset

INSERT INTO stat_snapshot.stat_user_tables_history SELECT :snapshot_id, now(), t.* FROM pg_stat_user_tables t;
INSERT INTO stat_snapshot.stat_user_indexes_history SELECT :snapshot_id, now(), i.* FROM pg_stat_user_indexes i;
INSERT INTO stat_snapshot.statio_user_tables_history SELECT :snapshot_id, now(), t.* FROM pg_statio_user_tables t;
INSERT INTO stat_snapshot.statio_user_indexes_history SELECT :snapshot_id, now(), i.* FROM pg_statio_user_indexes i;
COMMIT;
EOF
)
    if ! psql "$CONN_DB" -v ON_ERROR_STOP=1 -c "$DB_SQL" 2>/tmp/pg_stat_snapshot_collect_db.err; then
        echo "❌ 数据库 ${DB} 采集失败："
        cat /tmp/pg_stat_snapshot_collect_db.err
        FAILED_ITEMS+=("${DB}: 库级采集失败，事务已回滚")
        continue
    fi
    DB_SNAP_ID=$(psql "$CONN_DB" -Atc "SELECT max(snapshot_id) FROM stat_snapshot.snapshots WHERE database_name='${DB}';")
    T_ROWS=$(psql "$CONN_DB" -Atc "SELECT count(*) FROM stat_snapshot.stat_user_tables_history WHERE snapshot_id=${DB_SNAP_ID};")
    I_ROWS=$(psql "$CONN_DB" -Atc "SELECT count(*) FROM stat_snapshot.stat_user_indexes_history WHERE snapshot_id=${DB_SNAP_ID};")
    echo "✅ 库 ${DB} 快照 ID=${DB_SNAP_ID}: pg_stat_user_tables ${T_ROWS} 行, pg_stat_user_indexes ${I_ROWS} 行"
done

END_TS=$(date +%s)
echo "== 采集完成，总耗时 $((END_TS - START_TS)) 秒 =="
if [[ ${#FAILED_ITEMS[@]} -gt 0 ]]; then
    echo "失败项:"; printf '  - %s\n' "${FAILED_ITEMS[@]}"
else
    echo "失败项: 无"
fi
