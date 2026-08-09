#!/usr/bin/env bash
# kingbase-load-spike-forensics: 操作系统 / 存储 / 网络侧只读取证脚本
# 用法: ./collect_os_metrics.sh "2026-08-09 02:00:00" "2026-08-09 03:00:00"
# 说明: 全部为只读命令，不修改任何系统配置；若 sysstat 未采集历史数据，
#       sar 相关命令会报错或返回空，此时需如实在报告中标注该维度证据缺失。

set -uo pipefail

START="${1:-}"
END="${2:-}"

if [[ -z "$START" || -z "$END" ]]; then
  echo "用法: $0 '<开始时间 YYYY-MM-DD HH:MM:SS>' '<结束时间 YYYY-MM-DD HH:MM:SS>'"
  exit 1
fi

# macOS 与 Linux 的 date 命令语法不同，先尝试 GNU date，再 fallback BSD
START_HM=$(date -d "$START" +%H:%M:%S 2>/dev/null || date -j -f "%Y-%m-%d %H:%M:%S" "$START" +%H:%M:%S 2>/dev/null || echo "")
END_HM=$(date -d "$END" +%H:%M:%S 2>/dev/null || date -j -f "%Y-%m-%d %H:%M:%S" "$END" +%H:%M:%S 2>/dev/null || echo "")

echo "===== 0. 时区与基础信息 ====="
command -v timedatectl &>/dev/null && timedatectl || date
uname -a
nproc 2>/dev/null || sysctl -n hw.ncpu
free -h 2>/dev/null || vm_stat
df -h
df -i 2>/dev/null || echo "[提示] df -i 不可用"

echo
echo "===== 1. CPU / Load / 内存 历史指标 (sar, 需 sysstat 已采集历史) ====="
if command -v sar &>/dev/null && [[ -n "$START_HM" ]]; then
  echo "--- CPU (user/system/iowait) ---"
  sar -u -s "$START_HM" -e "$END_HM" 2>&1 || echo "[提示] 无对应历史数据或 sar 未正确安装"
  echo "--- Load average / runqueue ---"
  sar -q -s "$START_HM" -e "$END_HM" 2>&1 || echo "[提示] 无对应历史数据"
  echo "--- 内存 ---"
  sar -r -s "$START_HM" -e "$END_HM" 2>&1 || echo "[提示] 无对应历史数据"
  echo "--- Swap / 换页 ---"
  sar -B -s "$START_HM" -e "$END_HM" 2>&1 || echo "[提示] 无对应历史数据"
else
  echo "[提示] 未安装 sar（sysstat），该维度改用 vmstat 当前基线 + dmesg/journalctl 事件日志佐证"
  vmstat 1 5 2>/dev/null || echo "[提示] vmstat 也不可用"
fi

echo
echo "===== 2. 内核/系统事件日志（OOM、段错误、文件系统错误等） ====="
echo "--- dmesg (OOM / killed process) ---"
command -v dmesg &>/dev/null && dmesg -T 2>/dev/null | grep -iE "oom|out of memory|killed process|segfault" | tail -n 50 || echo "[提示] dmesg 不可用或无 ring buffer 权限"

echo "--- journalctl 窗口内 warning 及以上 ---"
if command -v journalctl &>/dev/null; then
  journalctl --since "$START" --until "$END" -p warning --no-pager 2>&1 | tail -n 200
else
  echo "[提示] journalctl 不可用，改查 /var/log/messages"
  grep -iE "oom|segfault|kernel|error" /var/log/messages 2>/dev/null | tail -n 200
fi

echo
echo "===== 3. 存储：磁盘 IO 历史 / 数据库目录 ====="
if command -v sar &>/dev/null && [[ -n "$START_HM" ]]; then
  echo "--- 磁盘 tps / await / %util ---"
  sar -d -p -s "$START_HM" -e "$END_HM" 2>&1 || echo "[提示] 无对应历史数据"
else
  echo "--- 当前 iostat 基线（无历史数据时仅供参考） ---"
  command -v iostat &>/dev/null && iostat -x 1 5 || echo "[提示] iostat 未安装"
fi
echo "--- 数据盘剩余空间 ---"
df -h
# 数据目录环境变量优先，否则用默认 /home/kingbase/userdata/data
DATA_DIR="${KINGBASE_DATA_DIR:-/home/kingbase/userdata/data}"
if [[ -d "$DATA_DIR" ]]; then
  echo "--- 金仓数据目录（${DATA_DIR}）空间分布 ---"
  du -sh "$DATA_DIR" 2>/dev/null
  du -sh "$DATA_DIR"/* 2>/dev/null | sort -h | tail -n 10
  # WAL 目录在 PG 兼容 KB 中通常名为 pg_wal 或 wal
  ls -la "$DATA_DIR"/pg_wal "$DATA_DIR"/wal 2>/dev/null || echo "[提示] WAL 目录未找到（命名可能为 pg_wal 或 wal）"
fi

echo
echo "===== 4. cgroup CPU 限流（容器/K8s 部署场景） ====="
if [[ -f /sys/fs/cgroup/cpu.stat ]]; then
  echo "--- cgroup v2 ---"
  cat /sys/fs/cgroup/cpu.stat
elif [[ -f /sys/fs/cgroup/cpu/cpu.stat ]]; then
  echo "--- cgroup v1 ---"
  cat /sys/fs/cgroup/cpu/cpu.stat
else
  echo "[提示] 未检测到 cgroup CPU 限流文件，可能非容器环境或路径不同"
fi

echo
echo "===== 5. 网络：连接数与 TCP 质量 ====="
echo "--- ss 汇总 ---"
ss -s 2>/dev/null || netstat -s | head -20
echo "--- 5432 端口已建立连接数 ---"
ss -tan state established '( dport = :5432 or sport = :5432 )' 2>/dev/null | wc -l \
  || netstat -an | grep -E '5432.*ESTABLISHED' | wc -l
if command -v sar &>/dev/null && [[ -n "$START_HM" ]]; then
  echo "--- 网卡吞吐历史 ---"
  sar -n DEV -s "$START_HM" -e "$END_HM" 2>&1 || echo "[提示] 无对应历史数据"
  echo "--- TCP 重传等异常历史 ---"
  sar -n ETCP -s "$START_HM" -e "$END_HM" 2>&1 || echo "[提示] 无对应历史数据"
fi

echo
echo "===== 6. KB 后台进程检查（kingbase 应常驻以下后台进程） ====="
command -v ps &>/dev/null && ps -ef | grep -E "kingbase" | grep -v grep | awk '{print $NF}' | sort -u || echo "[提示] ps 不可用"

echo
echo "===== 采集完成，请结合数据库日志/统计视图做时间线对齐分析 ====="