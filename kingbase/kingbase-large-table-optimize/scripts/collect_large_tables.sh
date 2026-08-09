#!/usr/bin/env bash
# kingbase_large_table_optimize psql 采集脚本（KingbaseES / 金仓，只读）
# ---------------------------------------------------------------------
# 全程只执行 SELECT，不执行任何 DDL/DML/VACUUM/ANALYZE。
# 连接参数优先级（从高到低）：
#   1. 命令行参数 --host/--port/--user/--password/--dbname
#   2. 环境变量 PGHOST/PGPORT/PGDBNAME(兼容 PGDATABASE)/PGUSER/PGPASSWORD
#   3. 内置默认值 127.0.0.1:5432 / kingbase / kingbase / 123456
# 依赖：psql（KingbaseES 兼容 PG 网络协议，标准 psql 或金仓 ksql 均可）
#
# 注意：本脚本只采集【单个数据库】（默认 kingbase，或 --dbname 指定）。
#   需要遍历全部非模板库时，对每个库分别执行一次，或改用 collect_large_tables.py。
# 已知边界：若 schema/表名含点号或单引号，候选解析（按第一个点切分）可能不准确，
#   生产环境建议对含特殊字符的标识符手工验证。
#
# 用法：
#   bash collect_large_tables.sh [--host H] [--port P] [--user U] [--password PW] \
#       [--dbname DB] [--top-n 20] [--min-size-gb 10] [--output-dir DIR]
set -uo pipefail

# ---------- 连接参数解析 ----------
HOST="${PGHOST:-127.0.0.1}"
PORT="${PGPORT:-5432}"
DBNAME="${PGDBNAME:-${PGDATABASE:-kingbase}}"
USER="${PGUSER:-kingbase}"
PASSWORD="${PGPASSWORD:-123456}"
TOP_N=20
MIN_SIZE_GB=10
OUTDIR=""

usage() {
    echo "usage: $0 [--host H] [--port P] [--user U] [--password PW] [--dbname DB] [--top-n N] [--min-size-gb GB] [--output-dir DIR]" >&2
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --host) HOST="${2:?}"; shift 2 ;;
        --port) PORT="${2:?}"; shift 2 ;;
        --user) USER="${2:?}"; shift 2 ;;
        --password) PASSWORD="${2:?}"; shift 2 ;;
        --dbname) DBNAME="${2:?}"; shift 2 ;;
        --top-n) TOP_N="${2:?}"; shift 2 ;;
        --min-size-gb) MIN_SIZE_GB="${2:?}"; shift 2 ;;
        --output-dir) OUTDIR="${2:?}"; shift 2 ;;
        *) usage ;;
    esac
done

[ -z "$OUTDIR" ] && OUTDIR="/tmp/kingbase_lto_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTDIR"

# 通过环境变量传递密码，避免出现在命令行参数中
export PGHOST="$HOST" PGPORT="$PORT" PGUSER="$USER" PGPASSWORD="$PASSWORD" PGDATABASE="$DBNAME"

PSQL="psql -X -h $HOST -p $PORT -U $USER -d $DBNAME -tA -F '|'"

# ---------- 阶段 0：连接与预检 ----------
echo "== 连接测试 =="
eval "$PSQL -c 'SELECT version();'" > "$OUTDIR/00_version.txt" 2>&1 \
    || { echo "连接失败，请检查连接参数/网络"; cat "$OUTDIR/00_version.txt"; exit 1; }
cat "$OUTDIR/00_version.txt"

eval "$PSQL -c \"SELECT current_setting('server_version_num');\"" > "$OUTDIR/00_server_version_num.txt" 2>&1

echo "== 扩展检测（kbstattuple / pageinspect）=="
eval "$PSQL -c \"SELECT extname, extversion FROM pg_extension WHERE extname IN ('kbstattuple','pageinspect') ORDER BY 1;\"" > "$OUTDIR/01_extensions.txt" 2>&1
cat "$OUTDIR/01_extensions.txt"

echo "== 数据库列表 =="
eval "$PSQL -c 'SELECT datname FROM pg_database WHERE datistemplate=false AND datallowconn=true ORDER BY 1;'" > "$OUTDIR/02_databases.txt" 2>&1
cat "$OUTDIR/02_databases.txt"

# ---------- 阶段 1：大表初筛 ----------
MIN_BYTES=$(awk -v g="$MIN_SIZE_GB" 'BEGIN{printf "%.0f", g*1024*1024*1024}')

eval "$PSQL -c \"SELECT n.nspname || '.' || c.relname,
  pg_total_relation_size(c.oid) AS total_bytes,
  pg_relation_size(c.oid) AS table_bytes,
  pg_indexes_size(c.oid) AS index_bytes,
  c.reltuples::bigint AS est_rows,
  CASE WHEN p.partrelid IS NOT NULL THEN 'partitioned' ELSE '' END
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_partitioned_table p ON p.partrelid = c.oid
WHERE c.relkind IN ('r','p')
  AND n.nspname <> ALL (ARRAY['pg_catalog','information_schema','pg_toast','sys','sys_catalog','sys_hm','sysmac','sysaudit','src_restrict','sys_anon'])
  AND (pg_total_relation_size(c.oid) > $MIN_BYTES
       OR c.oid IN (SELECT c2.oid FROM pg_class c2 JOIN pg_namespace n2 ON n2.oid=c2.relnamespace
                    WHERE c2.relkind IN ('r','p')
                      AND n2.nspname <> ALL (ARRAY['pg_catalog','information_schema','pg_toast','sys','sys_catalog','sys_hm','sysmac','sysaudit','src_restrict','sys_anon'])
                    ORDER BY pg_total_relation_size(c2.oid) DESC LIMIT $TOP_N))
