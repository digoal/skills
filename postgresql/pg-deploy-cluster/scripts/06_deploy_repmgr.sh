#!/usr/bin/env bash
# 06_deploy_repmgr.sh
# 用途：基于 references/repmgr.conf.template 渲染 repmgr.conf，注册主库/从库，
#       可选启动 repmgrd 实现自动故障转移。
# 用法：
#   角色=primary: ./06_deploy_repmgr.sh primary <node_id> <node_name> <this_ip> <pg_data_dir> <pg_port> <repmgrd_enable:yes|no>
#   角色=standby: ./06_deploy_repmgr.sh standby <node_id> <node_name> <this_ip> <pg_data_dir> <pg_port> <repmgrd_enable:yes|no> <primary_ip>

set -euo pipefail

ROLE="${1:?用法: $0 <primary|standby> <node_id> <node_name> <this_ip> <pg_data_dir> <pg_port> <repmgrd_enable> [primary_ip]}"
NODE_ID="${2:?缺少 node_id}"
NODE_NAME="${3:?缺少 node_name}"
THIS_IP="${4:?缺少本机 IP}"
PG_DATA_DIR="${5:?缺少数据目录}"
PG_PORT="${6:-5432}"
REPMGRD_ENABLE="${7:-no}"

TEMPLATE="$(dirname "$0")/../references/repmgr.conf.template"
[[ -f "$TEMPLATE" ]] || { echo "未找到模板 ${TEMPLATE}" >&2; exit 1; }

OUT="/etc/repmgr.conf"

sed \
  -e "s#__NODE_ID__#${NODE_ID}#g" \
  -e "s#__NODE_NAME__#${NODE_NAME}#g" \
  -e "s#__THIS_IP__#${THIS_IP}#g" \
  -e "s#__PG_DATA_DIR__#${PG_DATA_DIR}#g" \
  -e "s#__PG_PORT__#${PG_PORT}#g" \
  "$TEMPLATE" > "$OUT"

chown postgres:postgres "$OUT"
chmod 600 "$OUT"
echo "==== 已生成 ${OUT} ===="

case "$ROLE" in
  primary)
    echo "==== 注册主库 ===="
    sudo -u postgres repmgr -f "$OUT" primary register
    ;;
  standby)
    PRIMARY_IP="${8:?standby 模式需提供 primary_ip}"
    echo "==== 从主库 ${PRIMARY_IP} clone 数据（若 04 脚本已用 pg_basebackup 完成可跳过 clone，仅执行 register） ===="
    sudo -u postgres repmgr -f "$OUT" standby register
    ;;
  *)
    echo "未知角色: ${ROLE}（应为 primary|standby）" >&2
    exit 1
    ;;
esac

if [[ "$REPMGRD_ENABLE" == "yes" ]]; then
  echo "==== 启动 repmgrd 以支持自动故障转移 ===="
  systemctl enable --now repmgrd
else
  echo "提示：repmgrd 未启用，当前为手动切换模式，故障发生时需人工执行 'repmgr standby switchover' 或 failover。"
fi

echo "==== 集群状态 ===="
sudo -u postgres repmgr -f "$OUT" cluster show
