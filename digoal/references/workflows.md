# Workflows

Use these repeatable workflows to produce stable, verifiable output.

## Problem Classification Matrix

Classify first, then load only the relevant workflow. If a request spans multiple types, choose the primary deliverable and mention secondary constraints.

| Problem type | Typical triggers | Required inputs | Evidence path | Thinking frame | Output shape | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| Database technical answer | "怎么做", "为什么", feature usage, SQL behavior, PG/PolarDB/DuckDB mechanism | DB/version if version-sensitive, scenario, workload, data shape, expected result | Blog precedent plus official docs/source when behavior depends on current technology | Scenario -> mechanism -> practical path -> risks -> verification | Conclusion, rationale, SQL/commands, risks, acceptance criteria | Claims are tied to sources or marked as assumptions; operational advice includes a check |
| Troubleshooting/performance | slow query, lock, bloat, OOM, replication lag, CPU/IO spike, timeout | Symptom, version, deployment, timeframe, top SQL, metrics/logs when available | Runtime facts first, then PG views/logs, blog cases, official docs | Symptom -> observability -> likely causes -> minimal reversible test -> durable fix | Ordered checklist, SQL/commands, risk, rollback, before/after metrics | Steps are ordered by probability, reversibility, and blast radius |
| Architecture/selection | choose PG vs X, HA/DR design, migration, product architecture | Business goal, SLA, data volume, read/write shape, RPO/RTO, budget/team constraints | Official capability boundaries, benchmark methodology, blog cases | Value to protect -> hard constraints -> options -> tradeoffs -> failure modes | Comparison table, recommendation, assumptions, validation plan | Recommendation changes if stated assumptions change |
| Article/project interpretation | 公众号, 爆款, technical explainer, open-source project article, course note | Target reader, thesis or topic, article type, source target | Primary sources first, DeepWiki for GitHub repos when available, secondary interpretations, blog for style/precedent | Hook -> pain -> sharp thesis -> first principles -> evidence -> hands-on -> caveat | Article-ready Markdown with references plus Mermaid/SVG visuals at key points | Core judgments and diagrams have support; unsupported claims are softened or removed |
| Source/commit/new-feature interpretation | commit, patch, source code, release note, new PG feature | Exact repo/commit/version/doc link when available, target reader | Code, diff, tests, docs, release notes, mailing list; blog only as precedent | What changed -> why it matters -> mechanism -> user impact -> verification | Feature/commit explanation, code path, examples, risks | Every factual claim maps to code/docs/tests or is marked inference |
| Learning path/course | 学习路线, training, curriculum, "how to learn" | Learner role, current level, target capability, time budget | repo-map series posts, official docs, exercises/labs | Target capability -> prerequisite gaps -> staged path -> practice -> acceptance | Roadmap, materials, exercises, milestones | Each stage has a concrete output or test |
| Skill/digital employee design | write/improve skill, digital employee, SOP, stable AI workflow | Task examples, trigger, desired artifact, tools/source systems, validation standard | skill-creator guidance, AI skill blog posts, existing skill files | Trigger -> input contract -> decision path -> tools -> validation -> fallback -> output -> boundary | Skill design or patch plan; optionally edited skill files | Skill is valid, concise, reusable, and has forward-test prompts when complex |
| Community/product/ecosystem strategy | open-source growth, community, developer adoption, product promotion | Product/project, target users, adoption barrier, goals, metrics | User pain, product facts, ecosystem data, blog/community precedent | User pain -> adoption barrier -> content system -> community flywheel -> metrics | Strategy, action plan, metrics, risks | Actions have owners/metrics and do not depend on vague slogans |

Fallback rules:

- If required inputs are missing but not blocking, state assumptions and provide a first-pass path.
- If required inputs are blocking, ask the smallest useful question instead of guessing.
- If evidence is unavailable, say what was checked and narrow the claim.
- If a task asks for a current external fact, verify current sources before relying on blog memory.
- If the selected workflow does not fit after evidence gathering, reclassify once and state why.

## PostgreSQL/PolarDB Technical Answer

1. Restate the scenario: workload type, data size, concurrency, SLA, deployment shape, and current symptom.
2. Search blog evidence by category and keyword.
3. Explain the mechanism before the fix: storage, index, optimizer, MVCC, lock, WAL, replication, memory, IO, or network.
4. Provide the practical path:
   - immediate mitigation
   - root-cause confirmation
   - durable design or configuration change
   - regression guard
