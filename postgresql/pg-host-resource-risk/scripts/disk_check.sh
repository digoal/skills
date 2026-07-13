#!/usr/bin/env bash
# disk_check.sh
# 磁盘剩余空间只读体检。
# 用法: disk_check.sh <PGDATA> [wal_dir] [log_dir] [tablespace_dir1] [tablespace_dir2] ...
#
# 输出全量挂载点使用率，并对传入的关注目录逐一列出剩余空间；
# 对告警目录（剩余<20%或<100GB）追加 du 大文件溯源。

set -euo pipefail

PGDATA_DIR="${1:-}"
shift || true
EXTRA_DIRS=("$@")

echo "=== df -h 全量挂载点 ==="
df -h

CHECK_DIRS=()
[ -n "${PGDATA_DIR}" ] && CHECK_DIRS+=("${PGDATA_DIR}")
CHECK_DIRS+=("/tmp" "/")
for d in "${EXTRA_DIRS[@]}"; do
  [ -n "$d" ] && CHECK_DIRS+=("$d")
done

# 去重
declare -A seen
UNIQUE_DIRS=()
for d in "${CHECK_DIRS[@]}"; do
  if [ -z "${seen[$d]:-}" ]; then
    seen[$d]=1
    UNIQUE_DIRS+=("$d")
  fi
done

for dir in "${UNIQUE_DIRS[@]}"; do
  if [ -d "${dir}" ]; then
    echo ""
    echo "=== 关注目录: ${dir} ==="
    df -h "${dir}"

    # 计算剩余百分比与绝对值(GB)，判断是否需要溯源
    LINE=$(df -PBG "${dir}" | tail -1)
    AVAIL_GB=$(echo "${LINE}" | awk '{print $4}' | tr -d 'G')
    USE_PCT=$(echo "${LINE}" | awk '{print $5}' | tr -d '%')
    AVAIL_PCT=$((100 - USE_PCT))

    if [ "${AVAIL_PCT}" -lt 20 ] || [ "${AVAIL_GB}" -lt 100 ]; then
      echo "--- 该目录剩余空间告警，执行大文件溯源 (du -ah --max-depth=3, 可能耗时) ---"
      du -ah "${dir}" --max-depth=3 2>/dev/null | sort -rh | head -20 || echo "du 执行失败或权限不足"
    fi
  else
    echo ""
    echo "=== 关注目录: ${dir} (不存在，跳过) ==="
  fi
done
