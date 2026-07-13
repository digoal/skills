#!/usr/bin/env bash
# pg-parameter-tuning-advisor: 操作系统 / 存储 / 网络侧只读采集脚本
#
# 用途：在已获得用户授权的前提下（同机执行，或通过 SSH 登录到数据库所在主机），
#       采集 CPU / 内存 / 磁盘 / 文件系统 / 网络 等只读指标，供参数调优分析使用。
#
# 安全声明：
#   - 全程只读，不做任何写入、重启、kill 进程等操作。
#   - 不需要 root 权限即可执行的部分会尽量用普通权限命令；
#     部分命令（如 iostat 需要 sysstat 包）若未安装会跳过并提示，不自动安装。
#   - 若通过 SSH 远程执行，本脚本本身不处理 SSH 连接逻辑，
#     由调用方（Agent）负责 `ssh user@host 'bash -s' < collect_os_metrics.sh` 或等效方式。
#
# 用法：
#   bash collect_os_metrics.sh [PG_DATA_DIRECTORY]
#   PG_DATA_DIRECTORY 可选，传入后会额外分析数据目录所在磁盘/文件系统。

set -u

PG_DATA_DIR="${1:-}"

section () {
  echo ""
  echo "===== $1 ====="
}

has_cmd () {
  command -v "$1" >/dev/null 2>&1
}

section "主机信息"
hostname
uname -a

section "CPU"
if has_cmd lscpu; then
  lscpu
else
  echo "lscpu 未安装，跳过"
fi
echo "逻辑核数: $(nproc 2>/dev/null || echo 未知)"

section "内存"
if has_cmd free; then
  free -h
else
  echo "free 未安装，跳过"
fi

section "Swap 使用情况"
if has_cmd swapon; then
  swapon --show 2>/dev/null || echo "无 swap 或无法读取"
fi

section "磁盘设备与类型 (ROTA=1 机械盘 / ROTA=0 SSD-NVMe)"
if has_cmd lsblk; then
  lsblk -d -o NAME,ROTA,SIZE,TYPE,MODEL 2>/dev/null
else
  echo "lsblk 未安装，跳过"
fi

section "磁盘 IO 压力采样 (3 次, 每次间隔 1s, 仅短时采样)"
if has_cmd iostat; then
  iostat -x 1 3
else
  echo "iostat 未安装（sysstat 包），跳过。建议安装后重新采集获得更准确的 IO 指标。"
fi

section "文件系统与挂载信息"
df -hT

if [ -n "$PG_DATA_DIR" ]; then
  section "数据目录所在挂载点 (data_directory=$PG_DATA_DIR)"
  df -hT "$PG_DATA_DIR" 2>/dev/null || echo "无法定位该路径，请确认路径是否可读"
  mount | grep " $(df --output=target "$PG_DATA_DIR" 2>/dev/null | tail -1) " 2>/dev/null
fi

section "IO 调度器 (各块设备)"
for dev in /sys/block/*/queue/scheduler; do
  if [ -f "$dev" ]; then
    echo "$dev: $(cat "$dev")"
  fi
done

section "Transparent Huge Pages 状态"
if [ -f /sys/kernel/mm/transparent_hugepage/enabled ]; then
  cat /sys/kernel/mm/transparent_hugepage/enabled
else
  echo "未找到 THP 配置文件"
fi

section "内核内存相关 sysctl"
sysctl vm.swappiness vm.overcommit_memory vm.overcommit_ratio 2>/dev/null

section "网络连接概览"
if has_cmd ss; then
  ss -s
else
  echo "ss 未安装，跳过"
fi

section "网络相关内核参数"
sysctl net.core.somaxconn net.ipv4.tcp_max_syn_backlog 2>/dev/null

section "文件句柄限制"
ulimit -n

section "正在运行的 postgres 进程（确认是否同机）"
if has_cmd pgrep; then
  pgrep -a postgres 2>/dev/null | head -10
else
  ps -ef | grep '[p]ostgres' | head -10
fi

echo ""
echo "===== 采集完成 ====="
