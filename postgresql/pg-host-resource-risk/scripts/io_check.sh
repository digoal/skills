#!/usr/bin/env bash
# io_check.sh
# 磁盘 IO 使用率与等待只读体检。若 iostat/sar 不存在则提示缺失并降级。

set -euo pipefail

if command -v iostat &>/dev/null; then
  echo "=== iostat -x 1 3 ==="
  iostat -x 1 3
elif command -v sar &>/dev/null; then
  echo "=== sar -d 1 3 ==="
  sar -d 1 3
else
  echo "警告: 未检测到 iostat 或 sar，无法采集 IO 使用率/等待数据。"
  echo "请安装 sysstat 包: (dnf|yum|apt) install -y sysstat"
  exit 0
fi

echo ""
echo "=== 磁盘类型判断 (0=SSD, 1=HDD) ==="
for dev in /sys/block/*/queue/rotational; do
  devname=$(echo "${dev}" | awk -F'/' '{print $4}')
  rot=$(cat "${dev}" 2>/dev/null || echo "unknown")
  echo "${devname}: rotational=${rot}"
done
