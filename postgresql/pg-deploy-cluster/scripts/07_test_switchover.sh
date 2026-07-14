#!/usr/bin/env bash
# 07_test_switchover.sh
# 用途：执行一次正常手动切换（switchover），并记录耗时与验证结果，供最终报告使用。
# 用法：
#   Patroni: ./07_test_switchover.sh patroni <patroni_conf_path> <candidate_node_name>
#   repmgr : ./07_test_switchover.sh repmgr <repmgr_conf_path> <standby_node_name>
#
# 本脚本只做切换与验证，不做破坏性的“无确认执行”——调用前请确保已在对话中获得用户确认。

set -euo pipefail

HA_TYPE="${1:?用法: $0 <patroni|repmgr> <conf_path> <target_node_name>}"
CONF_PATH="${2:?缺少配置文件路径}"
TARGET_NODE="${3:?缺少目标节点名}"

START_TS="$(date -Iseconds)"
echo "==== [$START_TS] 开始 switchover 测试，目标节点: ${TARGET_NODE} ===="

case "$HA_TYPE" in
  patroni)
    patronictl -c "$CONF_PATH" switchover --force --candidate "$TARGET_NODE" || {
      echo "switchover 命令执行失败，请检查 patronictl 输出。" >&2; exit 1;
    }
    sleep 5
    echo "==== 切换后集群状态 ===="
    patronictl -c "$CONF_PATH" list
    ;;
  repmgr)
    sudo -u postgres repmgr -f "$CONF_PATH" standby switchover --siblings-follow || {
      echo "repmgr switchover 执行失败，请检查输出与日志。" >&2; exit 1;
    }
    sleep 5
    echo "==== 切换后集群状态 ===="
    sudo -u postgres repmgr -f "$CONF_PATH" cluster show
    ;;
  *)
    echo "未知类型: ${HA_TYPE}（应为 patroni|repmgr）" >&2
    exit 1
    ;;
esac

END_TS="$(date -Iseconds)"
echo "==== [$END_TS] switchover 测试完成 ===="
echo "开始时间: ${START_TS}"
echo "结束时间: ${END_TS}"
echo "请人工/后续脚本进一步验证：新主库是否可读写、旧主库是否已作为从库正常追增。"
