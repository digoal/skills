#!/usr/bin/env bash
# kingbase-find-bloat: 安全执行只读诊断查询的 psql 封装脚本
#
# 用法：
#   PGPASSWORD='<password>' ./run_query.sh -h <host> -p <port> -U <user> -d <dbname> -f <sql_file>
#   PGPASSWORD='<password>' ./run_query.sh -h <host> -p <port> -U <user> -d <dbname> -c "<sql>"
#
# 连接参数解析优先级（与 SKILL.md 一致）：
#   1. 命令行 -h/-p/-U/-d 显式参数
#   2. PG 兼容环境变量 PGHOST/PGPORT/PGDBNAME/PGUSER/PGPASSWORD
#   3. 内置默认（127.0.0.1:5432, kingbase/kingbase，仅供本地测试）
#
# 设计原则：
#   - 密码只通过 PGPASSWORD 环境变量在当前进程传递，不写入任何文件、不打印到日志。
#   - 默认以只读方式连接（-c 'SET default_transaction_read_only = on;'），
#     即使误传入了写操作 SQL 也会被数据库拒绝执行，作为最后一道防线。
#   - 输出使用对齐表格，方便后续解析，不做任何自动重试写操作。
#   - KingbaseES 沿用 PG 客户端协议，标准 psql 与 KingbaseES 自带的 ksql 均可使用。

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
# 3. 内置默认（仅供本地测试）
: "${HOST:=${PGHOST:-127.0.0.1}}"
: "${PORT:=${PGPORT:-5432}}"
: "${USER:=${PGUSER:-kingbase}}"
: "${DBNAME:=${PGDBNAME:-kingbase}}"

# 密码优先级：PGPASSWORD 环境变量 > 内置默认（123456，仅本地测试用）；
# 必须 export，否则外部 psql 进程读不到（:= 赋值不会自动导出）
export PGPASSWORD="${PGPASSWORD:-123456}"

if [[ -z "$SQL_FILE" && -z "$SQL_CMD" ]]; then
  echo "错误：必须通过 -f 指定 SQL 文件，或通过 -c 指定单条 SQL" >&2
  exit 1
fi

# 客户端二进制：优先 psql，其次 KingbaseES 自带的 ksql（语法与 psql 兼容）
if command -v psql >/dev/null 2>&1; then
  PSQL_BIN=psql
elif command -v ksql >/dev/null 2>&1; then
  PSQL_BIN=ksql
else
  echo "错误：未找到 psql / ksql 客户端，请安装 postgresql-client 或 KingbaseES 客户端" >&2
  exit 1
fi

# 强制只读事务作为最后一道防线；即使误传入了 DDL/DML/写操作也会被数据库拒绝
COMMON_ARGS=(-h "$HOST" -p "$PORT" -U "$USER" -d "$DBNAME"
  -v ON_ERROR_STOP=1
  -c 'SET default_transaction_read_only = on;')

if [[ -n "$SQL_FILE" ]]; then
  "$PSQL_BIN" "${COMMON_ARGS[@]}" -f "$SQL_FILE"
else
  "$PSQL_BIN" "${COMMON_ARGS[@]}" -c "$SQL_CMD"
fi
