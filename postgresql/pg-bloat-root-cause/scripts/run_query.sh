#!/usr/bin/env bash
# pg-bloat-root-cause: 安全执行只读诊断查询的 psql 封装脚本
#
# 用法：
#   PGPASSWORD='<password>' ./run_query.sh -h <host> -p <port> -U <user> -d <dbname> -f <sql_file>
#   PGPASSWORD='<password>' ./run_query.sh -h <host> -p <port> -U <user> -d <dbname> -c "<sql>"
#
# 设计原则：
#   - 密码只通过 PGPASSWORD 环境变量在当前进程传递，不写入任何文件、不打印到日志。
#   - 默认以只读方式连接（-c 'default_transaction_read_only=on'），
#     即使误传入了写操作 SQL 也会被数据库拒绝执行，作为最后一道防线。
#   - 输出使用 --csv 或对齐表格，方便后续解析，不做任何自动重试写操作。

set -euo pipefail

HOST=""
PORT="5432"
USER=""
DBNAME="postgres"
SQL_FILE=""
SQL_CMD=""

while getopts "h:p:U:d:f:c:" opt; do
  case "$opt" in
    h) HOST="$OPTARG" ;;
    p) PORT="$OPTARG" ;;
    U) USER="$OPTARG" ;;
    d) DBNAME="$OPTARG" ;;
    f) SQL_FILE="$OPTARG" ;;
    c) SQL_CMD="$OPTARG" ;;
    *) echo "Usage: $0 -h host -p port -U user -d dbname [-f sql_file | -c sql_command]" >&2; exit 1 ;;
  esac
done

if [[ -z "$HOST" || -z "$USER" ]]; then
  echo "错误：必须提供 -h（主机）和 -U（用户名）" >&2
  exit 1
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "错误：请通过 PGPASSWORD 环境变量提供密码，不要作为命令行参数传递（会被写入 shell 历史）" >&2
  exit 1
fi

if [[ -z "$SQL_FILE" && -z "$SQL_CMD" ]]; then
  echo "错误：必须通过 -f 指定 SQL 文件，或通过 -c 指定单条 SQL" >&2
  exit 1
fi

COMMON_ARGS=(-h "$HOST" -p "$PORT" -U "$USER" -d "$DBNAME"
  -v ON_ERROR_STOP=1
  -c 'SET default_transaction_read_only = on;')

if [[ -n "$SQL_FILE" ]]; then
  psql "${COMMON_ARGS[@]}" -f "$SQL_FILE"
else
  psql "${COMMON_ARGS[@]}" -c "$SQL_CMD"
fi
