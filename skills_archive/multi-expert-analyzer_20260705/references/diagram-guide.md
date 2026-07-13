# 图示规范

专家产稿时如何选图、用图。SVG / Mermaid / ASCII 三选一。

---

## 选型决策树

```
Q1: 这个图是否强烈依赖视觉冲击、配色、几何形状？
    ├─ 是 → SVG
    └─ 否 → Q2

Q2: 这个图是流程、时序、状态、关系、思维导图？
    ├─ 是 → Mermaid
    └─ 否 → Q3

Q3: 这个图本质是表格、层级、并排对比？
    ├─ 是 → ASCII
    └─ 否 → 优先 ASCII（最简单稳定）
```

---

## 1. Mermaid（首选）

直接嵌 markdown，用 `\`\`\`mermaid` 代码块。

### 流程图
\`\`\`mermaid
flowchart TD
    A[用户提出问题] --> B{领域识别}
    B -->|单领域| C[派 1 个专家]
    B -->|多领域| D[并行派 N 个专家]
    C --> E[综合成文]
    D --> E
\`\`\`

### 时序图
\`\`\`mermaid
sequenceDiagram
    participant U as 用户
    participant M as 主控 agent
    participant E1 as 专家 1
    participant E2 as 专家 2
    U->>M: 抛出问题
    M->>M: 领域识别
    par 并行
        M->>E1: 派稿
        M->>E2: 派稿
    end
    M->>M: 事实核查 + 红队
    M->>U: 输出综合文章
\`\`\`

### 状态机
\`\`\`mermaid
stateDiagram-v2
    [*] --> 待派稿
    待派稿 --> 产稿中: 派活
    产稿中 --> 自我验证: 完成初稿
    自我验证 --> 产稿中: 不通过
    自我验证 --> 已落盘: 通过
    已落盘 --> [*]
\`\`\`

### 思维导图 / 概念图
\`\`\`mermaid
mindmap
  root((棘手问题))
    显性问题
      时间窗口
      地域边界
    隐含前提
      文化背景
      经济周期
    关键变量
      趋势 X
      反趋势 Y
\`\`\`

### 关系图（ER / 影响关系）
\`\`\`mermaid
erDiagram
    问题 ||--o{ 领域 : "拆解为"
    领域 ||--|| 专家 : "对应"
    专家 ||--o{ 草稿 : "产出"
    草稿 ||--o| 综合文章 : "汇成"
\`\`\`

---

## 2. ASCII Text（最稳）

适合表格、层级、对比、机制说明。

### 表格
\`\`\`
+-----------------+-------------------+-------------------+
| 维度            | 专家 A 的观点     | 专家 B 的观点     |
+-----------------+-------------------+-------------------+
| 时间窗口        | 短期（1 年内）    | 中期（3~5 年）    |
| 关键变量        | 政策             | 人口结构          |
| 失败条件        | 政策反复         | 人口拐点提前      |
+-----------------+-------------------+-------------------+
\`\`\`

### 决策树
\`\`\`
                    你是不是专家？
                       │
              ┌────────┴────────┐
             是                 否
              │                  │
        你能查权威源吗？      你的目标受众是谁？
              │                  │
       ┌──────┴──────┐    ┌─────┴─────┐
      能            不能  小白         同行
       │             │     │            │
   直接给数据     重新搜证 用类比解释   用术语
\`\`\`

### 机制图
\`\`\`
价格 ──→ 销量 ──→ 利润
  │                │
  └───── 反馈 ─────┘

需求 ↑ ──→ 价格 ↑ ──→ 供给 ↑ ──→ 价格 ↓ ──→ 需求 ↓
\`\`\`

---

## 3. SVG（强视觉时才用）

**必须输出为单独 `.svg` 文件**，命名规则：

```
{question-slug}/expert-{N}-{领域简写}-fig-{K}.svg
```

例如：`ai-replace-programmers/expert-1-ai-engineer-fig-1.svg`

在 markdown 中用相对路径引用：

```markdown
![AI 取代程序员的风险地图](./expert-1-ai-engineer-fig-1.svg)
```

### SVG 模板（带 caption 风格）

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 480" font-family="sans-serif">
  <rect width="800" height="480" fill="#fafafa"/>
  <text x="400" y="40" text-anchor="middle" font-size="22" fill="#222">标题</text>
  <!-- 主体 -->
  <g transform="translate(50, 80)">
    <circle cx="100" cy="100" r="60" fill="#4f8ef7" opacity="0.85"/>
    <text x="100" y="105" text-anchor="middle" fill="white" font-size="16">要素 A</text>
  </g>
  <!-- 箭头 -->
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#666"/>
    </marker>
  </defs>
  <line x1="170" y1="180" x2="280" y2="180" stroke="#666" stroke-width="2" marker-end="url(#arrow)"/>
  <g transform="translate(290, 80)">
    <circle cx="100" cy="100" r="60" fill="#f7a14f" opacity="0.85"/>
    <text x="100" y="105" text-anchor="middle" fill="white" font-size="16">要素 B</text>
  </g>
  <text x="400" y="450" text-anchor="middle" font-size="12" fill="#888">图源：multi-expert-analyzer</text>
</svg>
```

### SVG 设计要点

- **简洁**：单色或双色调，避免花哨渐变；专业感优先
- **可读**：字号 ≥ 12，文字用深色背景浅色字或反之
- **caption**：底部加一行小字说明（"图 X：XXX"，或"图源：XXX"）
- **viewBox 留余量**：上下左右各留 30~40px
- **复用图库**：复杂图（漏斗、桑基、雷达、热力）可参考 `d3`/`observable` 经典模板

---

## 引用方式统一

- Mermaid：直接 markdown 代码块
- ASCII：直接 markdown 代码块
- SVG：单独文件 + `![说明](./path.svg)`

> **不要把 svg 内容直接粘到 markdown 里** —— 那会让读者没法单独查看/复制。