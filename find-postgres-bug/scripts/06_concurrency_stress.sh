#!/usr/bin/env bash
# 阶段6：并发与压力测试 + amcheck 索引完整性校验
# 用法: ./06_concurrency_stress.sh <bin目录> <PGDATA> [持续秒数，默认600] [并发客户端数，默认8]
set -euo pipefail

BIN="${1:?用法: $0 <bin目录> <PGDATA> [持续秒数] [并发数]}"
PGDATA="${2:?需要 PGDATA 路径}"
DURATION="${3:-600}"
CONCURRENCY="${4:-8}"
PORT="${PGPORT:-55432}"
DB="${PGDATABASE:-fuzzdb}"

ARTIFACT_DIR="$(dirname "$PGDATA")/find-bug-artifacts-stress"
mkdir -p "$ARTIFACT_DIR"

# 密码统一走 PGPASSWORD，不落盘
: "${PGPASSWORD:?请先 export PGPASSWORD=<一次性测试实例密码>，不要硬编码}"

echo ">>> 确保 amcheck 扩展已安装"
"${BIN}/psql" -h localhost -p "$PORT" -U postgres -d "$DB" \
  -c "CREATE EXTENSION IF NOT EXISTS amcheck;"

echo ">>> 建立测试表与索引（如已存在则跳过）"
"${BIN}/psql" -h localhost -p "$PORT" -U postgres -d "$DB" <<'SQL'
CREATE TABLE IF NOT EXISTS stress_test (id bigserial PRIMARY KEY, val text, ts timestamptz default now());
CREATE INDEX IF NOT EXISTS idx_stress_val ON stress_test (val);
SQL

echo ">>> 启动并发 DDL/DML 压力循环，持续 ${DURATION} 秒，${CONCURRENCY} 个并发会话"

run_dml_worker() {
  local end=$((SECONDS + DURATION))
  while [ $SECONDS -lt $end ]; do
    "${BIN}/psql" -h localhost -p "$PORT" -U postgres -d "$DB" -q -c \
      "INSERT INTO stress_test (val) VALUES (md5(random()::text));" >/dev/null 2>&1 || true
    "${BIN}/psql" -h localhost -p "$PORT" -U postgres -d "$DB" -q -c \
      "DELETE FROM stress_test WHERE id IN (SELECT id FROM stress_test ORDER BY random() LIMIT 5);" >/dev/null 2>&1 || true
  done
}

run_ddl_worker() {
  local end=$((SECONDS + DURATION))
  while [ $SECONDS -lt $end ]; do
    "${BIN}/psql" -h localhost -p "$PORT" -U postgres -d "$DB" -q -c \
      "REINDEX INDEX CONCURRENTLY idx_stress_val;" >> "${ARTIFACT_DIR}/ddl.log" 2>&1 || true
    sleep 2
  done
}

run_kill_worker() {
  local end=$((SECONDS + DURATION))
  while [ $SECONDS -lt $end ]; do
    sleep 5
    "${BIN}/psql" -h localhost -p "$PORT" -U postgres -d "$DB" -q -c \
      "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
       WHERE datname = '${DB}' AND pid <> pg_backend_pid() AND state <> 'idle'
       ORDER BY random() LIMIT 1;" >> "${ARTIFACT_DIR}/kill.log" 2>&1 || true
  done
}

pids=()
for i in $(seq 1 "$CONCURRENCY"); do
  run_dml_worker &
  pids+=($!)
done
run_ddl_worker &
pids+=($!)
run_kill_worker &
pids+=($!)

wait "${pids[@]}" || true

echo ">>> 压力测试结束，运行 amcheck 校验索引完整性"
"${BIN}/psql" -h localhost -p "$PORT" -U postgres -d "$DB" \
  -c "SELECT bt_index_check(index => 'idx_stress_val'::regclass, heapallindexed => true);" \
  2>&1 | tee "${ARTIFACT_DIR}/amcheck_result.log"

if grep -qi "error\|corrupt" "${ARTIFACT_DIR}/amcheck_result.log"; then
  echo "!!! amcheck 报告了异常，立即保存现场（$PGDATA 全量拷贝）并停止进一步写入该实例"
else
  echo "本轮 amcheck 未发现索引损坏（不代表没有潜在问题，建议多轮重复）"
fi

echo ""
echo "=== 完成 ==="
echo "产物目录: $ARTIFACT_DIR"
