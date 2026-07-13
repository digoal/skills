#!/usr/bin/env python3
"""
human_score.py — 统计层"人味"打分器

这个脚本只负责*可以被代码客观计算*的那部分人味信号：
  1. 句式节奏（句长是否有起伏，AI 喜欢句句中等长度、很匀）
  2. 段落节奏（段落长度是否有起伏）
  3. AI 高频套话 / 强信号短语密度（"综上所述""不可否认""值得注意的是"……）
  4. 软性商业/技术 buzzword 密度（"赋能""抓手""闭环"……，权重比强信号轻，
     因为这些词在金融/产品语境里有时是合理的行业术语）
  5. 形式化过渡词密度（"此外""与此同时""首先……其次……最后"……）
  6. 词汇多样性 / 重复度（character bigram distinct ratio）

这些指标合成一个 0-100 的 statistical_score，作为 Claude 做整体人味评分时的
*客观锚点*——主观维度（具体细节、情感真实感、口语化痕迹）仍需 Claude 结合
通读内容来判断，脚本不负责，也不应该负责，那部分判断。

用法：
    python human_score.py <文件路径>
    python human_score.py --text "直接传入的文本"
    cat file.md | python human_score.py -

输出：JSON，打到 stdout。
"""

import sys
import re
import json
import argparse
import statistics as stats

# ---------------------------------------------------------------------------
# 词表：强 AI 信号短语（命中一次扣分较重）
# ---------------------------------------------------------------------------
STRONG_AI_PHRASES = [
    "综上所述", "总的来说", "总而言之", "简而言之", "归根结底", "由此可见",
    "显而易见", "毋庸置疑", "不可否认", "值得注意的是", "值得一提的是",
    "需要指出的是", "我们可以看到", "我们不难发现", "从某种意义上说",
    "在很大程度上", "不难看出", "可以说", "可见一斑",
    "in conclusion", "in summary", "to summarize", "overall,",
    "it is worth noting that", "it's worth noting that",
    "it is important to note that", "it's important to note that",
    "needless to say", "without a doubt", "it goes without saying",
    "delve into", "navigate the complexities of", "in today's fast-paced world",
    "in the realm of", "left an indelible mark", "underscores the importance of",
    "plays a pivotal role", "stands as a testament", "as an ai language model",
]

# ---------------------------------------------------------------------------
# 词表：软性 buzzword / 行业套话（命中扣分较轻，避免误伤合理术语）
# ---------------------------------------------------------------------------
SOFT_BUZZWORDS = [
    "赋能", "抓手", "底层逻辑", "颗粒度", "闭环", "沉淀", "心智", "链路",
    "生态矩阵", "体系化", "系统化", "一站式", "全方位", "多维度", "深层次",
    "大力推动", "持续发力", "积极探索", "勇于创新", "砥砺前行", "蓄势待发",
    "起到了重要作用", "发挥着重要作用", "具有重要意义", "至关重要",
    "不可或缺", "锦上添花", "添砖加瓦", "深耕", "赋予", "联动",
    "leverage", "synergy", "robust", "holistic", "seamless", "cutting-edge",
    "game-changer", "paradigm shift", "unlock the potential", "unlock potential",
]

# ---------------------------------------------------------------------------
# 词表：形式化过渡词/结构标记（密度过高说明"教科书式"结构）
# ---------------------------------------------------------------------------
TRANSITION_WORDS = [
    "首先", "其次", "再次", "最后", "一方面", "另一方面", "与此同时", "此外",
    "另外", "除此之外", "不仅如此", "不仅", "而且", "因此", "所以", "然而",
    "但是", "不过", "换言之", "也就是说", "进一步来说", "更重要的是",
    "moreover", "furthermore", "additionally", "however", "nevertheless",
    "in addition", "on the other hand", "on one hand", "as a result",
    "consequently", "therefore", "thus", "firstly", "secondly", "lastly",
]

SENT_SPLIT_RE = re.compile(r"[。！？!?\n]+")
PARA_SPLIT_RE = re.compile(r"\n\s*\n+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z]+|[\u4e00-\u9fff]")


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def cv_score(lengths, target_cv=0.55):
    """句长/段落长变异系数 -> 0-100 分。变异系数越接近/高于 target，分越高。"""
    lengths = [l for l in lengths if l > 0]
    if len(lengths) < 3:
        return 50.0, 0.0  # 样本太少，给中性分
    mean = stats.mean(lengths)
    if mean == 0:
        return 50.0, 0.0
    sd = stats.pstdev(lengths)
    cv = sd / mean
    score = clamp(100 * min(1.0, cv / target_cv))
    return score, cv


def phrase_density(text, phrases, total_chars):
    text_low = text.lower()
    count = 0
    for p in phrases:
        count += text_low.count(p.lower())
    density_per_1000 = count / max(total_chars, 1) * 1000
    return count, density_per_1000


