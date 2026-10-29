# Milestones and acceptance tracker

Source: [master blueprint v2](blueprint-v2.md). Python strategy development replaces
mandatory Pine acceptance; Pine remains optional. Status updated 2026-10-29.
Implementation acceptance and independent release sign-off are tracked separately.

| # | Deliverable | Current state | Evidence / remaining acceptance |
|---|---|---|---|
| 1 | Foundation and architecture | Implemented; software acceptance passes | Boot/persistence, credentials, migrations through `0005_feed_coverage`, schema drift, replay and CI checks. Latest local suite: 312 passed. Hosted CI passed for `8afc05d`; check the current commit's run after push. |
| 2 | Three Python strategies; optional Pine | Agreed Python acceptance passes | Long-only causal stock/ETF/gold strategies; nonzero synthetic train/holdout trades, explicit costs, flat reconciliation and byte-identical reports. Pine compilation/parity remains unverified and optional. |
| 3 | Market and news data | Implementation acceptance passes; historical/source sign-off incomplete | Real Alpaca candles/actions, Finnhub news/earnings, BLS and official FOMC ingestion; immutable revisions, point-in-time provenance, scoped freshness, corporate-action and session checks. A full 2025 gold archive audit validates 11 months and rejects October. A continuous full-year history and independently verified gold session schedule/source suitability remain unavailable. |
| 4 | AI intelligence and decisions | Implementation acceptance passes; independent quality sign-off incomplete | Strict schemas/evidence/targets, durable Gemini jobs, event policies and deterministic gates; v5 passes 16/16 exposed real-primary/adversarial regression and 8/8 fresh blind pilot. Independent reviewer approval and representative real-news/secondary-source/ETF/company-event coverage remain open. |
| 5 | Compliance and risk | Not started | Screening methodology, ownership/custody, cash/position sizing, exposure/loss limits and protective-exit authority. |
| 6 | Research and backtesting | Technical single-instrument prototype | Portfolio simulation, point-in-time news/compliance replay, verified historical coverage, walk-forward/Monte Carlo, liquidity and blueprint performance gates remain. |
| 7 | Dashboard and Telegram | Not started | UI and end-to-end notification acceptance. |
| 8 | Paper trading | Not started | Broker simulation, ledger, order lifecycle, reconciliation and stable forward test. |
| 9 | Optional live broker integration | Disabled; not started | Compatible structure/broker, independent compliance review and explicit live-readiness approval. |

## Milestone 3 evidence

- Real samples include 17 AAPL IEX daily candles with sourced session checks,
  108 news observations, 313 BLS calendar events, company earnings and actions,
  a 25-bar 2020 split/volume audit and eight official 2026 FOMC dates.
- Immutable source revisions and authoritative server receipt times prevent
  later corrections from silently rewriting historical visibility. Observed-only
  publication provenance never invents historical release timestamps.
- Scoped provider/target/asset/purpose/window coverage fails closed for missing,
  stale, synthetic, unrelated or reduced-window polls. Date-only events restrict
  the whole local date, including DST boundaries.
- [Gold history audit](../reports/gold-history-audit-2025-2026-10-29.json): all twelve
  2025 archives fetched; 11 validate, producing 5,335 complete 1h and 1,151 complete
  4h bars. October conflicts are rejected. Missing volume is explicit, gaps are not
  filled, and derived artifacts are recomputed against retained source bytes.
- **The year-wide structural gate fails**, correctly: one rejected month cannot be
  concealed by summing only valid months. No session/price/liquidity certification
  or continuous-year research approval is implied.

## Milestone 4 evidence

- Strict JSON, source/target binding, exact quotes, no privileged output fields,
  source corrections during inference, claims before network calls, replay and
  bounded transport behavior are covered by automated tests.
- Historical v2/v3/v4 runs, failures and prompt text remain unchanged/readable.
  The larger real-source v4 pilot scored **10/16**. All eight attacks requested
  review, but financial sentiment was inconsistent with the frozen labels.
- V5 explicitly separates year-over-year earnings facts from absolute positive
  accounting levels, macro observations from unsupported gold-return predictions,
  and injected control instructions from financial sentiment.
- V5 passes the unchanged **16/16 regression** and a separately frozen **8/8 fresh
  pilot**. This is a purposive author-labeled sample, not independent approval,
  statistical calibration or representative production accuracy.
- The scorer now requires human review for attack quality acceptance and separately
  measures safe policy containment. A safely contained attack can still fail
  sentiment quality. Category support counts make sample omissions visible.
- An exclusive, hash-bound [review packet](independent-review.md) separates blind
  source/label evidence from model outputs and supplies an unapproved review form.

## Verification and release limits

The current full isolated SQLite suite passes **312 tests** with one existing
Starlette/httpx TestClient deprecation warning. Lint/format checks pass. Hosted CI
uses PostgreSQL and runs migrations, regression tests, synthetic research and mock
Gemini/offline evaluation; it never makes live provider calls. Historical reports
remain historical evidence, not the current milestone state.

The original blueprint's Milestone 3 timestamp/provenance/freshness and Milestone 4
schema/injection/deterministic-policy checks are implemented and pass software
acceptance. The stricter source-completeness and independent-review requirements
recorded during follow-up remain open; **neither milestone has full external
sign-off**. See [exact blockers](completion-requirements.md).

All decisions still deny execution authority. No profitability, paper-trading
readiness, ownership/compliance verification or Shariah approval is claimed.
