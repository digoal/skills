---
name: future-planning-advisor
description: 根据提问者提供的个人背景、资源、困境、目标、行业处境或访谈信息，生成面向未来的中文规划与建议书。Use when the user asks for 个人规划、职业规划、创业规划、人生规划、未来建议书、赛道选择、转型路径、变现方案、产品原型、MVP、团队组建、商业机会分析, and wants a source-backed Markdown report saved under the current project's markdown directory.
---

# Future Planning Advisor

## Goal

Write a rigorous Chinese Markdown planning report for a specific person. Find the intersection of:

- What the person wants: motivation, values, ideal life, risk preference.
- What the person can do: skills, resources, constraints, energy pattern.
- What the era allows: industry demand, technology diffusion, macro trends, payment willingness.

Do not write generic inspirational advice. Turn the user's background into concrete strategic choices, scenario plans, commercial opportunities, MVPs, and action steps.

## Inputs

Use the user's provided background as primary material. If critical information is missing, ask up to 5 high-impact questions before writing. If the user asks you to proceed without more input, state assumptions clearly and mark confidence levels.

Minimum useful inputs:

- Current role, industry, city/country, age range or career stage.
- Skills, resources, constraints, current pain points.
- Desired lifestyle or goals.
- Risk tolerance, income pressure, family/time constraints.
- Any target industries, interests, or disliked paths.

For detailed interview prompts, read `references/profile-framework.md`.

## Workflow

1. Build the person's profile.
   - Extract facts from the prompt.
   - Separate facts, inferences, assumptions, and unknowns.
   - Summarize internal factors and external positioning.
   - Produce a personal SWOT and 3-version Odyssey plan.

2. Research current external evidence.
   - Browse current web sources when making claims about markets, jobs, salaries, AI substitution, funding, regulation, industry size, or macro trends.
   - Prefer official statistics, government/regulator data, listed-company filings, reputable research institutions, major consulting reports, academic papers, and large recruitment platforms.
   - Avoid relying on isolated anecdotes, single founder stories, viral posts, or unsourced claims.
   - Cite sources with links. Record publication dates when relevant.

3. Convert evidence into strategic options.
   - Analyze industry,赛道, scenarios, customer pain points, willingness to pay, and demand.
   - Explain assumptions behind each claim. If an assumption collapses, show the fallback path.
   - Give 2-4 feasible options, then recommend one main path and one backup path.

4. Design execution.
   - Define how the person participates: role, entry point, leverage, partners, first customers.
   - Design monetization: pricing, sales channel, delivery model, unit economics logic.
   - Provide product/service prototype and MVP scope.
   - Propose team composition only when needed; keep solo or part-time starts when that is more realistic.
   - Give 30/90/180-day actions and measurable success criteria.

5. Save the final report.
   - Create `markdown/` under the current project if missing.
   - Save as `markdown/future-planning-建议书-YYYYMMDD-HHMM.md` or a more specific filename when the person/project has a clear name.
   - Use Markdown with Mermaid diagrams and optional inline SVG where useful.

For the required report structure, read `references/report-template.md`.
For evidence and reasoning standards, read `references/evidence-standards.md`.

## Output Requirements

The report must include, at minimum:

- Executive summary and final recommendation.
- User profile: current abilities/resources, motivations, values, constraints, blind spots.
- External environment: industry analysis,赛道 analysis, scenario analysis, technology/AI impact, macro trend fit.
- SWOT and Odyssey plan.
- Customer-paid pain points and business opportunities.
- Demand analysis and target customer segmentation.
- Product/service prototype and MVP design.
- How the person participates and monetizes.
- Team, resources, milestones, risks, fallback paths.
- Source list with links.

Use clear titles, tables, Mermaid diagrams, and concise visual summaries. Use diagrams to clarify structure, not as decoration.

## Quality Bar

- State assumptions before conclusions.
- Distinguish "high confidence", "medium confidence", and "needs validation".
- Do not overfit to the person's current job; include adjacent paths when the evidence supports them.
- Do not promise certainty. Planning is a portfolio of bets under constraints.
- Do not present a path as viable unless it has a plausible customer, payment reason, channel, and MVP validation method.
- Keep recommendations specific enough to execute: who to contact, what to build, what to test, what metric decides continuation.
