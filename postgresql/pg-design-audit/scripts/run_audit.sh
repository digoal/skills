#!/usr/bin/env bash
# run_audit.sh :: pg-design-audit 编排脚本
#
# 用法:
#   PGPASSWORD='xxx' ./run_audit.sh -h <host> -p <port> -U <user> [-d <db1,db2,...>] [-o <outdir>]
#
# 说明:
#   - 仅执行只读查询（information_schema / pg_catalog / pg_stat_*），不执行任何 DDL/DML。
#   - 密码通过环境变量 PGPASSWORD 传入，不在命令行/脚本中硬编码或回显。
#   - 若不指定 -d，将自动扫描实例内所有非模板、允许连接的数据库。
#   - 每个数据库的每个检查项输出为独立文本文件，便于逐项审阅与后续汇总生成报告。
#
# 依赖: psql 客户端（无需数据库超级用户权限，但部分检查需相应系统视图的 SELECT 权限）

set -euo pipefail

HOST=""
PORT="5432"
USER=""
DBS=""
OUTDIR="./pg_audit_output"

while getopts "h:p:U:d:o:" opt; do
  case $opt in
    h) HOST="$OPTARG" ;;
    p) PORT="$OPTARG" ;;
    U) USER="$OPTARG" ;;
    d) DBS="$OPTARG" ;;
    o) OUTDIR="$OPTARG" ;;
    *) echo "未知参数: -$opt" >&2; exit 1 ;;
  esac
done

if [[ -z "$HOST" || -z "$USER" ]]; then
  echo "用法: PGPASSWORD='xxx' $0 -h <host> -p <port> -U <user> [-d <db1,db2>] [-o <outdir>]" >&2
  exit 1
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "警告: 未设置 PGPASSWORD 环境变量，将依赖 .pgpass 或触发交互式密码输入" >&2
fi

QUERY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/queries" && pwd)"
mkdir -p "$OUTDIR"

CONN_BASE=(psql -h "$HOST" -p "$PORT" -U "$USER" -X -q -v ON_ERROR_STOP=0 -A -F '|' -t)

# 1) 确定待扫描的数据库列表
if [[ -z "$DBS" ]]; then
  echo "未指定 -d，正在自动发现实例内所有非模板数据库..." >&2
  DB_LIST=$("${CONN_BASE[@]}" -d postgres -f "$QUERY_DIR/00_list_databases.sql")
else
  DB_LIST=$(echo "$DBS" | tr ',' '\n')
fi

echo "待扫描数据库列表:" >&2
echo "$DB_LIST" >&2

# 2) 对每个数据库逐一执行 7 大类检查项
for db in $DB_LIST; do
  db_trimmed=$(echo "$db" | xargs)
  [[ -z "$db_trimmed" ]] && continue
  db_outdir="$OUTDIR/$db_trimmed"
  mkdir -p "$db_outdir"
  echo "== 正在扫描数据库: $db_trimmed ==" >&2
  for qfile in "$QUERY_DIR"/0[1-7]_*.sql; do
    qname=$(basename "$qfile" .sql)
    outfile="$db_outdir/${qname}.txt"
    if "${CONN_BASE[@]}" -d "$db_trimmed" -f "$qfile" > "$outfile" 2> "$db_outdir/${qname}.err"; then
      if [[ -s "$db_outdir/${qname}.err" ]]; then
        echo "  [$qname] 执行完成但有告警/权限不足，详见 ${qname}.err" >&2
      fi
    else
      echo "  [$qname] 执行失败（可能权限不足），详见 ${qname}.err" >&2
    fi
  done
done

echo "全部扫描完成，原始结果已保存至: $OUTDIR" >&2
echo "下一步：由 Agent 读取 $OUTDIR 下各文件，按 SKILL.md 中的评分与报告规则生成最终 Markdown 报告。" >&2
