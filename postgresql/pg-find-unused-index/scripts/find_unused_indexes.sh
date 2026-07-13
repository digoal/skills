#!/usr/bin/env bash
# pg-find-unused-index 批量扫描脚本
#
# 用法:
#   export PGPASSWORD='your_password'
#   ./find_unused_indexes.sh <host> <port> <admin_user> [dbname_regex_filter]
#
# 密码只从 PGPASSWORD 环境变量或 ~/.pgpass 读取，绝不作为命令行参数传入，
# 避免出现在 `ps` 进程列表或 shell 历史中。
#
# 依赖: psql（PostgreSQL client）

set -euo pipefail

HOST="${1:?用法: $0 <host> <port> <user> [dbname_regex_filter]}"
PORT="${2:?缺少端口}"
PGUSER="${3:?缺少用户名}"
DB_FILTER="${4:-.*}"   # 可选：只扫描名字匹配该正则的数据库

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_FILE="${SCRIPT_DIR}/find_unused_indexes.sql"

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "警告: 未检测到 PGPASSWORD 环境变量，将依赖 ~/.pgpass 或触发交互式输入。" >&2
fi

ADMIN_CONN="host=${HOST} port=${PORT} user=${PGUSER} dbname=postgres sslmode=prefer"

echo "==> 正在列出实例下所有可连接数据库..."
mapfile -t DATABASES < <(
  psql "${ADMIN_CONN}" -tAc "
    SELECT datname FROM pg_database
    WHERE datistemplate = false AND datallowconn = true
    ORDER BY datname;"
)

echo "==> 共发现 ${#DATABASES[@]} 个数据库"

for DB in "${DATABASES[@]}"; do
  if [[ ! "${DB}" =~ ${DB_FILTER} ]]; then
    continue
  fi
  echo ""
  echo "########################################"
  echo "## 数据库: ${DB}"
  echo "########################################"

  CONN="host=${HOST} port=${PORT} user=${PGUSER} dbname=${DB} sslmode=prefer"

  if ! psql "${CONN}" -c "SELECT 1" >/dev/null 2>&1; then
    echo "!! 跳过: 无法连接到数据库 ${DB}（权限不足或禁止连接）" >&2
    continue
  fi

  psql "${CONN}" -f "${SQL_FILE}"
done

echo ""
echo "==> 扫描完成。请结合每库输出中的 stats_age / instance_uptime 判断统计窗口是否足够长，"
echo "    并对 backs_constraint = true 的索引保持谨慎，不要仅凭 idx_scan = 0 直接删除。"
