#!/usr/bin/env python3
"""
Evidence Extractor — 从粘贴的文章中抽取候选证据

用法:
    python3 evidence-extractor.py < article.txt > evidence-list.json
    python3 evidence-extractor.py --input article.txt --output evidence-list.json
    python3 evidence-extractor.py --input article.txt --md            # Markdown 输出

抽取 4 类证据:
  - data: 数字 / 百分比 / 统计
  - citation: "研究表明"、"专家表示" 等模糊/具体引文
  - event: 含具体日期的事件
  - concept: 理论名 / 概念引用

输出 JSON 字段:
  id, type, snippet, context, paragraph, sentence, search_query, suspicion_level
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ---------- 抽取模式 ----------

# 数据: 数字 + 单位 / 百分比 / 货币 / 日期
DATA_PATTERNS = [
    # 百分比
    (re.compile(r"(\d+(?:\.\d+)?)\s*[%％]"), "百分比"),
    # 货币
    (re.compile(r"[\$￥€£]\s*(\d+(?:[.,]\d+)*(?:\.\d+)?)\s*(万|亿|千|百万|billion|million|trillion)?", re.IGNORECASE), "货币"),
    # 大数字 + 量词
    (re.compile(r"(\d+(?:[.,]\d+)*)\s*(万|亿|千|百万|十亿|亿亿)(?:个|人|次|家|件|元|美元)?", re.IGNORECASE), "大数字"),
    # 温度/度量
    (re.compile(r"(\d+(?:\.\d+)?)\s*(℃|°C|°F|公斤|千克|kg|km|公里|米|m)"), "度量"),
    # 通用数字 + 单位(谨慎,易误报)
    (re.compile(r"(\d+(?:\.\d+)?)\s*(倍|次|倍增|years?|months?|days?)", re.IGNORECASE), "倍数/时长"),
]

# 引文: 模糊归因 + 具体引文标记
CITATION_PATTERNS = [
    # 模糊归因
    (re.compile(r"研究表明[^\s。,，;；]{0,30}"), "模糊归因"),
    (re.compile(r"专家(?:表示|指出|认为|强调)[^\s。,，;；]{0,30}"), "模糊归因"),
    (re.compile(r"研究(?:发现|显示|证实|表明)[^\s。,，;；]{0,30}"), "模糊归因"),
    (re.compile(r"(?:众所周知|据(?:报道|了解|传))[^\s。,，;；]{0,30}"), "模糊归因"),
    (re.compile(r"(?:有|某)(?:人|学者|教授|博士|研究员)(?:指出|表示|认为)[^\s。,，;；]{0,30}"), "模糊归因"),
    # 具体引文: 作者 + 年份 / 期刊
    (re.compile(r"([A-Z][a-zA-ZÀ-ſ]+(?:\s+(?:et\s+al\.?|and|&))?(?:\s+[A-Z][a-zA-ZÀ-ſ]+)*)\s*\(?(\d{4})\)?[^\s。,，;；]{0,60}"), "具体引文"),
    (re.compile(r"根据\s*([一-龥]{2,30}(?:研究|报告|调查|数据|统计|理论))"), "中文引文"),
]

# 事件: 含具体日期
EVENT_PATTERNS = [
    # ISO 日期
    (re.compile(r"(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})日?"), "ISO日期"),
    # 简单年份
    (re.compile(r"(?:19|20)\d{2}\s*年"), "年份"),
    # 季度
    (re.compile(r"(\d{4})\s*年第?\s*([1-4一二三四])\s*季度"), "季度"),
]

# 概念: 理论 / 定律 / 概念 / 模型
CONCEPT_PATTERNS = [
    (re.compile(r"([一-龥A-Za-z]{2,20})\s*(?:理论|定律|法则|效应|原理|模型|假说|悖论)"), "理论/概念"),
    (re.compile(r"(?:根据|依据|按照|基于)\s*([一-龥A-Za-z]{2,20}(?:理论|模型|框架|学说))"), "理论/概念"),
]

# 模糊归因红榜词
VAGUE_WORDS = [
    "研究表明", "专家表示", "专家指出", "专家认为",
    "众所周知", "据报道", "据了解", "据传",
    "有人说", "有人指出", "有研究显示",
    "几乎所有", "绝大多数", "唯一", "绝对", "彻底",
    "惊人", "令人震惊", "难以置信",
    "大量", "许多", "一些", "不少",
]

# 可疑信号: 整洁数字 / 排除性断言
SUSPICION_PATTERNS = [
    (re.compile(r"\d+\.\d{2,}%"), "精度异常的百分比"),
    (re.compile(r"^(?:唯一|绝对|彻底|完全)[^\s。,，;；]{0,20}"), "排除性断言"),
]


# ---------- 抽取函数 ----------

def split_paragraphs(text: str) -> list[str]:
    """按空行分段"""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def split_sentences(paragraph: str) -> list[str]:
    """按中文句末标点分句

    注意:不切 ASCII '.' 以保留小数(如 73.8)、缩写(如 et al.)。
    仅按中文全角句末标点 + 感叹号 + 问号切分。
    """
    return [s.strip() for s in re.split(r"[。！？!?]+\s*", paragraph) if s.strip()]


def extract_from_text(text: str) -> list[dict]:
    """从整篇文章抽取所有候选证据"""
    paragraphs = split_paragraphs(text)
    evidence_list = []
    seen_snippets: set[tuple[int, str, int, int]] = set()  # (paragraph, snippet, start, end)
    eid = 0

    def _add(etype: str, subtype: str, snippet: str, sentence: str,
             paragraph: int, sentence_index: int, position: int) -> None:
        nonlocal eid
        key = (paragraph, snippet, position, len(snippet))
        if key in seen_snippets:
            return
        seen_snippets.add(key)

        eid += 1
        if etype == "data":
            suspicion = assess_suspicion(snippet, sentence)
            search = build_search_query(snippet, "data")
        elif etype == "citation":
            suspicion = "high" if "模糊归因" in subtype else assess_suspicion(snippet, sentence)
            search = build_search_query(snippet, "citation")
        elif etype == "event":
            suspicion = assess_suspicion(snippet, sentence)
            search = build_search_query(snippet, "event")
        else:  # concept
            suspicion = assess_suspicion(snippet, sentence)
            search = build_search_query(snippet, "concept")

        evidence_list.append({
            "id": f"E-{eid:03d}",
            "type": etype,
            "subtype": subtype,
            "snippet": snippet,
            "sentence": sentence,
            "paragraph": paragraph,
            "sentence_index": sentence_index,
            "search_query": search,
            "suspicion_level": suspicion,
        })

    for p_idx, para in enumerate(paragraphs, 1):
        sentences = split_sentences(para)

        for s_idx, sent in enumerate(sentences, 1):
            # 数据
            for pattern, label in DATA_PATTERNS:
                for match in pattern.finditer(sent):
                    _add("data", label, match.group(0), sent, p_idx, s_idx, match.start())

            # 引文
            for pattern, label in CITATION_PATTERNS:
                for match in pattern.finditer(sent):
                    _add("citation", label, match.group(0), sent, p_idx, s_idx, match.start())

            # 事件
            for pattern, label in EVENT_PATTERNS:
                for match in pattern.finditer(sent):
                    _add("event", label, match.group(0), sent, p_idx, s_idx, match.start())

            # 概念
            for pattern, label in CONCEPT_PATTERNS:
                for match in pattern.finditer(sent):
                    _add("concept", label, match.group(0), sent, p_idx, s_idx, match.start())

    return evidence_list


def build_search_query(snippet: str, evidence_type: str) -> str:
    """生成反向搜证查询"""
    if evidence_type == "data":
        # 提取数字 + 周围上下文
        return f'"{snippet.strip()}"'
    elif evidence_type == "citation":
        # 模糊归因搜索原始研究
        return f"{snippet.strip()}"
    elif evidence_type == "event":
        return f"{snippet.strip()}"
    elif evidence_type == "concept":
        return f"{snippet.strip()}"
    return snippet


def assess_suspicion(snippet: str, sentence: str) -> str:
    """评估证据可疑等级"""
    for pattern, reason in SUSPICION_PATTERNS:
        if pattern.search(snippet):
            return "high"
    for word in VAGUE_WORDS:
        if word in sentence:
            return "medium"
    return "low"


# ---------- 输出 ----------

def to_markdown(evidence_list: list[dict]) -> str:
    """生成 Markdown 证据清单"""
    lines = ["# 候选证据清单", ""]
    lines.append(f"**总数**: {len(evidence_list)} 条")
    lines.append(f"**高可疑**: {sum(1 for e in evidence_list if e['suspicion_level'] == 'high')} 条")
    lines.append(f"**中可疑**: {sum(1 for e in evidence_list if e['suspicion_level'] == 'medium')} 条")
    lines.append("")

    # 按类型分组
    by_type: dict[str, list[dict]] = {}
    for e in evidence_list:
        by_type.setdefault(e["type"], []).append(e)

    type_names = {"data": "数据", "citation": "引文", "event": "事件", "concept": "概念"}
    for etype, items in by_type.items():
        lines.append(f"## {type_names.get(etype, etype)}({len(items)} 条)")
        lines.append("")
        lines.append("| ID | 段落 | 原文片段 | 可疑度 | 反向搜证查询 |")
        lines.append("|---|---|---|---|---|")
        for e in items:
            snippet_short = e["snippet"][:50].replace("|", "\\|")
            query = e["search_query"][:60].replace("|", "\\|")
            lines.append(f"| {e['id']} | 段{e['paragraph']}句{e['sentence_index']} | {snippet_short}... | {e['suspicion_level']} | `{query}` |")
        lines.append("")

    return "\n".join(lines)


# ---------- CLI ----------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="从文章抽取候选证据(data/citation/event/concept),用于人工核查。"
    )
    parser.add_argument("--input", "-i", help="输入文件路径(默认 stdin)")
    parser.add_argument("--output", "-o", help="输出文件路径(默认 stdout)")
    parser.add_argument("--md", action="store_true", help="Markdown 格式输出(默认 JSON)")
    args = parser.parse_args()

    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("[ERROR] 输入为空", file=sys.stderr)
        return 1

    evidence = extract_from_text(text)
    result = to_markdown(evidence) if args.md else json.dumps(evidence, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"[OK] 抽取 {len(evidence)} 条证据 → {args.output}", file=sys.stderr)
    else:
        print(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())