5. Include SQL/commands where possible.
6. State assumptions and when the recommendation fails.

Output skeleton:

```markdown
## 结论
## 判断依据
## 排查/实施步骤
## SQL或命令
## 风险与回滚
## 验收标准
## 参考
```

## Performance Diagnosis

Order checks by probability and reversibility:

1. Confirm symptom: latency, QPS/TPS, CPU, IO, locks, bloat, checkpoint, WAL, autovacuum, network, connection count.
2. Find top SQL: `pg_stat_statements`, slow log, `auto_explain`, `EXPLAIN (ANALYZE, BUFFERS)`.
3. Check plan mismatch: wrong row estimate, missing/unused index, correlation, stale stats, parameter sensitivity.
4. Check memory and temp files: `work_mem`, hash/sort spill, parallelism, connection fan-out.
5. Check MVCC maintenance: dead tuples, autovacuum lag, freeze, bloat.
6. Check contention: row locks, relation locks, LWLock, IO queue, WAL sync.
7. Convert diagnosis into a minimal change and verify with before/after metrics.

Never prescribe a parameter blindly; bind it to workload, memory budget, and failure mode.

If runtime facts are missing, split the answer:

1. "需要补充的信息": list only facts that change the diagnosis.
2. "先做的低风险检查": provide read-only SQL/commands.
3. "暂不建议直接修改": name parameters or schema changes that would be unsafe without evidence.

## Evidence Pack

Before giving a non-trivial answer, collect enough evidence to avoid overfitting to one post:

1. Search the exact keyword and at least one synonym, for example `pgvector`, `向量`, `HNSW`.
2. Prefer a series summary or category index when the user asks for a learning path or broad overview.
3. Prefer the newest dated posts for recent feature previews, but verify current external status with official sources when the answer depends on today's release state.
4. For code or commit claims, inspect the actual code/diff in addition to blog posts.
5. Cite repository-relative paths in the final answer.

Use JSON output when the search result is passed into another tool:

```bash
python3 skills/digoal/scripts/search_blog.py "pgvector" --json --limit 5
```

## Architecture and Selection

Start from first principles:

- What value must the database protect or accelerate?
- What is the dominant access pattern: OLTP, OLAP, HTAP, search, vector, graph, GIS, time-series, stream?
- What are scale dimensions: data volume, write rate, read rate, retention, tenant count, region count?
- What are hard constraints: RPO/RTO, consistency, compliance, cost, team skill, ecosystem?
- What failure mode is unacceptable?

Compare options with a table: `方案`, `适合场景`, `代价`, `风险`, `验证方法`.

## Article Writing in digoal Style

Use when asked to create public-account articles, project interpretations, course notes, or technical explainers.

Before drafting:

1. Think through the writing framework first: target reader, core thesis, article type, section order, expected evidence, practical path, caveats, and which key points deserve a Mermaid or SVG visual.
2. Search source material after the framework is clear.
3. Prefer primary sources: official docs, release notes, commits, source code, tests, papers, standards, benchmark data, or vendor engineering notes.
4. For GitHub open-source projects, use DeepWiki MCP when available to read the repo wiki/structure and ask repo-grounded questions; treat it as a fast project-understanding layer, then verify important claims against upstream docs, source code, commits, or tests.
5. Use internet articles already interpreted by others only after primary sources, mainly to discover angles, controversies, and common misunderstandings.
6. Use existing local blog articles last for precedent, style, related cases, and continuity with digoal's knowledge base.
7. Digest the collected context before writing: separate verified facts, reasonable inferences, uncertain claims, reusable examples, and claims that must be removed or softened.
8. Start drafting only when the context can support the thesis, mechanism explanation, hands-on method, effect verification, boundary conditions, and planned diagrams.

Hard gate: for a technical article about an external technology or open-source project, a context pack that only contains local blog search results is insufficient. Stop and gather upstream primary sources first. If upstream access, internet search, or DeepWiki MCP is unavailable, report the limitation and ask whether the user wants a blog-only draft with explicit caveats.

Authority order for source material:

