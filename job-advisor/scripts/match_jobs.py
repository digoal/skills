#!/usr/bin/env python3
"""
match_jobs.py — 个人特征 × 招聘信息 → 性价比排序

性价比 = 基础时薪 × 技能匹配系数 × 通勤折算 × 灵活度系数 × 类型匹配

Usage:
  python3 match_jobs.py \
    --profile profile.json \
    --jobs jobs.json \
    --top 10 \
    --out scored.json

AI 友好岗位: 通过 AI_ASSISTABLE_KEYWORDS 命中即标记 ai_friendly=true,
             不参与主排名加权,由报告层独立渲染为"AI 友好专区"。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# ---------- 薪资解析 ----------

# 捕获 "150/时", "150元/小时", "1.5k/天", "20k-30k/月", "面议"
PAY_HOURLY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:元|¥|RMB)?\s*/\s*(?:时|小时|h|hour)", re.I)
PAY_DAILY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*k?\s*(?:元|¥|RMB)?\s*/\s*(?:天|日|day)", re.I)
PAY_MONTHLY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*k\s*(?:元|¥|RMB)?\s*/\s*月", re.I)
PAY_RANGE_MONTHLY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*k\s*[-—~到至]\s*(\d+(?:\.\d+)?)\s*k\s*/\s*月")
PAY_PER_PROJECT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:k|K|万|w)?\s*(?:元|¥|RMB)?\s*/\s*(?:单|个|次|project|piece)")


# 工作形式关键词双向归一(中文 + 英文别名都映射到同一个 canonical key)
TYPE_ALIASES = {
    "remote": ["远程", "remote"],
    "part_time": ["兼职", "part_time", "part-time", "freelance", "临时", "零工"],
    "full_time": ["全职", "full_time", "full-time"],
    "freelance": ["freelance", "自由", "freelancer", "独立"],
    "contract": ["外包", "contract", "合约"],
    "project": ["项目", "project", "单次", "按单"],
}


# ---------- AI 友好岗位 ----------

# 借助 AI 工具链(LLM 翻译/文案、SD/MJ 生图、Whisper 字幕、PPT 排版等)
# 准入门槛被显著降低的岗位类别。命中关键词即标记 ai_friendly=true,
# 不参与主排名加权,由报告层独立渲染。
AI_ASSISTABLE_KEYWORDS = [
    # 翻译
    "翻译", "translator", "translation", "translate", "译员", "笔译", "口译",
    # 文案撰稿
    "文案", "撰稿", "copywriter", "copywriting", "软文", "种草", "脚本",
    "公众号", "小红书文案", "短视频脚本", "营销文案", "广告文案", "slogan",
    # 设计图像
    "海报", "banner", "封面", "logo", "图标", "icon", "配图", "插画", "头像",
    # 视频
    "字幕", "subtitles", "视频剪辑", "剪辑", "短视频",
    # 文档
    "ppt", "排版", "校对", "润色", "proofreading", "演示文稿",
    # 数据
    "数据录入", "数据整理", "信息搜集", "调研", "research",
    # 客服话术
    "客服话术", "客服脚本", "faq", "回复模板",
]


def ai_assistable_flag(job: dict) -> bool:
    """判断岗位是否属于"AI 友好"类别 — 用户即使没有直接技能,借助 AI 也能轻松拿下。

    命中即返回 True,主排名不依赖此标志,仅用于报告分区展示。
    """
    haystack = " ".join([
        job.get("title") or "",
        job.get("description") or "",
        job.get("type") or "",
    ])
    haystack_l = haystack.lower()
    for kw in AI_ASSISTABLE_KEYWORDS:
        # 同时做大小写不敏感(英文)与原文包含(中文)判断
        if kw.lower() in haystack_l or kw in haystack:
            return True
    return False


def _job_type_text(job_type: str) -> set[str]:
    """从 job.type 字符串里抽出所有 canonical type key。"""
    text = (job_type or "").lower()
    return {key for key, aliases in TYPE_ALIASES.items() if any(a.lower() in text for a in aliases)}


def parse_hourly_rate(pay_text: str) -> tuple[float | None, str]:
    """把各种写法归一到元/小时。返回 (rate, basis) basis ∈ {hourly, daily, monthly, project, unknown}"""
    if not pay_text:
        return None, "unknown"
    if "面议" in pay_text or "negotiable" in pay_text.lower():
        return None, "unknown"

    m = PAY_HOURLY_RE.search(pay_text)
    if m:
        return float(m.group(1)), "hourly"

    m = PAY_DAILY_RE.search(pay_text)
    if m:
        val = float(m.group(1))
        # 数字是 k 结尾就 *1000
        if re.search(r"\d+\s*k\s*(?:元|¥|RMB)?\s*/\s*(?:天|日|day)", pay_text, re.I):
            val *= 1000
        # 假设 8 小时工作日
        return round(val / 8, 2), "daily"

    m = PAY_RANGE_MONTHLY_RE.search(pay_text)
    if m:
        lo = float(m.group(1)) * 1000
        hi = float(m.group(2)) * 1000
        mid = (lo + hi) / 2
        # 假设 22 工作日 × 8 小时 = 176 小时/月
        return round(mid / 176, 2), "monthly"

    m = PAY_MONTHLY_RE.search(pay_text)
    if m:
        val = float(m.group(1)) * 1000
        return round(val / 176, 2), "monthly"

    m = PAY_PER_PROJECT_RE.search(pay_text)
    if m:
        val = float(m.group(1))
        if "k" in pay_text.lower() or "K" in pay_text:
            val *= 1000
        if "万" in pay_text or "w" in pay_text.lower():
            val *= 10000
        # 项目制无法折算时薪,先按 20 小时估算,可被覆盖
        return round(val / 20, 2), "project"

    return None, "unknown"


# ---------- 系数计算 ----------

def skill_match(profile_skills: list[str], job: dict) -> float:
    """技能匹配系数 [0, 1]。profile 技能覆盖 job 要求越多分越高。"""
    required = job.get("required_skills") or job.get("skills") or []
    if not required:
        return 0.5  # 没标明就当半匹配

    profile_set = {s.lower().strip() for s in profile_skills}
    required_set = {s.lower().strip() for s in required}

    if not required_set:
        return 0.5

    overlap = profile_set & required_set
    return round(len(overlap) / len(required_set), 3)


def commute_factor(profile: dict, job: dict) -> float:
    """通勤折算系数 [0.3, 1.0]。remote=1.0,同地=1.0,跨城按距离降权。"""
    if job.get("remote") or "远程" in (job.get("location") or ""):
        return 1.0

    p_loc = (profile.get("location") or "").strip()
    j_loc = (job.get("location") or "").strip()

    if not p_loc or not j_loc or p_loc == j_loc:
        return 1.0

    # 同省不同城市 / 同城不同区 — 0.7;跨省 — 0.4
    p_prov = p_loc[:2] if len(p_loc) >= 2 else p_loc
    j_prov = j_loc[:2] if len(j_loc) >= 2 else j_loc

    if p_prov == j_prov:
        return 0.7
    return 0.4


def flexibility_factor(job: dict, preferred: list[str]) -> float:
    """灵活度系数 [0.5, 1.1]。自由时间越多系数越高。"""
    score = 0.7
    canonical = _job_type_text(job.get("type") or "")

    if "part_time" in canonical or "freelance" in canonical:
        score = 1.0
    if "remote" in canonical:
        score = max(score, 1.05)
    if "contract" in canonical or "project" in canonical:
        score = max(score, 0.95)
    if "full_time" in canonical and "remote" not in canonical:
        score = min(score, 0.7)

    # 是否符合偏好(基于 canonical key)
    if preferred:
        pref_canonical: set[str] = set()
        for p in preferred:
            for key, aliases in TYPE_ALIASES.items():
                if p.lower() == key or p.lower() in [a.lower() for a in aliases]:
                    pref_canonical.add(key)
                    break
        if canonical & pref_canonical:
            score += 0.05

    return min(round(score, 3), 1.1)


def type_match(job: dict, preferred: list[str]) -> float:
    """类型匹配 [0, 1]。基于 canonical key 比对,中英文别名都识别。"""
    if not preferred:
        return 1.0
    canonical = _job_type_text(job.get("type") or "")

    pref_canonical: set[str] = set()
    for p in preferred:
        for key, aliases in TYPE_ALIASES.items():
            if p.lower() == key or p.lower() in [a.lower() for a in aliases]:
                pref_canonical.add(key)
                break
        else:
            pref_canonical.add(p.lower())

    if not pref_canonical:
        return 0.0
    hits = len(canonical & pref_canonical)
    return round(hits / len(pref_canonical), 3)


# ---------- 主打分 ----------

def score_job(profile: dict, job: dict) -> dict:
    """单条打分,返回带 score 明细的 dict。"""
    pay_text = job.get("pay_text") or job.get("pay") or ""
    hourly, basis = parse_hourly_rate(pay_text)
    pay_unknown = hourly is None

    s_skill = skill_match(profile.get("skills") or [], job)
    f_commute = commute_factor(profile, job)
    f_flex = flexibility_factor(job, profile.get("preferred_types") or [])
    f_type = type_match(job, profile.get("preferred_types") or [])

    min_rate = profile.get("min_hourly_rate") or 0
    if pay_unknown:
        # 薪资未知降权但保留,方便人工判断
        cost_eff = 0
        meets_floor = False
    else:
        # 基础分 = 实际时薪 / 用户期望时薪,>1 表示超期望
        if min_rate > 0:
            base = hourly / min_rate
        else:
            base = hourly / 100  # 没设期望就按 100 元/h 基准
        cost_eff = round(base * s_skill * f_commute * f_flex * f_type, 4)
        meets_floor = hourly >= min_rate

    # 关键词黑名单
    avoid = profile.get("avoid_keywords") or []
    title_text = (job.get("title") or "").lower()
    desc_text = (job.get("description") or "").lower()
    blocked = [k for k in avoid if k.lower() in title_text or k.lower() in desc_text]

    return {
        **job,
        "_score": {
            "hourly_rate_cny": hourly,
            "pay_basis": basis,
            "pay_unknown": pay_unknown,
            "skill_match": s_skill,
            "commute_factor": f_commute,
            "flexibility_factor": f_flex,
            "type_match": f_type,
            "cost_effectiveness_score": cost_eff,
            "meets_salary_floor": meets_floor,
            "blocked_by_keyword": blocked,
            "ai_friendly": ai_assistable_flag(job),
        },
    }


def rank_jobs(profile: dict, jobs: list[dict], top: int | None = None) -> list[dict]:
    scored = [score_job(profile, j) for j in jobs]

    # 关键词黑名单的丢到最后,score=0 但保留可见
    def sort_key(item):
        s = item["_score"]
        if s["blocked_by_keyword"]:
            return (1, 0)
        if s["pay_unknown"]:
            # 未知薪资排在已知薪资之后,按技能匹配和类型匹配二次排序
            return (0, -(s["skill_match"] + s["type_match"]))
        return (0, -s["cost_effectiveness_score"])

    scored.sort(key=sort_key)

    if top:
        scored = scored[:top]
    return scored


def split_ai_friendly(scored_jobs: list[dict]) -> tuple[list[dict], list[dict]]:
    """把打分结果拆成 (常规, AI友好)。

    AI 友好专区排序规则:已知薪资按 hourly_rate_cny 降序,未知薪资靠后。
    """
    regular = [j for j in scored_jobs if not j["_score"]["ai_friendly"]]
    friendly = [j for j in scored_jobs if j["_score"]["ai_friendly"]]

    def friendly_key(item):
        s = item["_score"]
        if s["pay_unknown"]:
            return (1, 0)
        return (0, -(s["hourly_rate_cny"] or 0))

    friendly.sort(key=friendly_key)
    return regular, friendly


# ---------- IO ----------

def load_json(path: str) -> Any:
    p = Path(path)
    if not p.exists():
        sys.exit(f"file not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    profile = load_json(args.profile)
    jobs = load_json(args.jobs)

    if not isinstance(jobs, list):
        sys.exit("--jobs 必须是 JSON 数组")

    ranked = rank_jobs(profile, jobs, top=args.top)

    Path(args.out).write_text(
        json.dumps(ranked, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 简报
    n = len(ranked)
    known = sum(1 for j in ranked if not j["_score"]["pay_unknown"])
    print(f"[match_jobs] ranked {n} jobs ({known} with parsed pay)")


if __name__ == "__main__":
    main()
