# 个人特征输入 Schema

## 字段定义

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `skills` | `string[]` | ✅ | 技能关键词,大小写不敏感 |
| `location` | `string` | ✅ | 期望工作地点,如"杭州"、"北京"、"深圳" |
| `available_hours_per_week` | `int` | ✅ | 每周可投入小时数 |
| `min_hourly_rate` | `int` | ✅ | 时薪下限(元/小时),低于此值的会被 `meets_salary_floor=false` 标记 |
| `preferred_types` | `string[]` | ✅ | 工作形式偏好,可选 `remote` / `part_time` / `full_time` / `freelance` / `contract` / `project` |
| `max_commute_minutes` | `int` | ⛔ | 最大通勤分钟数,仅对非远程岗位生效 |
| `avoid_keywords` | `string[]` | ⛔ | 黑名单关键词,出现在标题或描述中直接降权到底部 |
| `language` | `string[]` | ⛔ | 语言能力,如 `["中文", "英文"]` |
| `experience_years` | `int` | ⛔ | 工作年限,JD 要求超过此值会扣分 |
| `industries` | `string[]` | ⛔ | 偏好行业,如 `["互联网", "金融", "教育"]` |

## 最小必填示例

```json
{
  "skills": ["Python", "PostgreSQL", "数据工程"],
  "location": "杭州",
  "available_hours_per_week": 20,
  "min_hourly_rate": 150,
  "preferred_types": ["remote", "part_time"]
}
```

## 完整示例

```json
{
  "skills": ["Python", "PostgreSQL", "Airflow", "dbt", "SQL"],
  "location": "杭州",
  "available_hours_per_week": 25,
  "min_hourly_rate": 200,
  "preferred_types": ["remote", "freelance", "contract"],
  "max_commute_minutes": 45,
  "avoid_keywords": ["销售", "地推", "客服", "保险"],
  "language": ["中文", "英文"],
  "experience_years": 8,
  "industries": ["互联网", "金融科技", "SaaS"]
}
```

## 收集方式

若用户未给出关键字段,用 AskUserQuestion 分批收集:

1. 必填四件套:技能 / 地点 / 每周时间 / 时薪下限
2. 工作形式偏好:多选(远程 / 兼职 / 全职 / 项目 / 外包)
3. 可选:黑名单关键词 / 行业 / 经验年限

不要在用户没给时薪下限时瞎猜,默认值会导致打分失真。