1. Upstream source code, commit diff, tests, release notes, official docs, standards/specs, or peer-reviewed paper.
2. Vendor engineering blog or maintainer-authored design note.
3. DeepWiki MCP for GitHub repos, used for repo navigation, architecture understanding, and question answering.
4. Reproducible benchmark, lab, SQL, command output, or test result.
5. Reputable third-party technical articles, used as secondary interpretation only.
6. Existing local blog articles, used for precedent, style, historical continuity, and related cases.

Most authoritative sites depend on the topic:

- PostgreSQL: `postgresql.org` docs, `git.postgresql.org` or upstream GitHub mirror commits, mailing list archives, source code, and tests.
- DuckDB: `duckdb.org` docs/release notes, `github.com/duckdb/duckdb`, source code, tests, and extension docs.
- Lance: official Lance docs/site, `github.com/lancedb/lance`, source code, tests, issues/PRs, release notes, and related Apache Arrow/DataFusion docs when the claim depends on those layers.
- Open-source projects in general: upstream project docs, GitHub/GitLab repo, maintainer release notes, code, tests, design docs, issues, PRs, and official benchmarks.
- Cloud/vendor products: official docs, release notes, SLA/pricing pages, product blogs by the vendor engineering team, and public benchmark methodology.
- Academic algorithms or systems: original paper, authors' artifact/repo, conference proceedings, and reproducibility reports.

Drafting steps:

1. Pick a sharp title that names the consequence, not just the feature.
2. Open with a concrete pain point, surprising observation, or 药引子 that activates reader demand.
3. State the core judgment early, preferably as a falsifiable thesis.
4. Explain from mechanism or first principles.
5. Add evidence: official docs, code, benchmark, case, before/after comparison, or blog precedent.
6. Pair theory with practice: mechanism plus SQL/commands/config/checklist.
7. Explain the effect: what improves, through which path, and how to measure it.
8. Add caveats: what assumptions must hold and what happens if they fail.
9. Insert visuals where they reduce cognitive load: Mermaid for flows, dependency graphs, causal chains, state transitions, tradeoff matrices, or validation paths; compact inline SVG only when Mermaid cannot express the shape clearly.
10. Close with a short takeaway, action suggestion, or "你怎么看" interaction when publishing style is requested.

Visual placement rules:

- Add 2-4 visuals for a full public-account or project interpretation article unless the article is very short or the user forbids diagrams.
- Place diagrams immediately after the paragraph that introduces the concept they clarify, not in a detached appendix.
- Prefer Mermaid `flowchart`, `sequenceDiagram`, `stateDiagram-v2`, `quadrantChart`, or `journey` blocks for mechanisms, architecture paths, adoption flywheels, and verification loops.
- Use SVG sparingly for simple 2D conceptual maps, scorecards, or layered system sketches that would be awkward in Mermaid. Keep SVG self-contained, readable in Markdown, and under roughly 80 lines.
- Give every diagram a one-sentence lead-in and a one-sentence takeaway; do not let the graphic replace evidence.
- Do not invent entities, metrics, or causal arrows just to make a diagram look complete. If a visual edge is an inference, label it as an inference in nearby text.
- Keep labels short and Chinese-first; use established English terms only for technical names such as `WAL`, `MVCC`, `RAG`, `HNSW`, or `EXPLAIN`.

Common visual slots:

- After 药引子 or 场景痛点: reader pain -> hidden constraint -> consequence.
- After 反常识判断 or 第一性原理: old path vs new path, or hard constraint -> mechanism -> measurable result.
- In 原理介绍: component/data/control-flow diagram.
- In 理论加实操: implementation or verification checklist flow.
- In 边界条件: premise -> failure mode -> alternative recommendation.

Sections for PG commit/new feature interpretation:

```markdown
# 标题
## 摘要
关键词:
背景痛点:
核心价值:
## 原理介绍
## 应用场景及最佳实践
## 风险、限制与版本注意
## 小结和思考
## 参考
```

Article type templates:

### PG Commit or New Feature Interpretation

```markdown
# 标题
## 摘要
关键词:
背景痛点:
核心价值:
## 药引子: 为什么这个变化值得看
## 过去怎么做, 痛在哪里
## 这次改了什么
## 第一性原理: 为什么这样设计
## 原理介绍: 结合代码/commit讲清楚机制
## 应用场景及最佳实践
## 怎么验证: SQL、命令、指标或测试
## 风险、限制与版本注意
## 小结和思考
## 参考
```

### Product or Architecture Selection

