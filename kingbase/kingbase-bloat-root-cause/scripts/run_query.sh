#!/usr/bin/env bash
# kingbase-bloat-root-cause: 安全执行只读诊断查询的 psql 封装脚本
#
# 用法：
#   PGPASSWORD='<password>' ./run_query.sh -h <host> -p <port> -U <user> -d <dbname> -f <sql_file>
#   PGPASSWORD='<password>' ./run_query.sh -h <host> -p <port> -U <user> -d <dbname> -c "<sql>"
#
# 连接参数解析优先级（与 SKILL.md 一致）：
#   1. 命令行 -h/-p/-U/-d 显式参数
#   2. PG 兼容环境变量 PGHOST/PGPORT/PGUSER/PGDBNAME/PGPASSWORD
#   3. KingbaseES 专属环境变量 KINGBASE_HOST/KINGBASE_PORT/KINGBASE_USER/
#      KINGBASE_DB/KINGBASE_PASSWORD
#   4. 内置默认（127.0.0.1:5432, kingbase/kingbase，仅供本地测试）
#
# 设计原则：
#   - 密码只通过 PGPASSWORD 环境变量在当前进程传递，不写入任何文件、不打印到日志。
#   - 默认以只读方式连接（-c 'default_transaction_read_only=on'），
#     即使误传入了写操作 SQL 也会被数据库拒绝执行，作为最后一道防线。
#   - 输出使用对齐表格，方便后续解析，不做任何自动重试写操作。
#   - 显式拒绝参数 -X/--no-psqlrc 与 psql 同名 flag 冲突，保持原始 psql 行为。

set -euo pipefail

HOST=""
PORT=""
USER=""
DBNAME=""
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

# 1. 命令行参数优先（-h/-p/-U/-d）
# 2. PG 兼容环境变量（PGHOST/PGPORT/PGUSER/PGDBNAME/PGPASSWORD）
# 3. KingbaseES 专属环境变量（KINGBASE_HOST/KINGBASE_PORT/...）
# 4. 内置默认（仅供本地测试）
: "${HOST:=${PGHOST:-${KINGBASE_HOST:-127.0.0.1}}}"
: "${PORT:=${PGPORT:-${KINGBASE_PORT:-5432}}}"
: "${USER:=${PGUSER:-${KINGBASE_USER:-kingbase}}}"
: "${DBNAME:=${PGDBNAME:-${KINGBASE_DB:-kingbase}}}"

# PGPASSWORD 也按优先级读取：用户提供的环境变量 > PG* > KINGBASE_*
if [[ -z "${PGPASSWORD:-}" ]]; then
  if [[ -n "${KINGBASE_PASSWORD:-}" ]]; then
    export PGPASSWORD="${KINGBASE_PASSWORD}"
  fi
fi

if [[ -z "$HOST" || -z "$USER" ]]; then
  echo "错误：必须提供主机与用户（-h/-U 或 PGHOST/PGUSER 或 KINGBASE_HOST/KINGBASE_USER）" >&2
  exit 1
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "错误：请通过 PGPASSWORD 环境变量提供密码，不要作为命令行参数传递（会被写入 shell 历史）" >&2
  echo "      也可以通过 KINGBASE_PASSWORD 环境变量提供（PGPASSWORD 优先）" >&2
  exit 1
fi

if [[ -z "$SQL_FILE" && -z "$SQL_CMD" ]]; then
  echo "错误：必须通过 -f 指定 SQL 文件，或通过 -c 指定单条 SQL" >&2
  exit 1
fi

# 强制只读事务作为最后一道防线；即使误传入了 DDL/DML/写操作也会被数据库拒绝
COMMON_ARGS=(-h "$HOST" -p "$PORT" -U "$USER" -d "$DBNAME"
  -v ON_ERROR_STOP=1
  -c 'SET default_transaction_read_only = on;')

if [[ -n "$SQL_FILE" ]]; then
  psql "${COMMON_ARGS[@]}" -f "$SQL_FILE"
else
  psql "${COMMON_ARGS[@]}" -c "$SQL_CMD"
fi