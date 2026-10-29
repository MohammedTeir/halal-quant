# Milestones and acceptance tracker

Source: [master blueprint v2](blueprint-v2.md). The agreed change is to use Python
for strategy development and acceptance, retaining TradingView/Pine as optional.
Milestones 1 and 2 are locally validated; this does not imply production readiness.
CSV and versioned fact ingestion, split audits and single-instrument research start parts of 3 and 6.
Their broader data/portfolio requirements remain incomplete. Milestone 4 now has a validated advisory boundary and policy core; Gemini adapter mock acceptance is complete; live-model validation is pending.

| # | Deliverable | State | Acceptance and evidence |
|---|---|---|---|
| 1 | Foundation and architecture | Implemented; locally validated | FastAPI boots; PostgreSQL 16 migrations upgrade/downgrade and metadata check pass; 259 tests pass across foundation, research, ingestion, decisions and mocked Gemini; Docker API image builds; actual HTTP smoke and restart persistence checked. CI is defined; its hosted result has not been verified here. |
| 2 | Three Python strategies; optional Pine | Implemented; automated local acceptance passed | Stock pullback, ETF regime trend, gold breakout/retest; configurable periods/stops/dates/costs; 32 research tests; all defaults execute nonzero train/holdout trades on synthetic inputs and repeat byte-for-byte. Optional Pine compilation/parity remains unverified. |
| 3 | Market and news data | Provider-neutral foundation validated; real feeds pending | Historical CSV validation, split/volume audits, immutable news/calendar/action revisions, authoritative server receipt times, point-in-time reads, conservative URL deduplication and missing/stale/synthetic feed checks pass. Read-only Alpaca/Finnhub/BLS adapters, a restart-safe batch worker and sourced session audits now pass mocked acceptance. Real feed/account validation, complete action/gold/FOMC/earnings coverage, per-target verification and historical archives remain outstanding. |
| 4 | AI intelligence and decision engine | Core and Gemini adapter validated with mocks; live/model quality pending | Strict evidence contracts, immutable model history, event/gate policies, Gemini REST structured-output adapter, durable generation claims, bounded transport retries and mocked API tests pass. Frozen quality/adversarial evaluation and one-shot collection tooling are implemented. Real-account/model compatibility, held-out quality/robustness results, source verification and human review remain incomplete. |
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

- The Python increment originally passed 61 tests (32 research); the current full suite passes 259.
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

- The data increment passed 89 tests: the earlier 61 plus 17 data/API and 11 split-audit tests. Current total: 259.
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

## Intelligence/decision increment acceptance

- The intelligence/decision increment passed 153 tests: the earlier 89 plus 51 parser/schema/policy/core and 13
  classification/decision API tests. SQLite's 40 API tests also pass.
- Model output accepts only strict JSON, known current source IDs and exact quoted
  evidence. Invented sources/quotes, duplicate JSON keys, order/tool/approval fields,
  malformed output and wrong symbol/asset scope are rejected.
- Stored classifications preserve model/prompt versions and original source revisions.
  Receipt time prevents historical leakage; corrections/expired assessments cannot
  silently remain current. Opposing assessments require review.
- Earnings/macro windows and confidence/uncertainty restrictions cannot be cleared
  by positive ALLOW text. Mandatory gate priority and score boundaries are tested.
- Entry and protective exit paths are separate. Owned exit candidates are possible
  in trusted-state unit tests despite blocked entries; public exits cannot invent
  ownership. All candidate results still deny execution authorization.
- `0003_intelligence` preserves earlier facts/signals. Concurrent retries write one
  classification/decision audit. Actual HTTP smoke and restart persistence pass.
- See [intelligence and decisions](intelligence-decisions.md) and
  [synthetic runtime evidence](../reports/decision-smoke.json). No real LLM, accuracy
  assessment, live feed or order was involved. This does not complete Milestone 4.

## Gemini adapter increment acceptance

- That increment passed 201 tests: the previous 153 plus 31 adapter/config and 17 generation API tests.
  SQLite's 57 API tests also pass. All provider traffic in tests is HTTP-mocked.
- Backend-only key, fixed Google endpoint, verified TLS/proxy trust, no redirects,
  no caller-selected model/URL/key/tool, and target-bound JSON output are tested.
- Claims commit before inference; concurrent/duplicate requests do not recall the
  model. Success atomically stores assessment/model/usage/audits. Invalid evidence
  or a source correction during inference fails without storing an assessment.
- Two transport attempts maximum, limited transient retries, no ambiguous read/
  delivery retries, safe error codes, bounded response size and retained usage
  metadata pass. Crashed/ambiguous jobs stay blocked rather than auto-regenerating.
- `0004_gemini_jobs` preserves earlier records. Mock API smoke passes without a real
  key/call; the container stack loads its CA bundle and denies disabled generation.
- See [Gemini setup](gemini.md) and its recorded mock/container evidence. Real account,
  selected model, model accuracy and prompt-injection robustness remain unverified.

## First-four completion pass

- Current full PostgreSQL suite: **257 passed** (one existing test-client deprecation warning).
- Added 56 tests for acquisition, provider normalization/corrections, atomic polls,
  session/DST/early-close checks, worker restart/replay and model-quality evaluation.
- Provider traffic is mocked. No Alpaca, Finnhub, BLS or real Gemini request was sent.
- [Completion checklist](first-four-acceptance.md) remains open; credentials and
  network access are absent, and several required data coverage/review gates remain.
- [Provider setup](data-providers.md) and [model evaluation](model-evaluation.md)
  describe concrete commands and the evidence needed to close those gates.

## Next work

Choose a verified historical-data provider and import real adjusted candles with
source/session metadata. Connect the tested corporate-action and news/economic-calendar contracts to verified
provider adapters and acquisition workers for Milestone 3. The Alpaca/Finnhub/BLS
adapters are implemented but require live validation and full target/event coverage. Keep real holdout periods frozen before reviewing results.
Implement trusted compliance/risk/ownership services for Milestone 5, and configure/evaluate the selected Gemini model against real-account and quality gates before calling Milestone 4 complete. No paper promotion until its prerequisites pass. Complete Milestone 6's
portfolio and point-in-time research requirements before interpreting strategy
performance as release evidence. Optional Pine validation is not a blocker for
Python development. Live trading remains disabled.

## Published-environment live follow-up (2026-10-29)

- Provider credentials and Gemini model/enablement are ready; allowed destinations
  are enforced. No environment draft edits or publication were performed.
- Actual Alpaca IEX acquisition: 17 AAPL daily candles pass full session checks.
  Finnhub: 108 news observations imported. BLS: 313 calendar events imported;
  source publication stamps are absent and explicitly labeled as first observation.
- Fixed unstamped BLS support without inventing historical publication: optional
  provenance metadata preserves legacy canonical payloads; unchanged re-polls
  preserve source revisions/first observed times. Two regression tests added.
- Current full isolated SQLite suite: **259 passed**, one existing warning.
  Hosted PostgreSQL CI passed for `68ab48f`; the latest fix needs its own CI result.
- Real `gemini-3.5-flash-lite` metadata/generation verified. Diagnostic failed:
  8 valid responses, 7 label matches out of 12, two ambiguous timeouts (not
  recalled), two unattempted cases. Independent holdout/source review remains open.
- [Live evidence](../reports/live-provider-acceptance-2026-10-29.json) and
  [diagnostic scores](../reports/gemini-live-diagnostic-2026-10-29.json) supersede
  earlier statements that no live calls had occurred. Milestones 3/4 remain open
  for complete data coverage and a successful independently reviewed quality gate.