```markdown
# 标题
## 结论先行
## 药引子: 为什么现在必须重新判断
## 场景和约束
## 错误选型方式
## 第一性原理: 真正要优化的底层变量
## 选择标准
## 方案对比
## 落地路径
## 风险边界和替代方案
## 推荐动作
## 参考
```

### 德说 or Strategic Analysis

```markdown
# 标题
## 现象
## 反常识判断
## 底层变量: 供需、成本、效率、信任、生态或飞轮
## 为什么会这样
## 案例或证据托底
## 对个人/团队/企业意味着什么
## 前提条件
## 如果前提崩塌, 结论怎么换
## 行动建议
```

Pre-publish checks:

- Does the article turn a single case into a universal conclusion?
- Does every core judgment have a source, case, code path, benchmark, or reproducible check?
- Does it explain the mechanism behind the claimed effect?
- Do Mermaid/SVG visuals appear at the key information points and match the sourced argument?
- Does it give the reader an operational next step?
- Does it state the premise and the alternative view when the premise fails?
- Does any sentence claim certainty that the evidence cannot support?

Post-draft validation:

1. Extract the article's factual claims: version numbers, feature behavior, API names, SQL syntax, configuration names, performance claims, architecture diagrams, Mermaid/SVG labels and edges, and causal explanations.
2. Check each claim against the highest-authority available source. Use official docs/release notes for documented behavior, source code/commits/tests for implementation behavior, standards/papers for algorithmic claims, and DeepWiki MCP for repo-grounded cross-checking on open-source projects.
3. Run reproducible checks when feasible: SQL examples, CLI commands, unit tests, benchmark snippets, `EXPLAIN`, configuration inspection, or source grep.
4. Mark unsupported claims as inference, soften them, or remove them.
5. Verify terminology consistency: project name, version, extension name, file path, function name, catalog/view name, and metric name.
6. Verify boundaries: when the recommendation works, when it fails, how to rollback, and what metric proves success.
7. Re-read the final article once from the target reader's perspective: DBA, architect, developer, product owner, or learner.

Validation output should be explicit when the user asks for review:

```markdown
## 校验结论
## 已核实的关键事实
## 仍需谨慎的推断
## 修改或弱化的表述
## 参考来源
```

## Source Code or Commit Interpretation

1. Inspect the exact commit, diff, tests, docs, and nearby code.
2. Separate "what changed" from "why it matters".
3. Translate internals for the target reader: DBA, developer, architect, or product manager.
4. Avoid unsupported performance claims unless benchmark or code path proves them.
5. Verify article claims against code before final output.
6. If writing multiple files, keep each topic in an independent context and avoid cross-contamination.

## AI Skill/Digital Employee Distillation

Use the framework from `202603/20260317_03.md`, `202603/20260319_05.md`, and `202603/20260324_06.md`.

For each skill, define:

- Trigger: when should it be used?
- Input contract: what information is required?
- Decision path: how does it choose a workflow?
- Tools: what files, MCPs, CLIs, scripts, or source systems are used?
- Validation: how is correctness checked?
- Fallback: what happens when evidence is missing or tool calls fail?
- Output template: what artifact is produced?
- Responsibility boundary: what the skill must not do.

Strong skill criteria:

- 可验证: output can be checked.
- 可复用: procedure works repeatedly.
- 可规模化: not dependent on one-off genius.
- 可追责: inputs, steps, and boundaries are clear.

Forward-test prompts for this skill type should use realistic user wording and avoid leaking the intended fix. Examples:

- `Use $digoal at /path/to/digoal to diagnose why a PostgreSQL query became slow after data volume doubled.`
- `Use $digoal at /path/to/digoal to write a source-backed article explaining a PostgreSQL commit for DBAs.`
- `Use $digoal at /path/to/digoal to design a skill that turns a repeated database inspection workflow into a reusable AI capability.`

## Community and Ecosystem Strategy

Use digoal's community/product background when asked about open-source growth, database product promotion, or developer ecosystem.

Frame with:

- User pain and adoption barrier.
- Product core value and differentiated scenario.
- Content system: tutorials, labs, cases, benchmarks, migration guides, best practices.
- Community mechanism: contributors, users, partners, training, events, support channels.
- Flywheel: content -> trust -> usage -> feedback -> cases -> ecosystem.
- Metrics: users, deployments, contributors, issues, stars, courses, conversions, enterprise references.

Avoid vanity metrics without tying them to adoption or business value.
