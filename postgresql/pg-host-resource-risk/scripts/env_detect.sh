#!/usr/bin/env bash
# env_detect.sh
# 判断当前执行环境是否就是 PostgreSQL 数据库服务器本地。
# 用法: env_detect.sh <db_server_ip_from_inet_server_addr>
#
# 只读检测，不做任何修改。
# 输出:
#   LOCAL_MATCH=yes|no
#   PG_PROCESS_FOUND=yes|no
#   本地 IP 列表
#   本地是否存在正在运行的 postgres 主进程

set -euo pipefail

DB_SERVER_IP="${1:-}"

echo "=== 本地 IP 列表 ==="
LOCAL_IPS=$(hostname -I 2>/dev/null || echo "")
echo "${LOCAL_IPS}"

echo "=== 当前用户 ==="
whoami

echo "=== 本地 postgres 主进程 ==="
PG_PROC=$(ps aux | grep '[p]ostgres' | grep -E 'postgres( -D|:)| /usr/.*postgres$' || true)
if [ -n "${PG_PROC}" ]; then
  echo "${PG_PROC}"
  PG_PROCESS_FOUND="yes"
else
  echo "未发现本地 postgres 主进程"
  PG_PROCESS_FOUND="no"
fi

LOCAL_MATCH="no"
if [ -n "${DB_SERVER_IP}" ]; then
  for ip in ${LOCAL_IPS}; do
    if [ "${ip}" = "${DB_SERVER_IP}" ]; then
      LOCAL_MATCH="yes"
      break
    fi
  done
fi

echo "=== 判定结果 ==="
echo "LOCAL_MATCH=${LOCAL_MATCH}"
echo "PG_PROCESS_FOUND=${PG_PROCESS_FOUND}"

if [ "${LOCAL_MATCH}" = "yes" ] && [ "${PG_PROCESS_FOUND}" = "yes" ]; then
  echo "RESULT=LOCAL_MODE"
else
  echo "RESULT=REMOTE_MODE_NEEDED"
fi
