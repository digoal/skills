#!/usr/bin/env bash
#
# safe_explain.sh —— 安全获取 KingbaseES（金仓）执行计划（psql 通道）
#
# 用途：
#   对只读 SELECT 直接 EXPLAIN (ANALYZE, BUFFERS, VERBOSE)。
#   对 DML（INSERT/UPDATE/DELETE/MERGE）强制包裹在事务中，设置语句超时后
#   执行 EXPLAIN ANALYZE，最后无条件 ROLLBACK，绝不 COMMIT。
#
# 用法：
#   export PGPASSWORD='xxx'
#   ./safe_explain.sh \
#       -h <host> -p <port> -U <user> -d <dbname> \
#       -f <sql_file>                       # SQL 写在文件里，避免特殊字符/换行问题
#       [-t <statement_timeout>]            # 默认 30s，DML 场景建议更保守，如 10s
#       [--dml]                             # 显式声明这是 DML，走事务+回滚路径；不加则按首关键字自动识别
#       [--no-analyze]                      # 仅拿估算计划（EXPLAIN 不带 ANALYZE），不真实执行
#       [--params '{"$1": 100, "$2": "2026-01-01"}']   # JSON 内联替换绑定变量
#
# 连接参数解析优先级: 命令行 > 环境变量(PGHOST/PGPORT/PGUSER/PGDBNAME/PGDATABASE/PGPASSWORD 及 KINGBASE* 变体) > 缺省值
#   缺省值: PGHOST=127.0.0.1 PGPORT=5432 PGDBNAME=kingbase PGUSER=kingbase PGPASSWORD=123456
#
# 金仓差异（已在 V9R1C10 实测）:
#   - EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT) 语法与 PG 12 一致，实测可用；
#     BUFFERS 必须配 ANALYZE。
#   - PG 的 psql 可直接连接金仓 V9；如 PATH 中没有 psql 会尝试 ksql。
#
# 安全说明：
#   - 密码只能通过 PGPASSWORD 环境变量传入，脚本不接受密码作为命令行参数，
#     避免密码出现在 `ps` 输出或 shell history 中。
#   - DML 路径下，无论 EXPLAIN ANALYZE 成功、失败还是超时，都会执行 ROLLBACK
#     （连接异常中断时由服务端隐式回滚兜底），该脚本不提供、也不应被改造出任何 COMMIT 路径。
#   - DML 识别会先剥离开头注释（-- 行注释 / /* */ 块注释），避免带注释的 DML 被误判为只读
#     而在事务外执行（psql 自动提交会真实落库，这是红线风险）。

set -euo pipefail

HOST=""; PORT=""; USER=""; DBNAME=""; SQL_FILE=""; TIMEOUT="30s"; IS_DML="false"; NO_ANALYZE="false"; PARAMS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h) HOST="$2"; shift 2 ;;
    -p) PORT="$2"; shift 2 ;;
    -U) USER="$2"; shift 2 ;;
    -d) DBNAME="$2"; shift 2 ;;
    -f) SQL_FILE="$2"; shift 2 ;;
    -t) TIMEOUT="$2"; shift 2 ;;
    --dml) IS_DML="true"; shift 1 ;;
    --no-analyze) NO_ANALYZE="true"; shift 1 ;;
    --params) PARAMS="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

# 优先级: 命令行 > 环境变量(PG*/KINGBASE*) > 缺省值
HOST="${HOST:-${PGHOST:-${KINGBASEHOST:-${KINGBASE_HOST:-127.0.0.1}}}}"
PORT="${PORT:-${PGPORT:-${KINGBASEPORT:-${KINGBASE_PORT:-5432}}}}"
USER="${USER:-${PGUSER:-${KINGBASEUSER:-${KINGBASE_USER:-kingbase}}}}"
DBNAME="${DBNAME:-${PGDBNAME:-${PGDATABASE:-${KINGBASEDBNAME:-${KINGBASE_DBNAME:-${KINGBASE_DATABASE:-kingbase}}}}}}"

if [[ -z "${PGPASSWORD:-}" ]]; then
  PGPASSWORD="${KINGBASEPASSWORD:-${KINGBASE_PASSWORD:-123456}}"
  export PGPASSWORD
  if [[ "$PGPASSWORD" == "123456" && -z "${KINGBASEPASSWORD:-}" && -z "${KINGBASE_PASSWORD:-}" ]]; then
    echo "[提示] 未检测到 PGPASSWORD/KINGBASE* 密码环境变量，使用缺省密码 123456（开发/测试环境默认值）。" >&2
  fi
fi

if [[ -z "$SQL_FILE" ]]; then
  echo "缺少必要参数: -f <sql_file>（可选 -h -p -U -d -t --dml --no-analyze --params）" >&2
  exit 1
fi

if [[ ! -f "$SQL_FILE" ]]; then
  echo "SQL 文件不存在: $SQL_FILE" >&2
  exit 1
