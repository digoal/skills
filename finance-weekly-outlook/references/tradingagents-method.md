# TradingAgents-Inspired Method

This reference adapts ideas from "TradingAgents: Multi-Agents LLM Financial Trading Framework" for a single Codex workflow. Do not claim the report is produced by a live multi-agent system unless actual agents were used.

## Useful Ideas

- Specialize analysis roles so facts are not mixed with trading opinions too early.
- Use bull/bear debate to force the strongest opposing case before making a call.
- Translate research into structured trading decisions: buy, sell, hold, avoid, position size, entry, exit, invalidation.
- Add risk management after the trader decision, not before; risk review should modify sizing and invalidation levels.
- Preserve structured reports rather than long conversation history.

## Internal Review Roles

Use these roles as a checklist:

| Role | Question to answer | Evidence required |
|---|---|---|
| Fundamental analyst | Are earnings, cash flow, margins, balance sheet, valuation, and guidance improving or deteriorating? | filings, earnings releases, consensus revisions, credible data |
| News/policy analyst | What catalyst matters next week, and is it already priced? | official policy, company news, reliable news sources |
| Technical analyst | Does price/volume confirm the thesis? | relative strength, support/resistance, trend, volume, breadth |
| Bull researcher | What is the strongest upside path? | assumptions, catalyst, confirmation signals |
| Bear researcher | What can break the thesis? | falsification signals, crowdedness, downside catalysts |
| Trader | What should be done now? | action, trigger, sizing, stop, take-profit |
| Risk manager | How can this lose money, and how should exposure be capped? | correlation, drawdown, event risk, liquidity |

## Structured Debate Pattern

For each important industry or stock:

1. Bull case: write the strongest evidence-backed positive case.
2. Bear case: write the strongest evidence-backed negative case.
3. Resolution: explain why the final direction wins under the base assumptions.
4. Falsification: name the observable signal that flips the view.
5. Action: convert the view into entry/exit/sizing rules.

## Guardrails

- Debate is not decoration; include only points that can change the decision.
- If bull and bear evidence are balanced, classify as "观察" instead of forcing a trade.
- If the thesis depends on unverified data, downgrade confidence.
- If risk is asymmetric, reduce position size even when direction is favorable.
- If the stock is crowded and the catalyst is widely known, assume "priced in" until market behavior proves otherwise.
