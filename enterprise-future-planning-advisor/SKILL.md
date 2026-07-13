---
name: enterprise-future-planning-advisor
description: 基于用户提供的企业名、企业简介、公司网站、产品信息、财报或访谈材料，搜索当前公开资料并生成企业画像、未来规划与建议书。Use when the user asks for 企业未来规划、公司战略建议书、企业画像、行业/赛道/场景分析、商业机会挖掘、客户付费痛点、产品原型、MVP、团队组建、变现路径、转型增长方案, and wants a source-backed Chinese Markdown report saved under the current project's markdown directory.
---

# Enterprise Future Planning Advisor

## Goal

Write a rigorous Chinese Markdown planning report for a specific company. Start from the company's current reality, compare it with external opportunities and risks, then design feasible future paths, products, MVPs, teams, monetization, and validation steps.

Do not write generic consulting slogans. Build the recommendation from verifiable company facts, current industry evidence, explicit assumptions, and a clear bridge from "where the company is" to "where it can go".

## Inputs

Use the user's provided company material as primary context:

- Company name, website, location, founding stage, ownership/listing status.
- Company intro, products/services, target customers, pricing, channels.
- Financial reports, fundraising news, hiring pages, patents, regulatory licenses, media interviews, or internal notes.
- User's specific question, desired planning horizon, risk tolerance, and expected output depth.

If critical information is missing, first search public sources. Ask up to 5 high-impact questions only when public research cannot resolve the gap and the answer would materially change the plan. If the user asks you to proceed, state assumptions and confidence levels.

## Workflow

1. Build the evidence base.
   - Search the web for the company, website, filings, products, leadership, customers, competitors, funding, lawsuits/regulation, hiring, and recent news.
   - Prefer official company pages, annual reports/filings, regulator or government data, reputable industry reports, patents, job posts, customer reviews, and credible media.
   - Record source links, dates, and whether each claim is fact, inference, or assumption.

2. Create the enterprise profile.
   - Analyze internal current state: business fundamentals, product/service portfolio, customer assets, operating efficiency, organization, resources, and core capabilities.
   - Analyze internal future capacity: strategic intent, innovation history, evolution speed, transferable assets, and constraints.
   - Analyze external current state: market structure, profit pool, value chain, customers, competition, substitutes, entrants, macro and policy conditions.
   - Analyze external future trends: technology discontinuities, demographic and social changes, long-term policy anchors, supply-chain shifts, and value-driven demand migration.
   - For the detailed profile checklist, read `references/enterprise-profile-framework.md`.

3. Convert the profile into strategic options.
   - Identify gaps between internal limits and external possibilities.
   - Compare current business low-efficiency zones with external high-profit zones.
   - Test whether current advantages can survive future technology or demand shifts.
   - Produce 2-4 options, then recommend one main path and one backup path.

4. Design the plan.
   - Include industry analysis, track analysis, scenario analysis, and how the company participates.
   - Identify customer-paid pain points, commercial opportunities, target customer segments, demand logic, and willingness to pay.
   - Design product/service prototypes, MVPs, pricing hypothesis, sales channel, operating model, team structure, and milestone metrics.
   - Explain monetization: who pays, why now, how often, through which channel, and what unit economics must become true.

5. Save the final report.
   - Create `markdown/` under the current project if missing.
   - Save as `markdown/enterprise-future-planning-<company>-YYYYMMDD-HHMM.md`.
   - Use Markdown with tables, Mermaid diagrams, and optional inline SVG where useful.

For evidence requirements, read `references/evidence-standards.md`.
For the required report structure, read `references/report-template.md`.

## Output Requirements

The report must include, at minimum:

- Executive summary and final recommendation.
- Source-backed company profile: facts, inferences, assumptions, unknowns.
- Internal diagnosis: business, product, customers, operations, organization, resources, capabilities.
- External diagnosis: industry, track, value chain, profit pool, scenarios, customers, competition, substitutes, entrants, macro/policy.
- Future trend analysis: technology, demographics, social values, policy, supply chain, economic cycle.
- SWOT or equivalent strategic gap map.
- Customer-paid pain points and business opportunities.
- Demand analysis and target customer segmentation.
- Product/service prototype and MVP design.
- Participation mode, monetization path, channel, team and resource plan.
- 30/90/180-day roadmap, metrics, risks, fallback paths.
- Source list with links and publication dates where available.

## Quality Bar

- Use current web evidence for changeable claims. If browsing is unavailable, mark affected sections as unverified and lower confidence.
- State assumptions before conclusions. For major recommendations, include what changes if the key assumption fails.
- Do not infer market opportunity from isolated cases. Use cases only as illustrations unless backed by broader data.
- Do not recommend a new product, transformation, or market entry without a plausible buyer, payment reason, channel, MVP validation method, and stop/continue metric.
- Separate "what is known", "what is inferred", "what is assumed", and "what must be validated".
- Keep diagrams functional: use them to clarify value chain, opportunity map, product workflow, or execution roadmap.
