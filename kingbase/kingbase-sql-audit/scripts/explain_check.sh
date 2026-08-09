#!/usr/bin/env bash
# explain_check.sh
# 对给定 SQL 文件中的每条可 EXPLAIN 的语句（SELECT/INSERT/UPDATE/DELETE/MERGE/WITH）
# 只读方式获取执行计划，绝不加 ANALYZE，绝不真正执行会修改数据的语句。
# 用法: PGPASSWORD=xxx ./explain_check.sh [-h HOST] [-p PORT] [-U USER] [-d DBNAME] -f sql_file.sql
#
# 连接参数解析优先级: 命令行 > 环境变量(PGHOST/PGPORT/PGUSER/PGDBNAME/PGDATABASE/PGPASSWORD 及 KINGBASE* 变体) > 缺省值
#
# 金仓差异（已在 V9R1C10 实测）:
#   - EXPLAIN (COSTS, VERBOSE, BUFFERS, FORMAT TEXT) 会报 "BUFFERS requires ANALYZE"，
#     因此一律使用 EXPLAIN (COSTS, VERBOSE, FORMAT TEXT)，不加 BUFFERS
#   - 只读事务使用 BEGIN; SET TRANSACTION READ ONLY; ...; ROLLBACK;
#     （SET SESSION CHARACTERISTICS 不影响当前事务）
#   - 本脚本不在事务内执行任何 DDL（CREATE INDEX CONCURRENTLY 等不能在事务块内执行）
#
# 注意:
#   - 函数/触发器定义体内部含分号时，按分号切分会切碎函数体，请先人工拆出函数/触发器定义再单独处理
#   - DDL/DCL 不支持 EXPLAIN，会被跳过，交由人工审查环节处理

set -euo pipefail

ARG_HOST=""; ARG_PORT=""; ARG_USER=""; ARG_DB=""; SQLFILE=""

while getopts "h:p:U:d:f:" opt; do
  case $opt in
    h) ARG_HOST="$OPTARG" ;;
    p) ARG_PORT="$OPTARG" ;;
    U) ARG_USER="$OPTARG" ;;
    d) ARG_DB="$OPTARG" ;;
    f) SQLFILE="$OPTARG" ;;
    *) echo "未知参数"; exit 1 ;;
  esac
done

# 优先级: 命令行 > 环境变量(PG*/KINGBASE*) > 缺省值
HOST="${ARG_HOST:-${PGHOST:-${KINGBASEHOST:-${KINGBASE_HOST:-127.0.0.1}}}}"
PORT="${ARG_PORT:-${PGPORT:-${KINGBASEPORT:-${KINGBASE_PORT:-5432}}}}"
USER="${ARG_USER:-${PGUSER:-${KINGBASEUSER:-${KINGBASE_USER:-kingbase}}}}"
DBNAME="${ARG_DB:-${PGDBNAME:-${PGDATABASE:-${KINGBASEDBNAME:-${KINGBASE_DBNAME:-${KINGBASE_DATABASE:-kingbase}}}}}}"

if [[ -z "$SQLFILE" ]]; then
  echo "缺少必需参数: -f sql_file.sql (可选 -h -p -U -d)" >&2
  exit 1
fi

# 密码优先级: PGPASSWORD > KINGBASEPASSWORD/KINGBASE_PASSWORD > 缺省值 123456（与 SKILL.md 连接约定一致）
if [[ -z "${PGPASSWORD:-}" ]]; then
  PGPASSWORD="${KINGBASEPASSWORD:-${KINGBASE_PASSWORD:-123456}}"
  export PGPASSWORD
  if [[ "$PGPASSWORD" == "123456" && -z "${KINGBASEPASSWORD:-}" && -z "${KINGBASE_PASSWORD:-}" ]]; then
    echo "[提示] 未检测到 PGPASSWORD/KINGBASE* 密码环境变量，使用缺省密码 123456（开发/测试环境默认值）。" >&2
  fi
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
      stmt_no_semi="${stmt%;}"  # 去掉 awk 追加的尾部分号，避免 EXPLAIN ...;;
      {
        echo "BEGIN;"
        echo "SET TRANSACTION READ ONLY;"
        echo "SET LOCAL statement_timeout = '30s';"
        echo "EXPLAIN (COSTS, VERBOSE, FORMAT TEXT) ${stmt_no_semi};"
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
done < <(grep -vE '^[[:space:]]*--' "$SQLFILE" | awk 'BEGIN{RS=";"} NF{gsub(/\n+$/,""); print $0";"}')

echo "############ EXPLAIN 检查完成，共处理 ${idx} 条语句 ############"