fi

# 客户端二选一：psql（PG 客户端实测可连金仓）或 ksql（金仓自带）
if command -v psql >/dev/null 2>&1; then
  CLIENT="psql"
elif command -v ksql >/dev/null 2>&1; then
  CLIENT="ksql"
else
  echo "未找到 psql 或 ksql 客户端，请安装 PostgreSQL 客户端或使用 safe_explain.py（python 通道）。" >&2
  exit 1
fi

RAW_SQL="$(cat "$SQL_FILE")"

# 剥离开头注释后取首个关键字（支持 -- 行注释、/* */ 块注释、前置括号），用于 DML 识别
first_keyword() {
  awk '
    { buf = buf $0 "\n" }
    END {
      s = buf
      while (1) {
        gsub(/^[ \t\r\n]+/, "", s)
        if (s == "") break
        if (s ~ /^--/) { sub(/^--[^\n]*\n?/, "", s); continue }
        if (s ~ /^\/\*/) {
          if (s ~ /\/\*.*\*\//) { sub(/^\/\*.*\*\//, "", s); continue }
          s = ""; break
        }
        break
      }
      gsub(/^[ \t\r\n()]+/, "", s)
      if (s == "") { print ""; exit }
      split(s, a, /[ \t\n\r]/)
      w = a[1]
      gsub(/[,;]/, "", w)
      print toupper(w)
    }' <<< "$1"
}

FIRST_WORD="$(first_keyword "$RAW_SQL")"

# 自动识别 DML（首关键字），--dml 显式声明兜底；识别失败（空/异常）且未显式声明时按只读处理但给出提示
case "$FIRST_WORD" in
  INSERT|UPDATE|DELETE|MERGE) IS_DML="true" ;;
  "") echo "[警告] 未能识别 SQL 首关键字，将按只读路径处理；若这是 DML 请显式加 --dml。" >&2 ;;
esac

# 绑定变量内联替换: --params '{"$1": 100, "$2": "2026-01-01"}'
if [[ -n "$PARAMS" ]]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "错误: --params 需要 python3（用于 JSON 参数解析与安全替换）。" >&2
    exit 1
  fi
  # 利用 python3 做 JSON 解析与类型感知的 SQL 字面量替换（数值/布尔/null 不加引号）
  RAW_SQL="$(RAW_SQL="$RAW_SQL" PARAMS="$PARAMS" python3 - <<'PYEOF'
import json, os, re
sql = os.environ["RAW_SQL"]
params = json.loads(os.environ["PARAMS"])
def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"
for k, v in params.items():
    if not re.fullmatch(r"\$\d+", k):
        raise SystemExit(f"参数键必须是 $1/$2 形式: {k}")
    sql = re.sub(re.escape(k) + r"(?![0-9])", lambda m: lit(v), sql)
print(sql)
PYEOF
)"
  echo "== 已按 --params 内联替换绑定变量 ==" >&2
fi

TMP_SQL="$(mktemp)"
trap 'rm -f "$TMP_SQL"' EXIT

if [[ "$NO_ANALYZE" == "true" ]]; then
  EXPLAIN_CMD="EXPLAIN (VERBOSE, FORMAT TEXT)"
else
  EXPLAIN_CMD="EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT)"
fi

if [[ "$IS_DML" == "true" ]]; then
  cat > "$TMP_SQL" <<EOF
BEGIN;
SET LOCAL statement_timeout = '${TIMEOUT}';
SET LOCAL lock_timeout = '5s';
${EXPLAIN_CMD}
${RAW_SQL}
;
ROLLBACK;
EOF
  echo "== DML 模式：将在事务内执行 EXPLAIN ANALYZE，结束后强制 ROLLBACK，不会提交任何数据变更 ==" >&2
else
  cat > "$TMP_SQL" <<EOF
SET statement_timeout = '${TIMEOUT}';
SET lock_timeout = '5s';
${EXPLAIN_CMD}
${RAW_SQL}
;
EOF
  echo "== 只读模式：直接 EXPLAIN (ANALYZE 视 --no-analyze 而定) ==" >&2
fi

# set +e 包裹客户端调用：确保能捕获退出码并输出回滚确认（即使 EXPLAIN 报错）
set +e
$CLIENT "host=${HOST} port=${PORT} user=${USER} dbname=${DBNAME} sslmode=prefer" \
     -v ON_ERROR_STOP=1 \
     -f "$TMP_SQL"
STATUS=$?
set -e

if [[ "$IS_DML" == "true" ]]; then
  if [[ $STATUS -ne 0 ]]; then
    echo "== 注意：EXPLAIN 执行失败，事务已随连接关闭隐式回滚，未提交任何数据变更 ==" >&2
  else
    echo "== 已回滚，未对数据造成任何持久化变更 ==" >&2
  fi
fi

exit $STATUS
