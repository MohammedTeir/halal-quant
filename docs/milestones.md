# Milestones and acceptance tracker

Source: [master blueprint v2](blueprint-v2.md). The agreed change is to use Python
for strategy development and acceptance, retaining TradingView/Pine as optional.
Milestones 1 and 2 are locally validated; this does not imply production readiness.
CSV ingestion and a single-instrument research prototype start parts of 3 and 6.
Their broader data/intelligence/portfolio requirements remain incomplete.

| # | Deliverable | State | Acceptance and evidence |
|---|---|---|---|
| 1 | Foundation and architecture | Implemented; locally validated | FastAPI boots; PostgreSQL 16 migrations upgrade/downgrade and metadata check pass; 61 tests pass across foundation and research; Docker API image builds; actual HTTP smoke and restart persistence checked. CI is defined; its hosted result has not been verified here. |
| 2 | Three Python strategies; optional Pine | Implemented; automated local acceptance passed | Stock pullback, ETF regime trend, gold breakout/retest; configurable periods/stops/dates/costs; 32 research tests; all defaults execute nonzero train/holdout trades on synthetic inputs and repeat byte-for-byte. Optional Pine compilation/parity remains unverified. |
| 3 | Market and news data | Started: CSV input foundation | UTC close timestamps, metadata/provenance hashes, adjusted-basis declarations and data integrity validated. Provider adapters, verified corporate actions, news ingestion and calendar still missing. |
| 4 | AI intelligence and decision engine | Not started | Schema constraints, evidence/source validation, prompt-injection cases and deterministic mandatory gates pass. AI cannot authorize orders. |
| 5 | Compliance and risk engines | Not started | Reject forbidden instrument/ownership/margin/lending cases and insufficient cash; verify risk sizing, portfolio caps and protective-exit independence. Select scholarly methodology and verified gold structure. |
| 6 | Research and backtesting | Started: technical single-instrument prototype | Fixed chronological split, explicit costs, whole shares, next-open fills and exposure-matched buy-and-hold reports implemented. Still required: portfolio simulation, historical news/compliance replay, verified corporate actions, walk-forward/Monte Carlo analysis, liquidity modeling and real-data research gates. No promotion without blueprint performance and violation gates. |
| 7 | Dashboard and Telegram | Not started | Next.js scanner/portfolio/analytics/operations and end-to-end signal-to-notification tests, with credentials outside source. |
| 8 | Paper trading release | Not started | Broker simulation, ownership/cash ledger, order lifecycle, idempotency, reconciliation and stable forward test with zero critical violations. |
| 9 | Optional live broker integration | Disabled; not started | Compatible cash broker, custody/possession checks, independent compliance review and explicit live-readiness approval. |

## First increment checks

- Automated: migrations on a disposable PostgreSQL test database; no metadata drift;
  API credential separation; durable event and single audit on replay; ID conflicts;
  invalid action/price/asset class/time/extra fields; missing migration readiness;
  live-mode rejection; indicator hand calculations and prefix invariance;
  all three Pine alert templates validate against the Python contract.
- Runtime: Docker build with TLS verification and trusted CA; PostgreSQL healthy;
  migration job completes; ready endpoint; real authenticated POST/read/replay;
  persistence after API container restart.
- Unverified external gates: GitHub-hosted CI outcome, optional TradingView compile/chart/replay,
  direct alert delivery through a trusted gateway, and fresh cloud task restoration.
- No performance, profitability, research acceptance or Shariah-approval claim has
  been established. Neither candidate ingestion nor Pine's research simulation
  implements compliance/risk/order authorization.

## Python increment acceptance

- 61 tests pass on the full PostgreSQL-backed suite, including 32 research tests.
- Every strategy exercises both entry and exit behavior; tests reject a zero-trade
  fixture as acceptance. Prefix and future-mutation tests validate causal signals;
  gold uses only completed higher-timeframe buckets.
- Cash-only whole-share fills, adverse costs, gapped stops, monotonic trailing stops,
  date limits, missing benchmark data, short samples and invalid CSVs are tested.
- Fixed train/holdout windows start independently flat. Future holdout data cannot
  alter the training ledger. End-of-window liquidation reserves a real next bar.
- All default strategies and baselines execute nonzero synthetic train/holdout
  trades, end without open positions/pending orders/unfilled candidates, and produce
  byte-identical repeated CLI reports. See [recorded evidence](../reports/synthetic-smoke.json).
- Upstream pandas deprecation warnings are retained; no unexpected engine warnings
  occurred in the default synthetic acceptance. One existing Starlette test-client
  deprecation warning appears in the full suite.

## Next work

Choose a verified historical-data provider and import real adjusted candles with
source/session metadata. Add corporate-action validation and news/economic-calendar
contracts for Milestone 3. Keep real holdout periods frozen before reviewing results.
Build compliance/risk gates before any paper promotion. Complete Milestone 6's
portfolio and point-in-time research requirements before interpreting strategy
performance as release evidence. Optional Pine validation is not a blocker for
Python development. Live trading remains disabled.
