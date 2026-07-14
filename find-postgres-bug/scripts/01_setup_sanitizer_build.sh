#!/usr/bin/env bash
# 阶段1：构建带 ASan/UBSan + cassert 的调试版 PostgreSQL
# 用法: ./01_setup_sanitizer_build.sh <postgres-source-dir> [jobs]
set -euo pipefail

SRC_DIR="${1:?用法: $0 <postgres-source-dir> [jobs]}"
JOBS="${2:-$(nproc)}"
ARTIFACT_DIR="${SRC_DIR}/find-bug-artifacts"
BUILD_DIR="${SRC_DIR}/build-sanitizer"

mkdir -p "$ARTIFACT_DIR"

if [ ! -f "${SRC_DIR}/configure" ]; then
  echo "错误: ${SRC_DIR} 下没有找到 configure 脚本，请确认这是 PostgreSQL 源码根目录（或先执行 ./configure --help 生成的前置 autoconf 步骤）" >&2
  exit 1
fi

echo ">>> 使用 clang（若可用）以获得更好的 sanitizer 支持"
if command -v clang >/dev/null 2>&1 && command -v clang++ >/dev/null 2>&1; then
  export CC=clang
  export CXX=clang++
else
  echo "警告: 未检测到 clang，退回 gcc；部分 sanitizer 诊断信息可能较弱" >&2
fi

mkdir -p "$BUILD_DIR"
cd "$SRC_DIR"

echo ">>> 配置构建（--enable-cassert --enable-debug + ASan/UBSan）"
./configure \
  --prefix="${BUILD_DIR}/install" \
  --enable-cassert \
  --enable-debug \
  CFLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer -O1 -g" \
  LDFLAGS="-fsanitize=address,undefined" \
  2>&1 | tee "${ARTIFACT_DIR}/configure.log"

echo ">>> 编译 (make -j${JOBS})"
make -j"${JOBS}" 2>&1 | tee "${ARTIFACT_DIR}/build.log"

echo ">>> 安装到隔离目录 ${BUILD_DIR}/install"
make install 2>&1 | tee -a "${ARTIFACT_DIR}/build.log"

echo ">>> 跑基础回归测试 (make check) —— 先确认环境本身没问题"
set +e
make check 2>&1 | tee "${ARTIFACT_DIR}/make_check.log"
CHECK_RC=$?
set -e

if [ $CHECK_RC -ne 0 ]; then
  echo ""
  echo "!!! make check 未完全通过，请先人工确认失败项是不是已知的 sanitizer 误报/环境问题，"
  echo "    再继续后续阶段，否则后面发现的“候选 bug”可能只是环境噪音。"
  echo "    失败详情见 ${ARTIFACT_DIR}/make_check.log 以及 src/test/regress/regression.diffs"
fi

echo ""
echo "=== 完成 ==="
echo "安装目录: ${BUILD_DIR}/install"
echo "日志目录: ${ARTIFACT_DIR}"
echo "下一步: initdb -D <数据目录> --pgdata=... 使用 ${BUILD_DIR}/install/bin 下的二进制启动一次性测试实例"