def lexical_diversity(text):
    """character-level bigram distinct ratio，作为重复度的粗略代理。"""
    chars = [c for c in re.sub(r"\s", "", text)]
    if len(chars) < 4:
        return 50.0
    bigrams = ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)]
    distinct_ratio = len(set(bigrams)) / len(bigrams)
    # 经验上人类自然文本 distinct_ratio 大约在 0.55-0.85 之间
    score = clamp(distinct_ratio / 0.75 * 100)
    return score


def analyze(text):
    text = text.strip()
    if not text:
        raise ValueError("输入内容为空")

    total_chars = len(re.sub(r"\s", "", text))
    is_cjk_dominant = len(CJK_RE.findall(text)) > len(text) * 0.3

    sentences = [s.strip() for s in SENT_SPLIT_RE.split(text) if s.strip()]
    sent_lengths = [len(s) for s in sentences]
    rhythm_score, sent_cv = cv_score(sent_lengths, target_cv=0.55)

    paragraphs = [p.strip() for p in PARA_SPLIT_RE.split(text) if p.strip()]
    para_lengths = [len(p) for p in paragraphs]
    para_score, para_cv = cv_score(para_lengths, target_cv=0.5)

    strong_count, strong_density = phrase_density(text, STRONG_AI_PHRASES, total_chars)
    soft_count, soft_density = phrase_density(text, SOFT_BUZZWORDS, total_chars)
    trans_count, trans_density = phrase_density(text, TRANSITION_WORDS, total_chars)

    # 密度 -> 扣分。每千字命中 1 次强信号扣 12 分，软 buzzword 扣 6 分，
    # 过渡词扣 4 分（过渡词本身是正常语言现象，只有密度很高才算问题）。
    strong_score = clamp(100 - strong_density * 12)
    soft_score = clamp(100 - soft_density * 6)
    trans_score = clamp(100 - trans_density * 4)

    diversity_score = lexical_diversity(text)

    # 句式/段落节奏综合 (70% 句子 + 30% 段落)
    combined_rhythm = rhythm_score * 0.7 + para_score * 0.3

    weights = {
        "rhythm": 0.30,
        "strong_ai_phrases": 0.30,
        "soft_buzzwords": 0.10,
        "transition_density": 0.10,
        "lexical_diversity": 0.20,
    }
    components = {
        "rhythm": combined_rhythm,
        "strong_ai_phrases": strong_score,
        "soft_buzzwords": soft_score,
        "transition_density": trans_score,
        "lexical_diversity": diversity_score,
    }
    statistical_score = sum(components[k] * weights[k] for k in weights)

    return {
        "input_stats": {
            "total_chars": total_chars,
            "is_cjk_dominant": is_cjk_dominant,
            "sentence_count": len(sentences),
            "paragraph_count": len(paragraphs),
        },
        "components": {
            "rhythm": {
                "score": round(combined_rhythm, 1),
                "sentence_cv": round(sent_cv, 3),
                "paragraph_cv": round(para_cv, 3),
                "note": "句长/段长变异系数越高说明节奏越有起伏，越接近人类写作；"
                        "AI 文本常见特征是句子长度异常均匀（CV 偏低）。",
            },
            "strong_ai_phrases": {
                "score": round(strong_score, 1),
                "hits": strong_count,
                "density_per_1000_chars": round(strong_density, 2),
                "note": "命中'综上所述''不可否认''值得注意的是'等强 AI 套话的频率。",
            },
            "soft_buzzwords": {
                "score": round(soft_score, 1),
                "hits": soft_count,
                "density_per_1000_chars": round(soft_density, 2),
                "note": "命中'赋能''抓手''闭环'等软性 buzzword 的频率（权重较低，"
                        "因为这些词在行业语境下有时合理）。",
            },
            "transition_density": {
                "score": round(trans_score, 1),
                "hits": trans_count,
                "density_per_1000_chars": round(trans_density, 2),
                "note": "形式化过渡词/结构标记的密度，过高说明结构过于'教科书式'。",
            },
            "lexical_diversity": {
                "score": round(diversity_score, 1),
                "note": "字符级 bigram 不重复率，越高说明措辞越不千篇一律。",
            },
        },
        "weights": weights,
        "statistical_score": round(statistical_score, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="统计层人味打分")
    parser.add_argument("source", help="文件路径，或 '-' 表示从 stdin 读取")
    parser.add_argument("--text", help="直接传入文本而不是文件路径", default=None)
    args = parser.parse_args()

    if args.text is not None:
        text = args.text
    elif args.source == "-":
        text = sys.stdin.read()
    else:
        with open(args.source, "r", encoding="utf-8") as f:
            text = f.read()

    result = analyze(text)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
