#!/usr/bin/env bash
# 00_probe_env.sh
# 用途：探测目标节点的系统信息、资源、时间同步、防火墙/SELinux 状态、关键端口占用情况。
# 用法：./00_probe_env.sh <host> <ssh_user> <ssh_port> [extra_ports...]
#
# 安全说明：
#   - 本脚本仅通过 SSH 免密（推荐）或已配置的密钥连接目标主机，不接受明文密码参数。
#   - 若需要密码认证，请预先设置 SSHPASS 环境变量并安装 sshpass，脚本会自动识别；
#     禁止将密码写入本脚本或以命令行参数传入。
#   - 只读探测，不对目标主机做任何修改。

set -euo pipefail

HOST="${1:?用法: $0 <host> <ssh_user> <ssh_port> [extra_ports...]}"
SSH_USER="${2:?缺少 ssh_user}"
SSH_PORT="${3:?缺少 ssh_port}"
shift 3
EXTRA_PORTS=("$@")
DEFAULT_PORTS=(5432 8008 2379 2380)
ALL_PORTS=("${DEFAULT_PORTS[@]}" "${EXTRA_PORTS[@]}")

SSH_OPTS=(-p "$SSH_PORT" -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new)

ssh_run() {
  if [[ -n "${SSHPASS:-}" ]]; then
    sshpass -e ssh -p "$SSH_PORT" -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new "${SSH_USER}@${HOST}" "$@"
  else
    ssh "${SSH_OPTS[@]}" "${SSH_USER}@${HOST}" "$@"
  fi
}

echo "==== [${HOST}] 连通性检查 ===="
if ! ssh_run "echo connected" >/dev/null 2>&1; then
  echo "无法通过 SSH 连接到 ${HOST}:${SSH_PORT}，请检查凭据/网络后重试。" >&2
  exit 1
fi
echo "OK"

echo "==== [${HOST}] 系统信息 ===="
ssh_run '
  echo "--- OS ---"; cat /etc/os-release 2>/dev/null | grep -E "^(NAME|VERSION)="
  echo "--- Kernel/Arch ---"; uname -r; uname -m
  echo "--- CPU ---"; nproc
  echo "--- Memory ---"; free -h
  echo "--- Disk ---"; df -hT | grep -vE "tmpfs|devtmpfs"
'

echo "==== [${HOST}] 时间同步状态 ===="
ssh_run '
  if command -v chronyc &>/dev/null; then
    chronyc tracking 2>/dev/null || echo "chronyc 无法查询（服务可能未运行）"
  elif command -v ntpstat &>/dev/null; then
    ntpstat 2>/dev/null || echo "ntpstat 无法查询"
  else
    echo "未检测到 chrony/ntp，建议安装并启用时间同步服务"
  fi
'

echo "==== [${HOST}] 防火墙状态 ===="
ssh_run '
  if command -v firewall-cmd &>/dev/null && systemctl is-active firewalld &>/dev/null; then
    echo "firewalld: active"; firewall-cmd --list-ports 2>/dev/null
  elif command -v ufw &>/dev/null; then
    ufw status 2>/dev/null || true
  else
    echo "未检测到 firewalld/ufw，检查 iptables 规则数量:"; iptables -L -n 2>/dev/null | wc -l || true
  fi
'

echo "==== [${HOST}] SELinux 状态 ===="
ssh_run '
  if command -v getenforce &>/dev/null; then
    getenforce
  else
    echo "系统未安装 SELinux 工具（可能为 Debian/Ubuntu 系）"
  fi
'

echo "==== [${HOST}] 关键端口占用检查 ===="
for p in "${ALL_PORTS[@]}"; do
  ssh_run "ss -ltn 2>/dev/null | awk -v p=':$p\$' '\$4 ~ p {print}' | grep -q . && echo '端口 $p: 已被占用' || echo '端口 $p: 空闲'"
done

echo "==== [${HOST}] 探测完成 ===="
