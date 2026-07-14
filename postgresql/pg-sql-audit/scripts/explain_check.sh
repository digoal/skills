#!/usr/bin/env bash
# explain_check.sh
# 对给定 SQL 文件中的每条可 EXPLAIN 的语句（SELECT/INSERT/UPDATE/DELETE/MERGE）
# 只读方式获取执行计划，绝不加 ANALYZE，绝不真正执行会修改数据的语句。
#
# 用法: PGPASSWORD=xxx ./explain_check.sh -h HOST -p PORT -U USER -d DBNAME -f sql_file.sql
#
# 注意：
#   - 本脚本仅对每条语句包裹 EXPLAIN (COSTS, VERBOSE, BUFFERS, FORMAT TEXT) 后在只读事务内执行
#   - 只读事务中执行 EXPLAIN 不会真正提交任何数据变更（PostgreSQL 只是生成计划，不落盘），
#     但为保险起见仍强制 READ ONLY + 事务回滚，双重保护
#   - DDL/DCL/函数体/触发器定义不支持 EXPLAIN，会被跳过，交由人工审查环节处理

set -euo pipefail

HOST=""; PORT="5432"; USER=""; DBNAME=""; SQLFILE=""

while getopts "h:p:U:d:f:" opt; do
  case $opt in
    h) HOST="$OPTARG" ;;
    p) PORT="$OPTARG" ;;
    U) USER="$OPTARG" ;;
    d) DBNAME="$OPTARG" ;;
    f) SQLFILE="$OPTARG" ;;
    *) echo "未知参数"; exit 1 ;;
  esac
done

if [[ -z "$HOST" || -z "$USER" || -z "$DBNAME" || -z "$SQLFILE" ]]; then
  echo "缺少必需参数: -h HOST -U USER -d DBNAME -f sql_file.sql (可选 -p PORT)" >&2
  exit 1
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "错误: 请通过环境变量 PGPASSWORD 提供密码，禁止明文传参。" >&2
  exit 1
fi

if [[ ! -f "$SQLFILE" ]]; then
  echo "错误: 找不到 SQL 文件 $SQLFILE" >&2
  exit 1
fi

TMP_SQL=$(mktemp)
trap 'rm -f "$TMP_SQL"' EXIT

idx=0
while IFS= read -r stmt; do
  [[ -z "$(echo "$stmt" | tr -d '[:space:]')" ]] && continue
  first_word=$(echo "$stmt" | tr -s '[:space:]' ' ' | awk '{print toupper($1)}')
  idx=$((idx+1))

  case "$first_word" in
    SELECT|INSERT|UPDATE|DELETE|MERGE|WITH)
      {
        echo "BEGIN;"
        echo "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;"
        echo "SET LOCAL statement_timeout = '30s';"
        echo "EXPLAIN (COSTS, VERBOSE, BUFFERS, FORMAT TEXT) ${stmt};"
        echo "ROLLBACK;"
      } > "$TMP_SQL"
      echo "===== 语句 #${idx} 执行计划 (${first_word}) ====="
      echo "--- 原始SQL ---"
      echo "$stmt"
      echo "--- 执行计划 ---"
      psql -X -h "$HOST" -p "$PORT" -U "$USER" -d "$DBNAME" -v ON_ERROR_STOP=0 -f "$TMP_SQL" || \
        echo "[提示] 该语句无法获取执行计划(可能含未绑定参数/依赖上下文)，请人工复核。"
      echo
      ;;
    ALTER|CREATE|DROP|GRANT|REVOKE|COMMENT|TRUNCATE)
      echo "===== 语句 #${idx} (${first_word}) — DDL/DCL，跳过 EXPLAIN，转人工审查环节 ====="
      echo "$stmt"
      echo
      ;;
    *)
      echo "===== 语句 #${idx} (${first_word}) — 未识别类型，转人工审查环节 ====="
      echo "$stmt"
      echo
      ;;
  esac
done < <(grep -v '^--' "$SQLFILE" | awk 'BEGIN{RS=";"} NF{gsub(/\n+$/,""); print $0";"}')

echo "############ EXPLAIN 检查完成，共处理 ${idx} 条语句 ############"
