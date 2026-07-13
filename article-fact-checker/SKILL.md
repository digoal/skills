---
name: article-fact-checker
description: 三层审查模型,逐段逐句验证文章真伪、证据链与逻辑结构。Use when the user asks to fact-check, verify, audit, or evaluate the credibility of an article, essay, report, opinion piece, social-media post, or any written claim — including checking logical consistency, evidence chains, source reliability, fabrication, non-quantifiable conclusions, and producing a scored report with original-text citations.
---

# Article Fact Checker

## Overview

对任意文章做三层审查(L1 整体立论 / L2 段落论证 / L3 句子证据),产出可重复使用的带原文引用的评分报告。覆盖逻辑、证据链、可考、源头、不可量化结论的判定。

## When to use this skill

触发场景(满足任一即可):

- 用户明确要求 fact-check / 验证 / 鉴定 / 审查一篇文章
- 用户问"这段文字/这篇报道可信吗"
- 用户要求评估某观点的证据链
- 用户要求做信息溯源、源头考证
- 用户问"这个数据/引文是真的吗"
- 用户提供一段或一篇文字,要求做真伪评估并打分

不适用:

- 用户只是要求改写、翻译、总结(改用对应 skill)
- 用户要求从零写文章(用写作类 skill)

## Workflow(六遍通读法)

按顺序执行,每遍只解决一层问题。先粗后细,不要从证据找起。

### Pass 1 — L1 整体层(5 min)

只回答:**作者在主张什么?前提是什么?**

提取 4 项:

1. **立论**(一句话复述)
2. **隐含前提**(作者没说但必须为真的假设)
3. **范围边界**(时间 / 地域 / 对象 / 条件)
4. **整体定调**(严肃学术 / 媒体评论 / 营销 / 自媒体 / 营销软文 / 宣传)

详见 [references/layer1-overall.md](references/layer1-overall.md)。

### Pass 2 — L2 段落层(15 min)

逐段标注:主题句、段落主张、段落间关系(并列/递进/对比/回扣/游离)。

标记每段的推理类型:**演绎 / 归纳 / 类比 / 直觉**。

扫描常见逻辑谬误。详见 [references/layer2-paragraph.md](references/layer2-paragraph.md) 和 [references/logical-fallacies.md](references/logical-fallacies.md)。

### Pass 3 — L3 句子/证据层(30 min)

抽取所有具体证据进 evidence list:

| 类型 | 例子 | 反向搜证命令 |
|---|---|---|
| 数据 | "73.8% 的用户…" | `data:"<具体数字>"` |
| 引文 | "XX 研究表明…" | `<作者> <期刊> <年份>` |
| 事件 | "2024 年 3 月 X 公司…" | `<主体> <日期> <事件关键词>` |
| 概念 | "根据 Y 理论…" | `<理论名> site:.edu OR site:.org` |

详见 [references/layer3-sentence.md](references/layer3-sentence.md) 和 [references/evidence-verification.md](references/evidence-verification.md)。

自动化辅助:运行 `scripts/evidence-extractor.py` 从粘贴的文章自动抽取候选证据。

### Pass 4 — 横向验证(45 min)

每个高风险证据做一次反向搜证;每个核心主张找 ≥2 个**独立**(无相互引用)来源做三角验证。

工具链:

- Google Scholar / PubMed / 知网 — 学术
- TinEye / Google Images — 反向搜图
- Wayback Machine — 查历史快照
- Factiva / 主流媒体 — 新闻事件

方法论:见 [references/methodology.md](references/methodology.md)。

### Pass 5 — 不可量化结论判定

如果结论是定性的(不可量化),套 **6 维定性评估法**:

| 维度 | 评估问题 |
|---|---|
| ① 内部一致性 | 与文章所有事实陈述是否自洽? |
| ② 既有事实兼容性 | 与已确认的共识/物理规律是否相容? |
| ③ 共识程度 | 主流学界/业界是否认可? |
| ④ 可证伪性 | 能否举出"如果 X 发生则结论失败"的反例? |
| ⑤ 替代解释覆盖 | 作者是否主动列出并反驳其他解释? |
| ⑥ 时间检验 | 1 年 / 5 年 / 10 年回看是否仍成立? |

**关键洞察**:任何定性结论,作者说不出"什么情况下我会承认我错了" = 营销文/信仰文,不是知识。

详见 [references/qualitative-assessment.md](references/qualitative-assessment.md)。

### Pass 6 — 证据链完整性检查

对每条核心主张画证据链:

```
主张 P
├─ 证据 E1 → 直接支持 P? ☐ 全 ☐ 部分 ☐ 否
├─ 证据 E2 → 直接支持 P? ☐ 全 ☐ 部分 ☐ 否
├─ 证据 E3 → ……
├─ 缺失环节 G1: 需要的额外假设是什么?
├─ 缺失环节 G2: ……
└─ 反证 R: 被忽略的支持否定 P 的证据?
```

常见缺口:关键假设未声明 / 反证被剔除 / 第三变量未控制 / 样本迁移。

## 输出报告

复制 [assets/report-template.md](assets/report-template.md) 模板,产出:

1. **立论复述** + **整体定调判断**
2. **L1 / L2 / L3 三层评分**(各维 1-5 分)
3. **加权总分**(默认 L1=30% / L2=30% / L3=40%,可按文章类型调整)
4. **问题清单**(每条引用原文,标严重度 高/中/低)
5. **采纳建议**:推荐采纳 / 谨慎采纳 / 不予采纳 / 需进一步核查

## Resources

### scripts/

- `evidence-extractor.py` — 从粘贴的文章中按正则模式自动抽取候选证据(数据/引文/事件),输出 evidence-list.json。Pass 3 自动化辅助。

### references/

- `layer1-overall.md` — L1 整体层 8 项检查清单
- `layer2-paragraph.md` — L2 段落层 5 项结构检查 + 段落关系矩阵
- `layer3-sentence.md` — L3 句子层 6 项动作 + 模糊归因红榜
- `logical-fallacies.md` — 常见逻辑谬误分类清单(供 L2 排查)
- `evidence-verification.md` — 证据可考性 / 捏造识别 / 源头可信度评估
- `qualitative-assessment.md` — 不可量化结论的 6 维定性评估法(详细)
- `methodology.md` — SIFT / CRAAP / 横向阅读 / 三角验证方法论

### assets/

- `report-template.md` — Markdown 评分报告模板(直接复制使用)

## 时间预算参考

| 文章长度 | 完整审查耗时 |
|---|---|
| 推文 / 短帖(< 500 字) | 15-30 min |
| 媒体评论 / 博客(500-3000 字) | 1-2 h |
| 深度报道 / 学术综述(3000-10000 字) | 3-5 h |
| 长篇报告 / 书籍章节(> 10000 字) | 8+ h |

如时间不允许,至少做 Pass 1 + Pass 2 + Pass 3 证据抽查 → 输出简化版报告。