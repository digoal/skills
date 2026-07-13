# 平台搜索词模板与反爬说明

## 总原则

- **不直接请求平台域名**。Boss直聘/闲鱼/智联都有强反爬(IP 限速、登录墙、风控)。
- 走 `mmx web_search` 加 `site:` 操作符,搜索引擎返回的摘要已经够抽取结构化字段。
- 每个平台 ≤ 5 个 query,总量 ≤ 30 次 web_search。

## 通用 query 构造规则

```
site:<平台域名> "<技能1> <技能2>" <工作形式> <地点>
```

例如:Python + 远程 → `site:zhipin.com "Python" 远程`

## 各平台模板

### 闲鱼兼职(`goofish.com`)
适合:短期、零工、技能变现、私单。
```
site:goofish.com 兼职 <技能>
site:goofish.com <技能> 接单
site:goofish.com <技能> 远程
```
要点:闲鱼"兼职"频道大量是按单结算,适合项目制。

### Boss直聘(`zhipin.com`)
适合:长期雇佣、薪资透明、有 JD。
```
site:zhipin.com "<技能1>" <地点>
site:zhipin.com "<技能1> <技能2>" <地点>
site:zhipin.com "<技能1>" 远程
site:zhipin.com "<技能1>" 兼职
```
注意:boss 搜索结果含大量"boss 主动联系"广告,抽取时优先选有明确薪资区间的。

### 智联招聘(`zhaopin.com`)
适合:大型企业、国企、外企。
```
site:zhaopin.com "<技能1>" <地点>
site:zhaopin.com "<技能1>" 兼职 <地点>
```

### 拉勾(`lagou.com`)
适合:互联网技术岗。
```
site:lagou.com "<技能1>" <地点>
site:lagou.com "<技能1>" 远程
```

### 58 同城兼职(`58.com`)
适合:本地服务、家教、促销、跑腿。
```
site:58.com 兼职 <技能> <地点>
site:58.com 兼职 <地点>
```

### 豆瓣兼职小组(`douban.com`)
适合:文案、设计、翻译、撰稿。
```
site:douban.com 兼职 <技能>
site:douban.com <技能> 接活
```
注意:豆瓣内容质量参差,需要看发帖时间和回复数判断活跃度。

### 小蜜蜂远程工作(`xiaomifeng.work`)
适合:远程岗位聚合,有英文岗位。
```
site:xiaomifeng.work <技能>
site:xiaomifeng.work remote <技能>
```

### 电鸭社区(`eleduck.com`)
适合:远程、技术 freelance。
```
site:eleduck.com 远程 <技能>
site:eleduck.com freelance <技能>
```

### V2EX 酷工作(`v2ex.com`)
适合:技术圈,远程 + freelance 信息密度高。
```
site:v2ex.com 酷工作 <技能>
site:v2ex.com 远程 <技能>
```

## AI 友好岗位(跨平台通用)

这些岗位在传统视角下需要专业技能(翻译资质、设计功底、剪辑经验),但**借助 AI 工具链**(LLM 翻译/文案、SD/MJ 生图、Whisper 字幕、PPT 排版等)准入门槛大幅降低。本 skill 把这类岗位识别后单独列出为"AI 友好专区",不参与主排名加权。

适用类别:基础翻译、文案润色、简单海报、字幕、PPT、数据录入、信息搜集、客服话术等。

```
site:goofish.com 翻译 接单
site:goofish.com 文案 接单
site:goofish.com 海报 接单
site:goofish.com 字幕 接单
site:eleduck.com 翻译 远程
site:eleduck.com 文案 远程
site:v2ex.com 酷工作 翻译
site:douban.com 翻译 接活
site:douban.com 文案 接活
site:douban.com 海报 接活
site:xiaomifeng.work translation
site:xiaomifeng.work copywriting
```

配额说明:以上 query 与用户主技能 query 并发执行,共享 `web_search` ≤30 次总上限。建议选 4-6 条最高频的,不要全打。

## 反爬与法律边界

- 不要用 `requests`/`selenium` 直接打平台,会被封且可能违反 ToS。
- 不要爬取需要登录的内容(招聘方联系方式、简历库)。
- 搜索引擎结果是公开可索引的,做摘要在合规灰区,但不要原样转卖。

## 字段抽取提示(给 LLM)

从 web_search 返回的 `snippet` 中尽可能抽取:

| 字段 | 抽取策略 |
|---|---|
| `title` | 通常是结果标题第一行 |
| `company` | 看"XX公司"、"XX团队"、"XX工作室" |
| `location` | 看"北京/上海/远程" |
| `pay` | 看数字 + 单位(元/时、千/月、k/月、面议) |
| `type` | 看"兼职/全职/远程/外包/项目" |
| `required_skills` | 看 JD 中的工具/语言关键词 |
| `link` | 直接用 `link` 字段 |
| `source_platform` | 从域名反推 |

字段缺失且无法从 snippet 推断 → 丢弃或 `pay_unknown=true`。