ORDER BY total_bytes DESC;\"" > "$OUTDIR/03_candidates.txt" 2>&1

echo "== 候选大表（TOP $TOP_N / > ${MIN_SIZE_GB}GB）=="
cat "$OUTDIR/03_candidates.txt"

# ---------- 阶段 1/2：逐表采集 ----------
HAS_KBSTAT=$(grep -c '^kbstattuple' "$OUTDIR/01_extensions.txt" || true)

# 表头
echo "schema.table|n_live_tup|n_dead_tup|dead_tup_pct" > "$OUTDIR/04_bloat.csv"
echo "schema.table|n_tup_ins|n_tup_upd|n_tup_del|n_tup_hot_upd|last_autovacuum|last_autoanalyze" > "$OUTDIR/05_dml.csv"
echo "schema.table|seq_scan|seq_tup_read|idx_scan|idx_tup_fetch" > "$OUTDIR/06_scan.csv"
echo "schema.table|indexrelname|idx_scan|idx_tup_read|idx_tup_fetch|index_bytes|index_type|tree_level(exact)|tree_level(est)" > "$OUTDIR/07_indexes.csv"
[ "$HAS_KBSTAT" != "0" ] && echo "schema.table|table_len|tuple_count|dead_tuple_count|dead_tuple_percent|free_percent" > "$OUTDIR/08_kbstattuple.csv"

# 候选表循环（03_candidates.txt 第一列为 schema.table）
while IFS='|' read -r qualified rest; do
    [ -z "$qualified" ] && continue
    schema="${qualified%%.*}"
    table="${qualified#*.}"
    qtable="\"$schema\".\"$table\""

    # 1.2 膨胀（近似，pg_stat_user_tables）
    eval "$PSQL -c \"SELECT '$qualified', n_live_tup, n_dead_tup,
      CASE WHEN (n_live_tup+n_dead_tup)=0 THEN 0 ELSE round(100.0*n_dead_tup/(n_live_tup+n_dead_tup),2) END
      FROM pg_stat_user_tables WHERE schemaname='$schema' AND relname='$table';\"" >> "$OUTDIR/04_bloat.csv" 2>/dev/null

    # 2.1 DML 活跃度
    eval "$PSQL -c \"SELECT '$qualified', n_tup_ins, n_tup_upd, n_tup_del, n_tup_hot_upd,
      COALESCE(last_autovacuum::text,''), COALESCE(last_autoanalyze::text,'')
      FROM pg_stat_user_tables WHERE schemaname='$schema' AND relname='$table';\"" >> "$OUTDIR/05_dml.csv" 2>/dev/null

    # 2.2 读取模式
    eval "$PSQL -c \"SELECT '$qualified', seq_scan, seq_tup_read, idx_scan, idx_tup_fetch
      FROM pg_stat_user_tables WHERE schemaname='$schema' AND relname='$table';\"" >> "$OUTDIR/06_scan.csv" 2>/dev/null

    # 2.3 索引
    eval "$PSQL -c \"SELECT '$qualified', s.indexrelname, s.idx_scan, s.idx_tup_read, s.idx_tup_fetch,
      pg_relation_size(s.indexrelid), am.amname
      FROM pg_stat_user_indexes s JOIN pg_am am ON am.oid = (SELECT relam FROM pg_class WHERE oid=s.indexrelid)
      WHERE s.schemaname='$schema' AND s.relname='$table' ORDER BY pg_relation_size(s.indexrelid) DESC;\"" > "$OUTDIR/_idx_tmp.txt" 2>/dev/null

    # 索引深度：精确（kbstatindex）或估算
    while IFS='|' read -r q i idx_scan idx_tup_read idx_tup_fetch ibytes itype; do
        if [ "$HAS_KBSTAT" != "0" ] && [ "$itype" = "btree" ]; then
            lvl=$(eval "$PSQL -tA -c \"SELECT COALESCE(tree_level::text,'') FROM kbstatindex('$schema.$i');\"" 2>/dev/null | head -1)
        else
            lvl=""
        fi
        est=""
        if [ -n "${ibytes:-}" ] && [ "$ibytes" -gt 0 ] 2>/dev/null; then
            est=$(awk -v b="$ibytes" 'BEGIN{print int(log(b/8192)/log(200))+1}')
        fi
        echo "$q|$i|$idx_scan|$idx_tup_read|$idx_tup_fetch|$ibytes|$itype|$lvl|$est" >> "$OUTDIR/07_indexes.csv"
    done < "$OUTDIR/_idx_tmp.txt"
    rm -f "$OUTDIR/_idx_tmp.txt"

    # 1.2 精确膨胀（kbstattuple，仅已装扩展时）
    if [ "$HAS_KBSTAT" != "0" ]; then
        eval "$PSQL -c \"SELECT '$qualified', table_len, tuple_count, dead_tuple_count,
          round(dead_tuple_percent::numeric,2), round(free_percent::numeric,2)
          FROM kbstattuple('$qtable');\"" >> "$OUTDIR/08_kbstattuple.csv" 2>/dev/null
    fi
done < "$OUTDIR/03_candidates.txt"

# ---------- 汇总 ----------
echo ""
echo "== 采集完成，结果目录: $OUTDIR =="
ls -1 "$OUTDIR"
echo ""
echo "提示：膨胀/负载画像见 04_bloat.csv ~ 08_kbstattuple.csv，结合 SKILL 的 references/sql-queries.md 推导负载类型并生成报告。"
