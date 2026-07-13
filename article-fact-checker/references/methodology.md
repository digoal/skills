# 方法论工具箱

## SIFT 法则(Mike Caulfield)

四个动作:

| 动作 | 含义 | 操作 |
|---|---|---|
| **S**top | 停下来,不要立刻相信第一反应 | 看到惊人主张时,先暂停 |
| **I**nvestigate the source | 调查来源 | 谁写的?为谁写?出资方? |
| **F**ind better coverage | 找更好的覆盖 | 别只读一篇,横向比较 |
| **T**race claims | 追踪原始声明 | 引用的研究/数据原始出处是? |

适用场景:日常快速核查,适合处理单条主张。

## CRAAP 测试(加州州立大学)

5 个维度:

| 维度 | 评估问题 |
|---|---|
| **C**urrency 时效 | 发布日期?时效内? |
| **R**elevance 相关 | 与你的需求相关? |
| **A**uthority 权威 | 作者资质?机构权威? |
| **A**ccuracy 准确 | 证据可考?可验证? |
| **P**urpose 目的 | 为什么发布?为谁服务? |

适用场景:评估单一来源。

## 横向阅读法(Lateral Reading)

**不要纵向深读一篇文章,而是横向跳出读别的来源。**

具体操作:
1. 读完文章后,**立刻**打开新标签查作者/机构
2. 查该作者在其他场合的言论
3. 查该机构的历史立场、利益相关
4. 查其他媒体/学者对该事件的报道
5. 形成"侧面画像"再回到原文

**核心洞察**:专业 fact-checker 不读完原文,而是先用 30 秒查作者背景。

适用场景:任何事实核查的第一阶段。

## 三角验证(Triangulation)

**同一主张找 ≥3 个独立来源验证。**

"独立" = 三个来源之间没有相互引用 / 共同资助方 / 共同作者。

操作:
1. 列出主张
2. 找 3 个独立来源
3. 比对:
   - 全部一致 → 强可信
   - 2 个一致,1 个不同 → 查不同源的差异原因
   - 全部不同 → 主张本身有问题
   - 看似多源但实际同源 → 自循环引用,价值低

适用场景:核心主张的最终验证。

## 反向搜证链

针对数据 / 引文 / 事件 / 概念的不同搜证命令见 [evidence-verification.md](evidence-verification.md)。

## 时间检验法

对于预测性结论,检查:
- 结论发表后是否兑现?
- 有无反例事件?
- 作者是否回应过反例?

对于历史性结论,检查:
- 是否使用了后来被推翻的史料?
- 是否被后续考古/档案发现更新?

## 不可量化结论的方法论

见 [qualitative-assessment.md](qualitative-assessment.md)。

## 工具速查表

| 任务 | 工具 |
|---|---|
| 学术搜索 | Google Scholar / PubMed / 知网 / Microsoft Academic |
| 反向搜图 | TinEye / Yandex Images / Google Images |
| 历史快照 | Wayback Machine |
| 事实核查数据库 | Snopes / FactCheck.org / PolitiFact |
| 撤稿论文 | Retraction Watch |
| 期刊黑名单 | Beall's List(历史) / Cabells Predatory Reports |
| 域名信息 | whois / 备案查询 |
| 新闻数据库 | Factiva / LexisNexis / ProQuest |
| 中文核查 | 腾讯较真 / 澎湃明查 |

## 工作流整合

```
Phase 1 (5 min)  →  SIFT.Stop + 横向阅读作者背景
Phase 2 (15 min) →  CRAAP 测试整体来源
Phase 3 (30 min) →  三角验证核心主张
Phase 4 (45 min) →  反向搜证所有数据/引文
Phase 5 (20 min) →  不可量化结论 6 维评估
Phase 6 (15 min) →  出报告
```

## 自我审视清单

完成核查后,问自己:

- 我有没有被文章的修辞影响?(用 6 维法重新过一遍)
- 我有没有倾向性?(如果有,反向查证一下反向证据)
- 我有没有用模糊归因替代具体证据?(回到原文找原文)
- 我的判断有没有利益相关?(若核查结果与我立场一致,要更严)

**最危险的偏差**:确认偏误(confirmation bias) — 找支持自己结论的证据,忽略反驳。专业核查者必须主动反查。