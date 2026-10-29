# First four milestones: completion checklist

Milestones 1 and the agreed Python version of 2 pass local acceptance. Milestone 4's
implementation now passes its live synthetic diagnostic, but independent review
remains outstanding. Milestone 3 is blocked by concrete source-access gaps.
**The first four are not all fully signed off.**

| Milestone | Evidence now available | Remaining gate |
|---|---|---|
| 1: foundation | API boot/persistence, migrations/drift and regression checks; hosted CI passed for `cdc2aad` | Verify hosted CI for this follow-up commit after push. |
| 2: Python strategies | Three long-only causal strategies; nonzero synthetic train/holdout trades and byte-identical reports | Local acceptance passed. Real profitability is a separate Milestone 6 requirement. |
| 3: data | Real AAPL candles/news/BLS events, company earnings, splits/dividends; successful real split/volume audit; scoped target/purpose/window feed health; fail-closed replay/stale/correction/date-precision checks | Real spot-gold history and FOMC coverage require source access. Verify complete historical/action/session availability and independent source credibility. |
| 4: intelligence/decisions | Gemini v3: 12/12 live synthetic diagnostic cases valid and label-correct; one real-news durable API generation/replay; strict evidence contracts, uncertainty/injection and deterministic gate tests | Independently reviewed representative real-news/adversarial holdout and source-quality sign-off. The tuned synthetic diagnostic is not independent accuracy evidence. |

## What the latest completion pass fixed

- Versioned `news-classification-v3` adds explicit conservative uncertainty and
  instruction-attack rules; v1/v2 history and failed v2 runs remain unchanged.
- Default Gemini HTTP inactivity timeout is now 60 seconds (configurable 0.1–120),
  reflecting observed live latency. Ambiguous read/delivery failures still never
  trigger automatic generation retries. Collector result files retain durations.
- Read-only company earnings use stable fiscal-period identity and explicitly
  date-only New York timestamps. Restriction windows include the whole date,
  preserving DST and avoiding invented release times.
- Corporate-action acquisition records observed-time provenance. Raw equity data
  is available only for audits. Declared split-adjustment rounding is bounded to
  half a quantum of at most one cent and checked only on adjusted bars; unchanged
  bars and volume retain strict checks. The original failed strict audit is retained.
- `0005_feed_coverage` records provider/target/asset/purpose/window metadata in the
  same transaction as successful imports. One company's poll cannot refresh another
  company, earnings cannot substitute for macro coverage, and replay cannot refresh
  receipt time or recreate lost coverage. Legacy unscoped facts do not satisfy scoped
  gates. Date offsets normalize to UTC before SQL storage.
- New protected `/api/v1/data/coverage` exposes these checks. Decisions use scoped
  feed evidence, include the selected stock earnings feed, and consider all known
  calendar restrictions. Source verification/ownership/compliance/risk authorities
  are still unavailable, so entry authorization remains false.

See [precise remaining requirements](completion-requirements.md),
[provider commands](data-providers.md) and [model evaluation](model-evaluation.md).
No environment draft edits/publication occurred during this pass. A passing
software/diagnostic check is not Shariah approval or permission to trade.
