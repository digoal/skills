#!/usr/bin/env bash
# 02_init_cluster.sh
# 用途：创建数据/归档/日志目录并执行 initdb，配置超级用户密码与复制用户。
# 用法：PGSUPERPW=xxx PGREPLPW=yyy ./02_init_cluster.sh <pg_version> <data_dir> <wal_archive_dir> <log_dir>
#
# ⚠️ 破坏性操作：若 <data_dir> 已存在且非空，脚本会拒绝执行并退出，不会覆盖数据。
# 密码只通过环境变量 PGSUPERPW / PGREPLPW 传入，不接受命令行参数，不出现在 ps 输出中。

set -euo pipefail

PG_VERSION="${1:?用法: $0 <pg_version> <data_dir> <wal_archive_dir> <log_dir>}"
DATA_DIR="${2:?缺少 data_dir}"
WAL_ARCHIVE_DIR="${3:?缺少 wal_archive_dir}"
LOG_DIR="${4:?缺少 log_dir}"

: "${PGSUPERPW:?请通过环境变量 PGSUPERPW 提供超级用户密码，不要作为命令行参数传递}"
: "${PGREPLPW:?请通过环境变量 PGREPLPW 提供复制用户密码，不要作为命令行参数传递}"

PGBIN="/usr/pgsql-${PG_VERSION}/bin"
[[ -d "$PGBIN" ]] || PGBIN="/usr/lib/postgresql/${PG_VERSION}/bin"
[[ -d "$PGBIN" ]] || { echo "未找到 PostgreSQL ${PG_VERSION} 的 bin 目录，请确认已完成安装。" >&2; exit 1; }

if [[ -d "$DATA_DIR" ]] && [[ -n "$(ls -A "$DATA_DIR" 2>/dev/null)" ]]; then
  echo "❌ 目标数据目录 ${DATA_DIR} 已存在且非空，为防止覆盖数据，脚本已中止。" >&2
  echo "   如确认可以清空，请人工备份/清理后再重新执行本脚本。" >&2
  exit 1
fi

echo "==== 创建目录并设置属主 ===="
mkdir -p "$DATA_DIR" "$WAL_ARCHIVE_DIR" "$LOG_DIR"
chown -R postgres:postgres "$DATA_DIR" "$WAL_ARCHIVE_DIR" "$LOG_DIR"
chmod 0700 "$DATA_DIR"

echo "==== 执行 initdb（密码通过临时 pwfile 传递，用后即删） ===="
PWFILE="$(mktemp)"
trap 'rm -f "$PWFILE"' EXIT
printf '%s' "$PGSUPERPW" > "$PWFILE"
chmod 600 "$PWFILE"

sudo -u postgres "${PGBIN}/initdb" \
  -D "$DATA_DIR" \
  -U postgres \
  --pwfile="$PWFILE" \
  --auth-local=scram-sha-256 \
  --auth-host=scram-sha-256 \
  -E UTF8

rm -f "$PWFILE"
trap - EXIT

echo "==== 临时启动实例以创建复制角色 ===="
sudo -u postgres "${PGBIN}/pg_ctl" -D "$DATA_DIR" -l "${LOG_DIR}/init-startup.log" -w start

sudo -u postgres "${PGBIN}/psql" -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'replicator') THEN
    CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '${PGREPLPW}';
  END IF;
END
\$\$;
SQL

echo "==== 关闭临时实例，等待后续统一配置与正式启动 ===="
sudo -u postgres "${PGBIN}/pg_ctl" -D "$DATA_DIR" -m fast -w stop

echo "==== initdb 与角色初始化完成 ===="
echo "数据目录: ${DATA_DIR}"
echo "归档目录: ${WAL_ARCHIVE_DIR}"
echo "日志目录: ${LOG_DIR}"
