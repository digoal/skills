#!/usr/bin/env bash
# 03_configure_pg.sh
# 用途：根据节点内存自动计算推荐参数，生成 postgresql.conf 增量配置与 pg_hba.conf 增量条目，
#       写入前以 diff 形式展示，不直接覆盖用户已有的自定义配置。
# 用法：./03_configure_pg.sh <data_dir> <wal_archive_dir> <replica_ip_cidr> <mgmt_ip_cidr> [shared_preload_libs]

set -euo pipefail

DATA_DIR="${1:?用法: $0 <data_dir> <wal_archive_dir> <replica_ip_cidr> <mgmt_ip_cidr> [shared_preload_libs]}"
WAL_ARCHIVE_DIR="${2:?缺少 wal_archive_dir}"
REPLICA_CIDR="${3:?缺少允许复制连接的 CIDR（从库/管理节点网段）}"
MGMT_CIDR="${4:?缺少允许超级用户连接的管理网段 CIDR}"
PRELOAD_LIBS="${5:-}"

CONF_FILE="${DATA_DIR}/postgresql.conf"
HBA_FILE="${DATA_DIR}/pg_hba.conf"
[[ -f "$CONF_FILE" ]] || { echo "未找到 ${CONF_FILE}，请确认 initdb 已完成。" >&2; exit 1; }

TOTAL_MEM_KB="$(grep MemTotal /proc/meminfo | awk '{print $2}')"
TOTAL_MEM_MB=$(( TOTAL_MEM_KB / 1024 ))
SHARED_BUFFERS_MB=$(( TOTAL_MEM_MB * 25 / 100 ))
EFFECTIVE_CACHE_MB=$(( TOTAL_MEM_MB * 60 / 100 ))
MAINT_WORK_MEM_MB=$(( TOTAL_MEM_MB * 5 / 100 ))
[[ $MAINT_WORK_MEM_MB -gt 2048 ]] && MAINT_WORK_MEM_MB=2048
MAX_CONN=200
WORK_MEM_MB=$(( TOTAL_MEM_MB * 25 / 100 / MAX_CONN ))
[[ $WORK_MEM_MB -lt 4 ]] && WORK_MEM_MB=4

INCREMENT_FILE="$(mktemp)"
{
  echo "# ---- pg-deploy-cluster 自动生成（基于内存 ${TOTAL_MEM_MB}MB 计算），追加于 $(date -Iseconds) ----"
  echo "listen_addresses = '*'"
  echo "max_connections = ${MAX_CONN}"
  echo "shared_buffers = ${SHARED_BUFFERS_MB}MB"
  echo "effective_cache_size = ${EFFECTIVE_CACHE_MB}MB"
  echo "work_mem = ${WORK_MEM_MB}MB"
  echo "maintenance_work_mem = ${MAINT_WORK_MEM_MB}MB"
  echo "wal_level = replica"
  echo "max_wal_senders = 10"
  echo "max_replication_slots = 10"
  echo "wal_keep_size = 1024MB"
  echo "archive_mode = on"
  echo "archive_command = 'test ! -f ${WAL_ARCHIVE_DIR}/%f && cp %p ${WAL_ARCHIVE_DIR}/%f'"
  if [[ -n "$PRELOAD_LIBS" ]]; then
    echo "shared_preload_libraries = '${PRELOAD_LIBS}'"
  fi
} > "$INCREMENT_FILE"

echo "==== 以下是即将追加到 ${CONF_FILE} 的增量内容（未直接写入，请确认后再执行 apply） ===="
cat "$INCREMENT_FILE"
echo "==== diff 预览结束。确认无误后执行： cat '${INCREMENT_FILE}' >> '${CONF_FILE}' ===="

HBA_INCREMENT="$(mktemp)"
{
  echo "# ---- pg-deploy-cluster 自动生成，追加于 $(date -Iseconds) ----"
  echo "host    replication     replicator      ${REPLICA_CIDR}         scram-sha-256"
  echo "host    all             postgres        ${MGMT_CIDR}            scram-sha-256"
} > "$HBA_INCREMENT"

echo "==== 以下是即将追加到 ${HBA_FILE} 的增量内容 ===="
cat "$HBA_INCREMENT"
echo "==== diff 预览结束。确认无误后执行： cat '${HBA_INCREMENT}' >> '${HBA_FILE}' ===="

echo ""
echo "提示：本脚本只生成预览文件，不自动写入，请在用户确认 diff 后再手动或由 Agent 追加写入，"
echo "并注意 CIDR 范围应仅覆盖实际的从库/管理网段，禁止使用 0.0.0.0/0。"
