# 人工验证 / anti-bot 兜底方案

部分源对自动化请求做限制。下面的方案按源给出兜底路径，确保周报不会因为单源失败而中断。

## git.postgresql.org（最常见）

**症状**：`HTTP 200` 但返回 anti-bot 验证页（标题 `<title>Just a moment...` 或含 `cf-chl-bypass` / `Verifying you are human`）；或直接 `HTTP 403/429/503`。

**兜底步骤**：

1. 用 `mcp__MiniMax__web_search` 搜：
   - `postgresql.git site:git.postgresql.org shortlog 2026-06-16`
   - `Michael Paquier commit postgresql last week`
   - `Heikki Linnakangas postgresql git commit june 2026`
   - `Amit Langote postgresql commit`
   - `Álvaro Herrera postgresql commit`
   - `Fujii Masao postgresql commit`

2. 从搜索结果摘要里抽 commit subject + hash + author。

3. 若仍信息不足，对单条 commit 用 `https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=<hash>` 通过 `WebFetch` 抓取，commit 页通常是静态 HTML，反爬宽松。

4. 把抽到的 commit 列表用 `Item(date, title=subject, url=commit_url, summary="by <author>", tags=["PG", "内核"])` 填回 `SourceResult`。

5. 在"数据源覆盖"章标 `🙋 human_required`，备注写 "anti-bot, fallback via WebSearch commit lookup"。

**降级**：若连 commit hash 都凑不齐，用 weekly 内核趋势描述代替（如"本周 PG 内核主线仍在 logical decoding 修复 + pg_restore 改进 + RI 快路径稳定性"），不写具体 hash。

## github.com/trending

**症状**：`HTTP 529`（github 推理网关偶尔过载）或返回不完整页面。

**兜底**：

1. 重试 1 次（间隔 30s）。
2. 仍失败则用 `mcp__MiniMax__web_search` 搜 `github trending weekly <month>` 或 `github trending this week <lang>`，从搜索摘要里取仓库名 / 描述。
3. 仍取不到则章五标 `❌ error`，跳过整章（保留章节结构，列表说"本周无可展示项目"）。

## huggingface.co/papers/trending

**症状**：偶尔会混入博客条目时间线（页面结构变化），近 7 天 trending 论文定位不到。

**兜底**：

1. 抓 `https://huggingface.co/papers?date=today`（每日 trending）逐日回退 7 天。
2. 或改抓 `https://huggingface.co/papers` 默认页（按 trending 排）。
3. 仍失败则章六标 `⚠️ empty`，描述"本周 trending 论文未能定位"。

## aibase.com / ai-bot.cn（中文源）

**症状**：访问正常但内容含大量微信公众号跳转链接（落地页 404）。

**处理**：保留公众号原文链接（`mp.weixin.qq.com/s/...`），不要试图打开落地页。

## postgresweekly.com 解析失败

**症状**：`/issues` 页面结构变化，找不到 `/issues/<N>` 锚点。

**兜底**：

1. 用 `mcp__MiniMax__web_search` 搜 `postgresweekly.com issues 2026`。
2. 手动取最近 issue 编号，构造 `https://postgresweekly.com/issues/<N>`。
3. 用 `WebFetch` 抓取该单期页面。

## planet.postgresql.org / planet.postgis.net

**症状**：Planet 平台（Venus / rawdog feed）偶尔 5xx。

**兜底**：重试 2 次（指数退避 30s/60s），仍失败标 `❌ error`，不影响其他源。

## postgresql.org/about/newsarchive/

**症状**：偶尔 `HTTP 529`。

**兜底**：标 `❌ error`，周报中正常章节保留占位说明；该源本就条目稀疏（重大版本发布才有新闻），无条目本身不是异常。

## 通用兜底原则

- 单源失败 **永远不阻塞** 其他 9 源。
- 失败源在"数据源覆盖"章如实标注，不美化。
- 不在条目里写"由于 XX 失败所以本周没有"这种抱怨性文字 —— 直接说"本周无新条目"。
- 若一周内某源连续 2 周失败，下次执行前建议用户人工核查（`human_required` 状态）。