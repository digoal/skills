---
name: product-feature-tech-implement
description: 基于功能设计文档(由 product-feature-tech-design 产出或等价输入)、源码目录、以及测试所依赖的环境信息(例如 PostgreSQL 插件开发需要的 PG 源码/实例、第三方依赖),编排「开发者 ↔ 评审者 ↔ 测试者」三方隔离的实施循环,直至评审通过、且所有测试(新增 + 已有)通过。三方互不可见,测试者绝对不能看到开发者写的代码。完成后输出 markdown 总结报告到当前项目的 `markdown/` 目录。适用于:实施功能设计文档、按设计稿开发并自验证、闭环式开发流程、PostgreSQL 插件/扩展开发、需要 build + 部署 + 跑测的工程项目、TDD 式实施循环。
---

# Product Feature Tech Implement

## 核心约束(决定一切)

1. **测试者看不到代码**。这是与 `product-feature-tech-design` 一脉相承的隔离原则 — 测试者只读设计文档,绝不能读开发者写的代码、commit message 中的代码 diff、或评审意见里贴的代码片段。
2. **循环 A 必须有终止条件**。评审通过才能退出循环 A;测试通过(且已有测试不退化)才能结束任务。
3. **三方各持独立 prompt**。下方 references 里固化的 subagent prompt 是隔离的物理边界,**不要在主对话里临场改写**。

## 输入

| 输入 | 必填 | 用途 |
|---|---|---|
| 功能设计文档路径 | 是 | 所有角色的唯一共同依据 |
| 源码目录路径 | 是 | 开发者写入、评审者读取、测试者不读 |
| 已有测试目录 | 是 | 测试者运行回归 |
| 测试环境信息 | 否(按需) | 例如:PG 源码路径、PG 实例初始化命令、插件加载方式、构建系统(Make/CMake/Cargo/...) |
| 增量代码范围 | 是(从第 2 轮起) | 仅给评审者,标识本次新增/修改的文件 |
| 上轮评审意见 | 否(从第 2 轮起) | 给开发者修复用 |
| 上轮测试报告 | 否(从第 2 轮起) | 给开发者修复用 |

如果输入不全,先停下来问用户补齐,不要凭空白开始。

## 角色契约

### 角色 1:开发者(Subagent 1)

| 项 | 约束 |
|---|---|
| 输入 | 设计文档 + 上轮 review 意见(若有) + 上轮测试报告(若有) + 源码目录 |
| 输出 | 增量代码(diff 或文件列表)+ 开发者自检说明 |
| 可以看 | 设计文档全部、源码目录全部、已有测试目录的**文件名**(不是内容)、build/部署/运行日志 |
| 不可以看 | 测试者写的测试代码 |
| 隔离实现 | 由 `references/developer-prompt.md` 物理屏蔽 |

### 角色 2:评审者(Subagent 2)

| 项 | 约束 |
|---|---|
| 输入 | 设计文档 + 增量代码(本轮新增/修改的文件)+ 上一轮 review 报告(若有) |
| 输出 | review 报告(通过 / 不通过 + 问题清单 + 严重度) |
| 可以看 | 设计文档全部、增量代码 |
| 不可以看 | 测试代码、上轮测试报告(避免被「能跑通」污染 review 视角) |
| 通过条件 | 所有 P0 问题已修复,无新增 P0/P1 问题 |

### 角色 3:测试者(Subagent 3)

| 项 | 约束 |
|---|---|
| 输入 | **仅**功能设计文档 + 已有测试目录路径(运行用,不是阅读用) + 测试环境信息 |
| 输出 | 测试报告(新增测试用例 + 执行结果 + 已有测试执行结果) |
| 可以看 | 设计文档全部、运行 build/部署/跑测的命令、命令输出 |
| **绝对不可以看** | 开发者写的源码、commit message 中的 diff、review 报告里贴的代码片段 |
| 隔离实现 | 由 `references/tester-prompt.md` 强红线 |

## 编排流程

