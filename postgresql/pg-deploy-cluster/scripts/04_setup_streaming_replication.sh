#!/usr/bin/env bash
# 04_setup_streaming_replication.sh
# 用途：启动主库、通过 pg_basebackup 从主库拉取数据搭建从库、启动从库并校验复制状态。
# 用法：
#   角色=primary: ./04_setup_streaming_replication.sh primary <pg_version> <data_dir> <log_dir>
#   角色=standby: PGREPLPW=xxx ./04_setup_streaming_replication.sh standby <pg_version> <data_dir> <log_dir> <primary_host> <primary_port>
#
# ⚠️ 破坏性操作（standby 模式）：pg_basebackup 会清空/重建 <data_dir>，
#    执行前脚本会检测目标目录，若非空将拒绝执行。

set -euo pipefail

ROLE="${1:?用法: $0 <primary|standby> <pg_version> <data_dir> <log_dir> [primary_host] [primary_port]}"
PG_VERSION="${2:?缺少 pg_version}"
DATA_DIR="${3:?缺少 data_dir}"
LOG_DIR="${4:?缺少 log_dir}"

PGBIN="/usr/pgsql-${PG_VERSION}/bin"
[[ -d "$PGBIN" ]] || PGBIN="/usr/lib/postgresql/${PG_VERSION}/bin"
[[ -d "$PGBIN" ]] || { echo "未找到 PostgreSQL ${PG_VERSION} 的 bin 目录。" >&2; exit 1; }

case "$ROLE" in
  primary)
    echo "==== 启动主库 ===="
    sudo -u postgres "${PGBIN}/pg_ctl" -D "$DATA_DIR" -l "${LOG_DIR}/primary-startup.log" -w start
    echo "==== 确认主库可接受复制连接 ===="
    sudo -u postgres "${PGBIN}/psql" -v ON_ERROR_STOP=1 -c "SELECT 1;" >/dev/null
    echo "主库已启动，等待从库通过 pg_basebackup 拉取数据。"
    ;;

  standby)
    PRIMARY_HOST="${5:?standby 模式需提供 primary_host}"
    PRIMARY_PORT="${6:-5432}"
    : "${PGREPLPW:?请通过环境变量 PGREPLPW 提供复制用户密码}"

    if [[ -d "$DATA_DIR" ]] && [[ -n "$(ls -A "$DATA_DIR" 2>/dev/null)" ]]; then
      echo "❌ 从库数据目录 ${DATA_DIR} 非空，pg_basebackup 会清空该目录，脚本已中止以防误删。" >&2
      echo "   如确认可以清空，请人工备份/清理后再重新执行。" >&2
      exit 1
    fi

    mkdir -p "$DATA_DIR"
    chown postgres:postgres "$DATA_DIR"
    chmod 0700 "$DATA_DIR"

    PGPASSFILE="$(mktemp)"
    trap 'rm -f "$PGPASSFILE"' EXIT
    echo "${PRIMARY_HOST}:${PRIMARY_PORT}:*:replicator:${PGREPLPW}" > "$PGPASSFILE"
    chmod 600 "$PGPASSFILE"
    chown postgres:postgres "$PGPASSFILE"

    echo "==== 从主库 ${PRIMARY_HOST}:${PRIMARY_PORT} 执行 pg_basebackup ===="
    sudo -u postgres PGPASSFILE="$PGPASSFILE" "${PGBIN}/pg_basebackup" \
      -h "$PRIMARY_HOST" -p "$PRIMARY_PORT" -U replicator \
      -D "$DATA_DIR" -Fp -Xs -P -R

    rm -f "$PGPASSFILE"
    trap - EXIT

    echo "==== 启动从库 ===="
    sudo -u postgres "${PGBIN}/pg_ctl" -D "$DATA_DIR" -l "${LOG_DIR}/standby-startup.log" -w start

    echo "==== 校验复制状态（从库侧 pg_stat_wal_receiver） ===="
    sleep 3
    sudo -u postgres "${PGBIN}/psql" -v ON_ERROR_STOP=1 -c \
      "SELECT status, received_lsn, latest_end_lsn FROM pg_stat_wal_receiver;"
    ;;

  *)
    echo "未知角色: ${ROLE}（应为 primary|standby）" >&2
    exit 1
    ;;
esac

echo "==== 完成 ===="
