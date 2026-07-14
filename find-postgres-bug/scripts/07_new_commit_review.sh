#!/usr/bin/env bash
# 阶段7：新提交的即时审查
# 用法: ./07_new_commit_review.sh <postgres-source-dir> [天数，默认7]
set -euo pipefail

SRC_DIR="${1:?用法: $0 <postgres-source-dir> [天数]}"
DAYS="${2:-7}"
ARTIFACT_DIR="${SRC_DIR}/find-bug-artifacts"
OUT="${ARTIFACT_DIR}/recent_commit_review.md"
mkdir -p "$ARTIFACT_DIR"

cd "$SRC_DIR"

echo "# 近 ${DAYS} 天新提交审查" > "$OUT"
echo "" >> "$OUT"
echo "生成时间: $(date '+%Y-%m-%d %H:%M:%S')" >> "$OUT"
echo "" >> "$OUT"

COMMITS=$(git log --since="${DAYS} days ago" --pretty=format:"%H" -- src/)

if [ -z "$COMMITS" ]; then
  echo "近 ${DAYS} 天内没有找到新提交（src/ 目录）" >> "$OUT"
  echo "无新提交，报告写入 $OUT"
  exit 0
fi

for hash in $COMMITS; do
  subject=$(git show -s --format="%s" "$hash")
  author=$(git show -s --format="%an" "$hash")
  date=$(git show -s --format="%ad" --date=short "$hash")

  # 风险打分：命中风险关键词越多分越高，仅作粗略排序参考
  diff_content=$(git show "$hash" -- src/ 2>/dev/null || true)
  score=0
  reasons=()

  if echo "$diff_content" | grep -q "^-.*palloc\|^-.*MemoryContext"; then
    score=$((score+1)); reasons+=("移除/修改了内存分配相关代码")
  fi
  if echo "$diff_content" | grep -qE "^\+.*\b(LWLock|SpinLock|LockBuffer)\b"; then
    score=$((score+2)); reasons+=("新增/修改了锁相关代码")
  fi
  if echo "$diff_content" | grep -qE "^\+.*\bshm_toc|shared memory|SharedMem"; then
    score=$((score+2)); reasons+=("涉及共享内存结构改动，需确认对齐与信号安全")
  fi
  if echo "$diff_content" | grep -qE "^\+.*\b(memcpy|memmove|strcpy|sprintf)\b"; then
    score=$((score+1)); reasons+=("新增了原始内存/字符串操作，需确认边界检查")
  fi
  if [ -z "$(echo "$diff_content" | grep -E '^\+.*(test|regress)')" ] && [ "$score" -gt 0 ]; then
    score=$((score+1)); reasons+=("未见到对应的新增测试用例")
  fi

  if [ "$score" -gt 0 ]; then
    {
      echo "## ${hash:0:10} — ${subject}"
      echo ""
      echo "- 作者: ${author}  日期: ${date}"
      echo "- 风险分: ${score}"
      echo "- 原因: $(IFS='; '; echo "${reasons[*]}")"
      echo ""
    } >> "$OUT"
  fi
done

echo "审查完成，报告写入 $OUT"
echo "下一步：对风险分较高的提交，用 git show <hash> -- src/ 人工深入复核"
