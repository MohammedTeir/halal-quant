# Milestones and acceptance tracker

Source: [master blueprint v2](blueprint-v2.md). The agreed change is to use Python
for strategy development and acceptance, retaining TradingView/Pine as optional.
Milestones 1 and 2 are locally validated; this does not imply production readiness.
CSV and versioned fact ingestion, split audits and single-instrument research start parts of 3 and 6.
Their broader data/intelligence/portfolio requirements remain incomplete.

| # | Deliverable | State | Acceptance and evidence |
|---|---|---|---|
| 1 | Foundation and architecture | Implemented; locally validated | FastAPI boots; PostgreSQL 16 migrations upgrade/downgrade and metadata check pass; 89 tests pass across foundation, research and ingestion; Docker API image builds; actual HTTP smoke and restart persistence checked. CI is defined; its hosted result has not been verified here. |
| 2 | Three Python strategies; optional Pine | Implemented; automated local acceptance passed | Stock pullback, ETF regime trend, gold breakout/retest; configurable periods/stops/dates/costs; 32 research tests; all defaults execute nonzero train/holdout trades on synthetic inputs and repeat byte-for-byte. Optional Pine compilation/parity remains unverified. |
| 3 | Market and news data | Provider-neutral foundation validated; real feeds pending | Historical CSV validation, split/volume audits, immutable news/calendar/action revisions, authoritative server receipt times, point-in-time reads, conservative URL deduplication and missing/stale/synthetic feed checks pass. Real providers, workers, exchange sessions, verified action completeness and historical availability archives remain outstanding. |
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

- The Python increment originally passed 61 tests (32 research); the current full suite passes 89.
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

## Data increment acceptance

- 89 tests pass: the earlier 61 plus 17 data/API and 11 split-audit tests.
- `0002_data_events` upgrades the existing schema without removing signals; drift,
  readiness and downgrade/re-upgrade checks pass. New source revisions, imports and
  audits are durable and atomic; concurrent identical imports create one audit.
- Publication and server receipt must both precede an as-of query. Corrections,
  late arrivals and calendar cancellations retain historical visibility semantics.
- URL deduplication preserves source observations. Missing/stale feeds fail closed;
  fresh synthetic polls cannot satisfy a required non-synthetic feed.
- Split arithmetic covers forward/reverse splits, cumulative factors, explicit
  volume basis, effective dates, correction receipt and CLI success/failure outcomes.
- Real HTTP import/read/replay and restart persistence pass. See
  [data ingestion](data-ingestion.md) and the recorded evidence links there.
- This is provider-neutral/synthetic validation. Real source verification and
  trustworthy historical news receipts remain unverified. The technical backtester
  does not yet consume the new facts or enforce event restrictions.

## Next work

Choose a verified historical-data provider and import real adjusted candles with
source/session metadata. Connect the tested corporate-action and news/economic-calendar contracts to verified
provider adapters and acquisition workers for Milestone 3. Keep real holdout periods frozen before reviewing results.
Build compliance/risk gates before any paper promotion. Complete Milestone 6's
portfolio and point-in-time research requirements before interpreting strategy
performance as release evidence. Optional Pine validation is not a blocker for
Python development. Live trading remains disabled.
