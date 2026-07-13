# Article Structure

Use this structure for open-source project analysis articles. Keep headings natural; do not mechanically expose every checklist item if a combined section reads better.

## Required Flow

1. Title
   - Name the consequence or strategic value, not just the product name.
   - Example: `XXX：把 <old pain> 推进到 <new capability>`.

2. Opening thesis
   - Start from a concrete production trigger.
   - State one clear thesis early.
   - Include the preconditions under which the thesis is valid.
   - State the alternative thesis if those preconditions collapse.
   - Use this compact logic when helpful: `观点 -> 成立前提 -> 证据 -> 前提崩塌后的替代观点`.

3. Background
   - Explain why this problem matters now.
   - Include ecosystem context from authoritative sources when available.
   - Avoid generic history unless it changes the reader's decision.

4. Scenario
   - Name the user role: DBA, platform engineer, developer, security engineer, architect, maintainer.
   - Name the production situation: outage, migration, compliance, performance bottleneck, cost pressure, developer workflow, AI workload, etc.

5. Pain points
   - Identify root constraints: resource, coordination, observability, security, cost, compatibility, or adoption constraints.
   - For every pain point, explain the operational cost of ignoring it.

6. Traditional solutions and their problems
   - Compare established alternatives.
   - Be sharp but fair: state when traditional solutions are still correct.
   - Show failure modes, not slogans.

7. Product solution
   - Explain what the project does in one paragraph.
   - Map product capabilities directly to the pain points.

8. Principles and architecture
   - Use README + DeepWiki evidence.
   - Include at least one Mermaid architecture diagram.
   - Explain data flow, control flow, storage model, extension points, and operational boundaries where relevant.

9. Effect comparison
   - Use before/after table.
   - Include measurable metrics only when sourced.
   - If no benchmark exists, use qualitative operational comparison and mark it as inference.

10. Competitor comparison
   - Pick competitors that solve the same user problem.
   - Compare on mechanism, deployment cost, performance/cost, ecosystem fit, operational risk, and lock-in.
   - Cite competitor docs or official pages.

11. Usage scenarios
   - Give 3-6 concrete scenarios.
   - For each scenario: symptom, why this project helps, query/command/config, expected signal, caveat.

12. Best practices
   - Include deployment, security, observability, upgrade, rollback, and team-process advice where relevant.

13. Hands-on
   - Commands must come from README/docs or be clearly marked as adapted examples.
   - Include install, configure, first run, verification, troubleshooting, cleanup/rollback where possible.

14. Risks and boundaries
   - State when not to use the project.
   - State assumptions that can invalidate the thesis.
   - For each invalidated assumption, name the alternative viewpoint, product class, or traditional solution that becomes more reasonable.
   - Include operational hazards and missing evidence.

15. Conclusion
   - Return to the thesis.
   - Restate the conditional nature of the recommendation: when to adopt, when to reject, and what to choose instead.
   - Give concrete next actions for the target reader.

## Diagram Rules

Insert Mermaid or SVG diagrams in core sections:

- Background/problem map: flowchart or mindmap.
- Traditional vs new solution: flowchart or sequenceDiagram.
- Architecture: graph/flowchart.
- Data flow: sequenceDiagram.
- Competitor landscape: quadrant or table plus Mermaid when useful.
- Best-practice workflow: flowchart.

Prefer concise diagrams with 5-10 nodes. Avoid decorative diagrams that repeat nearby prose without adding structure.

## Evidence Style

For each core claim, include one of:

- Direct README fact.
- DeepWiki architecture finding.
- Official documentation.
- Release note.
- Benchmark report.
- Research paper.
- Reproducible command or SQL.
- Credible public case study.

Mark unsupported but useful reasoning as:

```text
我的推断是：...
成立前提是：...
如果前提不成立：...
```

## Assumption Collapse Pattern

Use this pattern whenever the article makes a strong recommendation:

```text
我的观点：<project/product is valuable for X>
成立前提：<workload/user/scenario/security/cost/scale assumptions>
支撑证据：<README/DeepWiki/official docs/benchmarks/cases>
如果前提崩塌：<switch to competitor/traditional solution/do not adopt/reframe the product as research-only>
```

Examples:

- If a database observability project only helps Linux/container workloads, say that non-Linux or managed-service users should prefer cloud-native monitoring, logs, or SQL-only extensions.
- If a model project is validated only on benchmark data, say that production trading or medical/legal/financial decisions require independent validation and a fallback to established workflows.
- If a security project assumes trusted superusers, say that hostile-admin threat models require external KMS, application-side encryption, HSM, or architecture-level isolation.
