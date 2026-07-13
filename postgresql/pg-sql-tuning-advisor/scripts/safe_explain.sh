#!/usr/bin/env bash
#
# safe_explain.sh —— 安全获取 PostgreSQL 执行计划
#
# 用途：
#   对只读 SELECT 直接 EXPLAIN (ANALYZE, BUFFERS, VERBOSE)。
#   对 DML（INSERT/UPDATE/DELETE/MERGE）强制包裹在事务中，
#   设置语句超时后执行 EXPLAIN ANALYZE，最后无条件 ROLLBACK，绝不 COMMIT。
#
# 用法：
#   PGPASSWORD='xxx' ./safe_explain.sh \
#       -h <host> -p <port> -U <user> -d <dbname> \
#       -f <sql_file>            # SQL 写在文件里，避免特殊字符/换行问题
#       [-t <statement_timeout>] # 默认 30s，DML 场景建议更保守，如 10s
#       [--dml]                  # 显式声明这是 DML，走事务+回滚路径；不加则按只读处理
#
# 安全说明：
#   - 密码只能通过 PGPASSWORD 环境变量传入，脚本不接受密码作为命令行参数，
#     避免密码出现在 `ps` 输出或 shell history 中。
#   - DML 路径下，无论 EXPLAIN ANALYZE 成功、失败还是超时，都会执行 ROLLBACK，
#     该脚本不提供、也不应被改造出任何 COMMIT 路径。

set -euo pipefail

HOST=""; PORT="5432"; USER=""; DBNAME=""; SQL_FILE=""; TIMEOUT="30s"; IS_DML="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h) HOST="$2"; shift 2 ;;
    -p) PORT="$2"; shift 2 ;;
    -U) USER="$2"; shift 2 ;;
    -d) DBNAME="$2"; shift 2 ;;
    -f) SQL_FILE="$2"; shift 2 ;;
    -t) TIMEOUT="$2"; shift 2 ;;
    --dml) IS_DML="true"; shift 1 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$HOST" || -z "$USER" || -z "$DBNAME" || -z "$SQL_FILE" ]]; then
  echo "缺少必要参数。用法见脚本头部注释。" >&2
  exit 1
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "请通过环境变量 PGPASSWORD 传入密码，而不是命令行参数。" >&2
  exit 1
fi

if [[ ! -f "$SQL_FILE" ]]; then
  echo "SQL 文件不存在: $SQL_FILE" >&2
  exit 1
fi

RAW_SQL="$(cat "$SQL_FILE")"
TMP_SQL="$(mktemp)"
trap 'rm -f "$TMP_SQL"' EXIT

if [[ "$IS_DML" == "true" ]]; then
  cat > "$TMP_SQL" <<EOF
BEGIN;
SET LOCAL statement_timeout = '${TIMEOUT}';
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT)
${RAW_SQL}
;
ROLLBACK;
EOF
  echo "== DML 模式：将在事务内执行 EXPLAIN ANALYZE，结束后强制 ROLLBACK，不会提交任何数据变更 ==" >&2
else
  cat > "$TMP_SQL" <<EOF
SET statement_timeout = '${TIMEOUT}';
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT)
${RAW_SQL}
;
EOF
  echo "== 只读模式：直接 EXPLAIN ANALYZE ==" >&2
fi

psql "host=${HOST} port=${PORT} user=${USER} dbname=${DBNAME} sslmode=prefer" \
     -v ON_ERROR_STOP=1 \
     -f "$TMP_SQL"

STATUS=$?

if [[ "$IS_DML" == "true" ]]; then
  echo "== 已回滚，未对数据造成任何持久化变更 ==" >&2
fi

exit $STATUS
