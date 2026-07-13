#!/usr/bin/env bash
# memory_check.sh
# 服务器整体内存 + PG 进程级内存只读体检。

set -euo pipefail

echo "=== free -h ==="
free -h

echo ""
echo "=== /proc/meminfo 关键字段 ==="
cat /proc/meminfo | grep -E "MemTotal|MemAvailable|SwapTotal|SwapFree|Cached|Buffers"

echo ""
echo "=== 可用内存/Swap 占比计算 ==="
MEM_TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_AVAIL_KB=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
SWAP_TOTAL_KB=$(grep SwapTotal /proc/meminfo | awk '{print $2}')
SWAP_FREE_KB=$(grep SwapFree /proc/meminfo | awk '{print $2}')

if [ "${MEM_TOTAL_KB}" -gt 0 ]; then
  AVAIL_PCT=$(awk -v a="${MEM_AVAIL_KB}" -v t="${MEM_TOTAL_KB}" 'BEGIN{printf "%.1f", a/t*100}')
  echo "MemAvailable 占比: ${AVAIL_PCT}%"
fi

if [ "${SWAP_TOTAL_KB}" -gt 0 ]; then
  SWAP_USED_PCT=$(awk -v f="${SWAP_FREE_KB}" -v t="${SWAP_TOTAL_KB}" 'BEGIN{printf "%.1f", (t-f)/t*100}')
  echo "Swap 使用占比: ${SWAP_USED_PCT}%"
else
  echo "Swap 未配置"
fi

echo ""
echo "=== PG 进程内存排序 (TOP 30, 按 %MEM) ==="
ps aux --sort=-%mem | grep '[p]ostgres' | head -30

echo ""
echo "=== 高内存进程明细 (RSS>500MB 或 %MEM>10%) ==="
ps aux --sort=-%mem | grep '[p]ostgres' | awk '$4>10 || $6>512000 {print}'
