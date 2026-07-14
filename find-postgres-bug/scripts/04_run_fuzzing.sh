#!/usr/bin/env bash
# 阶段4：多维度模糊测试（针对一次性测试实例，绝不针对生产库）
# 用法: ./04_run_fuzzing.sh <build-sanitizer/install 目录> [持续秒数，默认1800]
set -euo pipefail

INSTALL_DIR="${1:?用法: $0 <build-sanitizer/install目录> [持续秒数]}"
DURATION="${2:-1800}"

BIN="${INSTALL_DIR}/bin"
if [ ! -x "${BIN}/postgres" ]; then
  echo "错误: ${BIN}/postgres 不存在，请先跑阶段1的 sanitizer 构建" >&2
  exit 1
fi

WORKDIR="$(mktemp -d /tmp/pg-fuzz-XXXXXX)"
PGDATA="${WORKDIR}/data"
PORT="${PGPORT:-55432}"
ARTIFACT_DIR="${WORKDIR}/../find-bug-artifacts-fuzz"
mkdir -p "$ARTIFACT_DIR"

# 密码只通过 PGPASSWORD 传递，不落盘、不打印
export PGPASSWORD="${PGPASSWORD:-$(openssl rand -hex 12)}"

cleanup() {
  echo ">>> 清理一次性实例"
  "${BIN}/pg_ctl" -D "$PGDATA" -m immediate stop >/dev/null 2>&1 || true
  # 保留 data 目录以便崩溃现场分析；如需彻底清理由用户自行删除 $WORKDIR
}
trap cleanup EXIT

echo ">>> 初始化一次性测试实例: $PGDATA"
"${BIN}/initdb" -D "$PGDATA" -U postgres --pwfile=<(echo "$PGPASSWORD") >/dev/null

cat >> "${PGDATA}/postgresql.conf" <<EOF
port = ${PORT}
listen_addresses = 'localhost'
log_min_messages = notice
log_error_verbosity = verbose
EOF

echo ">>> 启动实例（日志输出到 ${ARTIFACT_DIR}/postgres.log）"
"${BIN}/pg_ctl" -D "$PGDATA" -l "${ARTIFACT_DIR}/postgres.log" -w start

"${BIN}/createdb" -h localhost -p "$PORT" -U postgres fuzzdb

echo ">>> 检查 SQLsmith 是否可用"
if command -v sqlsmith >/dev/null 2>&1; then
  echo ">>> 启动 SQLsmith，持续 ${DURATION} 秒"
  timeout "${DURATION}" sqlsmith --verbose \
    --target="host=localhost port=${PORT} dbname=fuzzdb user=postgres" \
    >> "${ARTIFACT_DIR}/sqlsmith.log" 2>&1 || true
else
  echo "未检测到 sqlsmith，跳过 SQL 层模糊测试。安装方式："
  echo "  git clone https://github.com/anse1/sqlsmith.git && cd sqlsmith && ./autogen.sh && ./configure && make"
fi

echo ">>> 检查后端日志/sanitizer 报告中是否出现 PANIC/FATAL/sanitizer error"
if grep -Ei "PANIC|FATAL|AddressSanitizer|UndefinedBehaviorSanitizer|runtime error" \
    "${ARTIFACT_DIR}/postgres.log" > "${ARTIFACT_DIR}/suspicious_lines.log" 2>/dev/null; then
  echo "!!! 发现可疑日志行，已提取到 ${ARTIFACT_DIR}/suspicious_lines.log"
  echo "!!! 请立即保存现场：复制 $PGDATA 和 ${ARTIFACT_DIR} 到独立目录，并记录触发时间点附近的 SQL"
else
  echo "本轮未发现明显崩溃/sanitizer 报错（不代表没有 bug，只是这次没触发到）"
fi

echo ""
echo "=== 完成 ==="
echo "实例数据目录: $PGDATA (未自动删除，需要人工清理)"
echo "日志与产物: $ARTIFACT_DIR"
