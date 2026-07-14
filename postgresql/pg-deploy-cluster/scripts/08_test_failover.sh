#!/usr/bin/env bash
# 08_test_failover.sh
# 用途：模拟主库故障（默认停止 PostgreSQL 服务，而非断网，以降低影响面），观察 HA 软件
#       是否完成故障转移，并在测试结束后尝试将原主库以从库身份重新加入集群。
# 用法：
#   ./08_test_failover.sh <patroni|repmgr> <conf_path> <failed_node_pg_service_name> [--network-cut]
#
# ⚠️ 本脚本会真实停止数据库服务（及可选的网络中断），必须仅在用户已明确确认的沙盒/
#    测试环境或已知悉风险的生产环境中执行。

set -euo pipefail

HA_TYPE="${1:?用法: $0 <patroni|repmgr> <conf_path> <pg_service_name> [--network-cut]}"
CONF_PATH="${2:?缺少配置文件路径}"
SERVICE_NAME="${3:?缺少目标节点 PostgreSQL 服务名（如 postgresql-16）}"
MODE="${4:-service-stop}"

START_TS="$(date -Iseconds)"
echo "==== [$START_TS] 开始 failover 测试，故障模拟方式: ${MODE} ===="

if [[ "$MODE" == "--network-cut" ]]; then
  echo "⚠️ 即将执行断网模拟（iptables 丢弃 5432 端口流量），仅在已获用户明确批准时使用。"
  iptables -A INPUT -p tcp --dport 5432 -j DROP
  iptables -A OUTPUT -p tcp --sport 5432 -j DROP
else
  echo "==== 停止目标节点 PostgreSQL 服务: ${SERVICE_NAME} ===="
  systemctl stop "$SERVICE_NAME"
fi

echo "==== 观察 HA 软件是否触发故障转移（最多等待 60 秒） ===="
case "$HA_TYPE" in
  patroni)
    for i in $(seq 1 30); do
      if patronictl -c "$CONF_PATH" list 2>/dev/null | grep -qi "Leader"; then
        echo "检测到新 Leader，故障转移已发生："
        patronictl -c "$CONF_PATH" list
        break
      fi
      sleep 2
    done
    ;;
  repmgr)
    echo "提示：若未启用 repmgrd 自动故障转移，需人工执行 'repmgr standby switchover' 完成切换。"
    sudo -u postgres repmgr -f "$CONF_PATH" cluster show || true
    ;;
  *)
    echo "未知类型: ${HA_TYPE}（应为 patroni|repmgr）" >&2
    ;;
esac

echo "==== 恢复原故障节点 ===="
if [[ "$MODE" == "--network-cut" ]]; then
  iptables -D INPUT -p tcp --dport 5432 -j DROP || true
  iptables -D OUTPUT -p tcp --sport 5432 -j DROP || true
  echo "已恢复网络连通性。"
else
  echo "服务已停止，是否将其重新加入集群作为从库，请根据 HA 类型手动确认后执行："
  echo "  Patroni: patronictl -c ${CONF_PATH} reinit <该节点名>"
  echo "  repmgr : repmgr -f ${CONF_PATH} node rejoin -d <primary_conninfo> --force-rewind (若需要)"
fi

END_TS="$(date -Iseconds)"
echo "==== [$END_TS] failover 测试记录完成 ===="
echo "开始时间: ${START_TS}"
echo "结束时间: ${END_TS}"
