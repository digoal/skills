#!/usr/bin/env bash
# 阶段2：把提交历史挖成"错误模式教科书"
# 用法: ./02_mine_historical_bugs.sh <postgres-source-dir> [--since=<日期或引用，如 2.years.ago>]
set -euo pipefail

SRC_DIR="${1:?用法: $0 <postgres-source-dir> [--since=2.years.ago]}"
shift || true

SINCE="2.years.ago"
for arg in "$@"; do
  case "$arg" in
    --since=*) SINCE="${arg#--since=}" ;;
  esac
done

ARTIFACT_DIR="${SRC_DIR}/find-bug-artifacts"
OUT="${ARTIFACT_DIR}/historical_patterns.md"
mkdir -p "$ARTIFACT_DIR"

cd "$SRC_DIR"

echo ">>> 拉取全部分支/标签（若为只读镜像可能失败，忽略即可）"
git fetch --all --tags 2>/dev/null || echo "警告: git fetch 失败，使用本地已有历史继续"

# 分类关键词：类别 -> grep 正则（大小写不敏感）
declare -A CATS=(
  ["内存管理"]="pfree|palloc|use-after-free|double.?free|memory leak|dangling"
  ["并发锁"]="deadlock|race condition|lock (order|held)|concurren|lwlock|spinlock"
  ["边界溢出"]="overflow|out.of.bound|buffer.*(small|overrun)|xid wraparound|off.by.one"
  ["逻辑错误"]="incorrect result|wrong (result|answer)|planner.*(bug|error)|semantics"
  ["资源泄漏"]="leak|not (closed|released|freed)|fd leak|resource"
  ["类型转换"]="cast|type coercion|implicit conversion|truncat"
)

echo "# 历史 Bug 修复模式挖掘报告" > "$OUT"
echo "" >> "$OUT"
echo "生成时间: $(date '+%Y-%m-%d %H:%M:%S')" >> "$OUT"
echo "扫描范围: --since=${SINCE}，全部分支" >> "$OUT"
echo "" >> "$OUT"
echo "> 说明：本报告只是候选列表，很多提交标题含 fix/bug 但与内存/并发/边界类问题无关（比如" >> "$OUT"
echo "> 修文档、修 typo），请在阶段3使用前人工过滤，只保留真正有泛化价值的模式。" >> "$OUT"
echo "" >> "$OUT"

for cat in "${!CATS[@]}"; do
  pattern="${CATS[$cat]}"
  echo "## 类别: ${cat}" >> "$OUT"
  echo "" >> "$OUT"
  echo '```' >> "$OUT"
  git log --all --since="$SINCE" --oneline -i --extended-regexp --grep="$pattern" \
    -- src/ 2>/dev/null | head -50 >> "$OUT" || true
  echo '```' >> "$OUT"
  echo "" >> "$OUT"
done

echo "## 使用建议" >> "$OUT"
cat >> "$OUT" <<'EOF'

1. 对每个类别下你感兴趣的 commit，用以下命令看完整 diff 再判断是否有泛化价值：
   git show <commit-hash> -- src/

2. 挑出 3-5 个"这是一种可能在其他地方重复出现的不安全模式"的提交，记下：
   - 修复前的错误写法长什么样（代码片段）
   - 修复后正确写法长什么样
   - 这种模式在其他函数里可能怎么出现（比如同一子系统的姊妹函数）

3. 把挑出的模式喂给阶段3的 pattern_scan.py（可以直接告诉 Claude 这几个模式的描述，
   由 Claude 生成对应的 semgrep 规则或直接人工 grep 全库）。
EOF

echo "输出已写入: $OUT"
