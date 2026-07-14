#!/usr/bin/env bash
# 05_deploy_patroni.sh
# 用途：基于 references/patroni.yml.template 渲染出 patroni.yml，启动 Patroni 并验证 Leader 选举。
# 用法：
#   PGSUPERPW=xxx PGREPLPW=yyy ./05_deploy_patroni.sh \
#     <node_name> <scope> <this_ip> <pg_data_dir> <pg_bin_dir> <etcd_hosts_csv> <pg_port> <api_port>
#
# 前置：references/patroni.yml.template 必须存在于同仓库 references/ 目录。
# 安全说明：密码通过环境变量注入模板渲染过程，不落盘明文到脚本自身；生成的 patroni.yml
#           权限设为 600 且仅 postgres 用户可读。

set -euo pipefail

NODE_NAME="${1:?用法: $0 <node_name> <scope> <this_ip> <pg_data_dir> <pg_bin_dir> <etcd_hosts_csv> <pg_port> <api_port>}"
SCOPE="${2:?缺少 scope（集群名）}"
THIS_IP="${3:?缺少本机 IP}"
PG_DATA_DIR="${4:?缺少数据目录}"
PG_BIN_DIR="${5:?缺少 PostgreSQL bin 目录}"
ETCD_HOSTS="${6:?缺少 etcd 地址，逗号分隔，如 10.0.0.1:2379,10.0.0.2:2379}"
PG_PORT="${7:-5432}"
API_PORT="${8:-8008}"

: "${PGSUPERPW:?请通过环境变量 PGSUPERPW 提供}"
: "${PGREPLPW:?请通过环境变量 PGREPLPW 提供}"

TEMPLATE="$(dirname "$0")/../references/patroni.yml.template"
[[ -f "$TEMPLATE" ]] || { echo "未找到模板 ${TEMPLATE}" >&2; exit 1; }

OUT="/etc/patroni/patroni.yml"
mkdir -p "$(dirname "$OUT")"

sed \
  -e "s#__NODE_NAME__#${NODE_NAME}#g" \
  -e "s#__SCOPE__#${SCOPE}#g" \
  -e "s#__THIS_IP__#${THIS_IP}#g" \
  -e "s#__PG_DATA_DIR__#${PG_DATA_DIR}#g" \
  -e "s#__PG_BIN_DIR__#${PG_BIN_DIR}#g" \
  -e "s#__ETCD_HOSTS__#${ETCD_HOSTS}#g" \
  -e "s#__PG_PORT__#${PG_PORT}#g" \
  -e "s#__API_PORT__#${API_PORT}#g" \
  -e "s#__PGSUPERPW__#${PGSUPERPW}#g" \
  -e "s#__PGREPLPW__#${PGREPLPW}#g" \
  "$TEMPLATE" > "$OUT"

chown postgres:postgres "$OUT"
chmod 600 "$OUT"

echo "==== 已生成 ${OUT}（权限 600，仅 postgres 可读） ===="

echo "==== 启动 Patroni ===="
systemctl enable --now patroni

echo "==== 等待 Leader 选举（最多 30 秒） ===="
for i in $(seq 1 15); do
  if patronictl -c "$OUT" list 2>/dev/null | grep -qi "Leader"; then
    echo "Leader 选举成功："
    patronictl -c "$OUT" list
    exit 0
  fi
  sleep 2
done

echo "⚠️ 30 秒内未观察到 Leader，请检查 etcd 连通性与 patroni 日志（journalctl -u patroni）。" >&2
exit 1
