# Milestones and acceptance tracker

Source: [master blueprint v2](blueprint-v2.md). Work starts with Milestones 1–2;
later milestones are planned, not implied by the presence of technical candidates.

| # | Deliverable | State | Acceptance and evidence |
|---|---|---|---|
| 1 | Foundation and architecture | Implemented; locally validated | FastAPI boots; PostgreSQL 16 migrations upgrade/downgrade and metadata check pass; 29 tests pass; Docker API image builds; actual HTTP smoke and restart persistence checked. CI is defined but has not run on GitHub. |
| 2 | Three Pine v6 strategies | Implemented draft; acceptance pending | Configurable stock, ETF, gold scripts, long-only entry sites, ATR/trailing stops, cost/date controls and v1 JSON contract. Python indicator and source guardrail tests pass. TradingView compilation, replay, chart behavior and numeric parity still required. |
| 3 | Market and news data | Not started | Validate UTC timestamps, publication/ingestion timing, provenance, corporate actions, deduplication and freshness; missing feeds fail closed. Select providers before production adapters. |
| 4 | AI intelligence and decision engine | Not started | Schema constraints, evidence/source validation, prompt-injection cases and deterministic mandatory gates pass. AI cannot authorize orders. |
| 5 | Compliance and risk engines | Not started | Reject forbidden instrument/ownership/margin/lending cases and insufficient cash; verify risk sizing, portfolio caps and protective-exit independence. Select scholarly methodology and verified gold structure. |
| 6 | Research and backtesting | Not started | Reproducible point-in-time runs, causal fills, fees/slippage, frozen out-of-sample periods, walk-forward and baseline reports. No promotion without blueprint performance and violation gates. |
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
- Unverified external gates: GitHub-hosted CI run, TradingView compile/chart/replay,
  direct alert delivery through a trusted gateway, and fresh cloud task restoration.
- No performance, profitability, research acceptance or Shariah-approval claim has
  been established. Neither candidate ingestion nor Pine's research simulation
  implements compliance/risk/order authorization.

## Next work

Complete the [TradingView acceptance checklist](pine-validation.md) with saved
compiler and chart evidence. Milestone 3 can then add provider-neutral data contracts
and timestamp/provenance tests; production provider adapters require an actual
provider selection. Do not mark Milestone 2 complete from Python source checks alone.
