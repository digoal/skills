#!/usr/bin/env bash
# network_check.sh
# 网络带宽使用率只读体检。优先 sar -n DEV，否则用 /proc/net/dev 两次采样估算速率。

set -euo pipefail

if command -v sar &>/dev/null; then
  echo "=== sar -n DEV 1 3 ==="
  sar -n DEV 1 3
else
  echo "警告: 未检测到 sar，使用 /proc/net/dev 两次采样估算速率 (间隔 1 秒)"
  echo "=== 采样 1 ==="
  cat /proc/net/dev
  sleep 1
  echo "=== 采样 2 (1秒后) ==="
  cat /proc/net/dev
fi

echo ""
echo "=== 网卡额定带宽 ==="
for iface_path in /sys/class/net/*/speed; do
  iface=$(echo "${iface_path}" | awk -F'/' '{print $5}')
  speed=$(cat "${iface_path}" 2>/dev/null || echo "unknown(可能是虚拟网卡或链路down)")
  echo "${iface}: ${speed} Mbps"
done

echo ""
echo "=== 可选交叉验证 (若已安装 iftop/nload，可手动执行) ==="
echo "iftop -t -s 3   # 或"
echo "nload -t 3"

echo ""
echo "=== 非 PG 端口流量排查 ==="
if command -v ss &>/dev/null; then
  ss -tup 2>/dev/null | head -50
else
  echo "ss 命令不可用，跳过端口连接排查"
fi