```
[读取输入]
   ↓
loop A:
   ① 启动 subagent 1(开发者)
        - 首轮:基于设计文档实现
        - 后续轮:基于设计文档 + review 意见 + 测试报告修复
   ② 启动 subagent 2(评审者)
        - 基于设计文档 + 本轮增量代码 review
   ③ review 通过?
        - 否 → 回到 loop A 开始(开发者按 review 修)
        - 是 → 退出 loop A
   ④ 启动 subagent 3(测试者)
        - 基于设计文档写新增测试 + 跑全量测试
   ⑤ 测试通过?
        - 否 → 回到 loop A 开始(开发者按 review + 测试报告修)
        - 是 → 退出整体流程
   ⑥ 关闭三个 subagent
   ⑦ 生成总结报告
```

### 循环退出判定

**loop A 退出**(进入测试):
- review 报告明确写 `verdict: pass`
- 没有任何 P0/P1 残留

**整体流程退出**:
- review pass **且** 测试报告 `verdict: pass`
- 测试报告必须包含:新增测试用例数、通过/失败/跳过统计、已有测试全部通过(无退化)
- 性能/安全/兼容性的"必测项"覆盖

**防死循环**:
- 同一 review 意见反复未修复 3 轮 → 暂停,询问用户是否调整设计文档
- 同一测试用例反复失败 3 轮 → 暂停,询问用户是设计问题还是实现问题

## subagent 启动规范

每次启动 subagent 时,**必须**:
1. 加载对应的 references 模板作为 subagent 的角色契约
2. 在 prompt 开头**显式**告知 subagent:
   - 它是什么角色
   - 它能读什么、不能读什么
   - 它的输入路径(设计文档、上轮报告等)
   - 它的输出格式
3. 显式约束:不要让 subagent 之间互看对方的产出
4. **subagent 完成后,只把它的最终输出带回主对话**,不要把它的内部 reasoning 全量带回

详细 prompt 见:
- `references/developer-prompt.md`
- `references/reviewer-prompt.md`
- `references/tester-prompt.md`

## 报告文件位置

| 报告 | 路径 | 说明 |
|---|---|---|
| Review 报告 | `markdown/<topic>-review-<round>-<YYYYMMDD>.md` | 每轮 1 份 |
| 测试报告 | `markdown/<topic>-test-<round>-<YYYYMMDD>.md` | 每轮 1 份 |
| 总结报告 | `markdown/<topic>-implement-summary-<YYYYMMDD>.md` | 最终 1 份 |

`<topic>` 与功能设计文档保持一致。

## 总结报告(见 `references/summary-template.md`)

至少包含:
- 任务概览(设计文档 + 源码目录 + 测试环境)
- 实施时间线(每轮做了什么、review 结论、测试结论)
- 最终增量代码清单(文件级)
- 最终测试覆盖(新增用例数、已有用例回归结果)
- 遗留风险与后续建议
- 关键决策记录(为什么这么做)

## 质检清单(交付前自检)

- [ ] 测试者 subagent 启动时 prompt 中显式写了"绝对不能看代码目录"
- [ ] 每轮 review 报告有明确的 verdict(pass / fail + 原因)
- [ ] 每轮测试报告有明确的 verdict(pass / fail + 失败用例)
- [ ] 已有测试无退化(失败数 0 或与基线一致)
- [ ] 总结报告保存到 `markdown/` 目录
- [ ] 三个 subagent 已被关闭(没有遗留子任务)
- [ ] 流程中**没有**把开发者代码泄漏给测试者
- [ ] 防死循环保护(同问题 3 轮未解决)未触发 / 已与用户确认

## 参考资料

- `references/developer-prompt.md` — 开发者 subagent 角色契约
- `references/reviewer-prompt.md` — 评审者 subagent 角色契约
- `references/tester-prompt.md` — 测试者 subagent 角色契约(强隔离)
- `references/summary-template.md` — 总结报告模板

## 上下游 skill

- **上游**:`product-feature-tech-design` — 输入是它的产物(功能设计文档)
- **本 skill** — 实施 + review + test 闭环
- **下游**:无需,本 skill 是交付终点
