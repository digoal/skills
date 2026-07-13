---
name: job-advisor
description: 从招聘平台(闲鱼兼职、Boss直聘、智联、拉勾、58同城、豆瓣兼职等)抓取招聘信息,根据用户输入的个人特征(技能、地点、时间、薪资期望、工作形式偏好)匹配适合的长期雇佣或临时工机会,按性价比(加权时薪)排序,输出 markdown 推荐报告到当前项目的 markdown 目录。当用户提出"找工作"、"匹配岗位"、"接私活"、"找兼职"、"招聘推荐"、"什么活适合我"等需求时触发。
---

# Job Advisor

## Overview

给定个人特征(技能、地点、可投入时间、薪资下限、工作形式偏好),从公开渠道抓取招聘信息,按 **加权时薪 = 基础时薪 × 技能匹配 × 通勤折算 × 灵活度** 排序,输出 markdown 推荐报告。

**除直接技能匹配外,本 skill 同时识别"借助 AI 工具也能较轻松拿下"的岗位**(基础翻译、文案润色、简单海报、字幕、PPT、数据录入、信息搜集等),在报告中以**独立专区**形式单独列出,不污染主 Top10 的技能匹配排序。

## 抓取渠道与限制(必读)

直接抓取 Boss直聘/闲鱼等平台 API 在工程上不可行(登录墙、强反爬、风控)。本 skill 采用**搜索引擎聚合**的实用策略:

| 渠道 | 抓取方式 | 说明 |
|---|---|---|
| 闲鱼兼职 | `mmx web_search "site:goofish.com 兼职"` 等 | 通过搜索引擎拿公开页面摘要 |
| Boss直聘 | `mmx web_search "site:zhipin.com <关键词>"` | 同上,只能拿搜索结果摘要 |
| 智联招聘 | `mmx web_search "site:zhaopin.com <关键词>"` | 同上 |
| 拉勾 | `mmx web_search "site:lagou.com <关键词>"` | 同上 |
| 58同城兼职 | `mmx web_search "site:58.com 兼职 <关键词>"` | 同上 |
| 豆瓣兼职小组 | `mmx web_search "site:douban.com 兼职 <关键词>"` | 同上 |
| 小蜜蜂远程工作 | `mmx web_search "site:xiaomifeng.work"` | 远程岗位聚合 |
| 电鸭社区 | `mmx web_search "site:eleduck.com 远程"` | 远程岗位 |

> 反爬声明:不要尝试用 requests/selenium 直接打平台,会被封 IP。本 skill 仅依赖搜索引擎可达的公开摘要,结果可能滞后/不完整,报告必须注明数据时间。

## 工作流程

1. **澄清输入** — 若用户未给出 [references/profile_schema.md](references/profile_schema.md) 必需字段(技能、地点、时间、薪资下限),先用 AskUserQuestion 问齐。
2. **构造搜索词** — 按 [references/platforms.md](references/platforms.md) 的模板,为每个平台生成 3-5 个搜索 query。
3. **并发抓取** — 通过 `mmx web_search` 执行每个 query,合并去重。
4. **结构化抽取** — 从搜索结果摘要中抽取 `title / company / location / pay / type / skills / link / source_platform` 字段,字段缺失则降级或丢弃。
5. **打分排序** — 调用 `scripts/match_jobs.py`,传入 `profile.json` 与 `jobs.json`,得到排序结果。
6. **生成报告** — 按 [references/output_template.md](references/output_template.md) 模板渲染 markdown,写入 `<项目根>/markdown/<日期>_job-recommendations.md`。
7. **自检清单** — 报告末尾追加:抓取时间、平台数、抓取条目数、排序后保留数、被过滤原因分布。

## 输入规格

读 [references/profile_schema.md](references/profile_schema.md) 完整定义。最小必填:

```json
{
  "skills": ["Python", "PostgreSQL"],
  "location": "杭州",
  "available_hours_per_week": 20,
  "min_hourly_rate": 150,
  "preferred_types": ["remote", "part_time"]
}
```

可选:`max_commute_minutes`、`avoid_keywords`、`language`、`experience_years`、`industries`。

## 抓取执行规范

- 每个平台最多 5 个 query,共 ≤ 30 次 web_search。
- 单次搜索只取前 5 条结果,合并去重后保留不超过 30 条原始记录。
- 单条记录若关键字段(title/pay/source_platform)缺失且无法从摘要中推断,丢弃并在报告中计入"被过滤"。
- 抓取完成后,**先**调用打分脚本,**再**渲染报告。

## 打分脚本调用

```bash
python3 scripts/match_jobs.py \
  --profile /path/to/profile.json \
  --jobs /path/to/jobs.json \
  --top 10 \
  --out /path/to/scored_jobs.json
```

`scripts/match_jobs.py` 读取两份 JSON,返回按 `cost_effectiveness_score` 降序的列表,含逐项打分明细。详见脚本内 docstring。

## 输出规格

- 文件位置:`<cwd>/markdown/<YYYY-MM-DD>_job-recommendations.md`
- 模板:[references/output_template.md](references/output_template.md)
- 必含:概要、Top10 表格、逐条详情(标题/公司/地点/薪资/工作形式/链接/打分明细/风险提示)、数据来源与免责声明。

## 失败与降级

| 情况 | 处理 |
|---|---|
| 用户未给地点或薪资下限 | AskUserQuestion 澄清,不要瞎猜 |
| 搜索引擎全失败 | 报告中标注"无可用抓取数据",不输出空 Top10 |
| 抓取 < 5 条 | 仍输出,但顶部加明显警示"样本不足,建议补充搜索词" |
| 字段无法解析薪资 | 标记为 `pay_unknown=true`,打分时该项置 0 并降权 |

## AI 友好岗位(独立专区)

很多岗位在传统视角下需要专业技能(翻译资质、设计功底、剪辑经验等),但**借助 AI 工具链(LLM 翻译/文案、SD/MJ 生图、Whisper 字幕、PPT 排版等)准入门槛已大幅降低**。本 skill 把这类岗位识别后,以"AI 友好专区"形式单独列在报告末尾,与主 Top10 解耦。

**机制:**
- `scripts/match_jobs.py` 维护 `AI_ASSISTABLE_KEYWORDS` 列表(翻译、文案、海报、字幕、PPT、数据录入、调研、客服话术等)
- 关键词命中即在 `_score.ai_friendly=true` 标记,**不参与主排名加权**(避免污染技能匹配结果)
- 报告渲染时按 `pay_basis` 与 `hourly_rate_cny` 二次排序,生成"AI 友好专区"小节
- 平台搜索词见 [references/platforms.md](references/platforms.md) "AI 友好岗位"章节,与主 query 并发执行,共享 ≤30 次 web_search 上限

**为什么不直接并入主排名:**
- 主 Top10 优先保证"用户技能直接匹配"的命中率
- AI 友好岗位特征差异大,简单加权容易把低匹配度岗位推到前面,降低主推荐质量
- 独立呈现让用户**自主判断**是否愿意承接 AI 辅助类工作

## Resources

### scripts/
- `match_jobs.py` — 性价比打分脚本,见上文调用方式。

### references/
- `platforms.md` — 各平台搜索词模板与反爬说明。
- `profile_schema.md` — 个人特征输入 schema 与示例。
- `output_template.md` — markdown 报告渲染模板。
