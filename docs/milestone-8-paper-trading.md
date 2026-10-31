# Milestone 8: internal paper trading

The user selected an **internal simulator with read-only Alpaca market data**.
The software now supports a separately gated forward campaign, autonomous virtual
order processing and an English-default dashboard with Arabic controls. It has
no external broker order transport. **Milestone 8 acceptance remains pending an
actual elapsed forward run.** The blueprint requires “Stable forward testing and
no critical operational violations”; passing accelerated fixtures cannot prove it.

## Implemented scope

- Immutable isolated cash accounts, market/limit orders, partial fills,
  cancellation/expiry, reservations, whole shares, fees/slippage, cost basis,
  realized P&L and settlement. No margin, borrowing, shorting or derivatives.
- Synthetic mode retains explicit quote/match controls. Forward mode accepts
  executable quotes and fills only from the worker, with fixed-host GET-only
  Alpaca IEX data, provider clock/session/calendar checks and receipt hashes.
  A later fresh quote is required for every fill; duplicate observations cannot
  replenish liquidity. Displayed sizes are conservatively treated as shares.
- Forward accounts support 1–10 US stock/ETF tickers, explicit symbol mappings,
  regular market hours and calendar-derived simulated T+1 through T+3 settlement.
  Synthetic accounts retain their configured elapsed settlement delay.
- Fresh stored research decisions can create deterministic virtual orders, once
  per source signal, after current policy, asset, methodology, source, news,
  calendar, ownership, cash and risk revalidation. The worker consumes existing
  upstream evidence; it does not invent signals or acquire missing news.
- Standing forward stop exits and operator liquidation intent sell owned shares
  only. Entry rejection, review expiry or source gaps do not disable protection
  for symbols with fresh usable quotes. Missing quotes never fill from stale
  cached liquidity. Stops can gap and cannot execute while the market is closed.
- Known corporate actions block new entries around their effective date and
  trigger exits beforehand. A position held across a known effective action
  makes the campaign critical; no split/dividend adjustment is fabricated.
- Server-enforced operator/reviewer separation, exact immutable protocol/config
  hashes, expiring review, fenced worker leases, restart evidence and chained
  cycle records. One campaign belongs to one fresh account.
- Ledger replay checks projections, quote consumption and independent financial
  deltas (cash, fees, shares, cost basis and settlements). Drift blocks mutation;
  post-cycle drift rolls back the transaction. This reconciles the internal
  simulator, not an independently captured external broker account. Database
  owners can rewrite hashes; they are not independently signed attestations.
- Bilingual dashboard creation, synthetic orders/quotes/matching, cancellation,
  halt/resume, forward protocol/review, owned liquidation intent, status export
  and finalization. Roles and CSRF are enforced on the backend. Admin does not
  implicitly have financial operator or reviewer rights.
- Emergency halt, cancellation, settlement tick and liquidation intent remain
  available to operators when entry flags are disabled. A running worker needs
  its configured flags to process exits; do not stop protection with holdings.

## Verification and acceptance boundary

[Source CI](https://github.com/MohammedTeir/halal-quant/actions/runs/41193584945) passed **645 tests** on PostgreSQL, including encrypted backup/isolated restore, for `299c505`. Local verification passed **643 tests, two PostgreSQL-only skips**, static-build
checks, lint/format, shell syntax and English/Arabic/mobile Chromium interaction
with zero JavaScript errors. Provider tests use mocked HTTP. Migration tests
preserve old quote JSON, command hashes and consumed quantities. Failure tests
cover stale/partial data, lease loss, expired reviews, restart, signal duplication,
late validation, corporate events and financial drift.

The isolated smoke simulates 20 days/round trips and ends reconciled and flat:

```sh
uv sync --frozen
uv run pytest -q
uv run python -m scripts.paper_smoke --output reports/generated/paper-smoke.json
```

These are software tests with injected time/data, not live performance or elapsed
forward evidence. The report-finalization positive unit test also fabricates its
timeline explicitly; it is not an operator acceptance report. See the
[software report](../reports/milestone8-forward-software-2026-10-31.json) and
[historical first checkpoint](../reports/milestone8-paper-simulator-2026-10-31.json).

## What remains to complete Milestone 8

Follow the [forward operations runbook](milestone-8-forward-operations.md): deploy
migration `0009_paper_forward`, configure the user's data and upstream producers,
choose instruments, obtain distinct paper-scoped reviews, and run the worker.
The implemented protocol proposes at least **20 complete regular-market sessions
and 20 actual elapsed days**, default ten completed exits (minimum three), a
restart with pending orders or owned holdings, no critical violations, current
reviews and flat settled final balances. Those numeric thresholds operationalize
the blueprint; they were not previously documented as completed acceptance and
must be explicitly reviewed for the campaign.

Accumulate genuine timestamped evidence, export and finalize only when all gates
pass. Interrupted/partial sessions do not count as complete sessions. No actual
campaign has been started or accepted by the development tests. Earlier source,
qualified compliance/custody and representative performance acceptance remains
open where documented. Paper-scoped reviews do not close those gates. Milestone
9 and live trading remain disabled.

## Campaign setup follow-up

The [setup workflow](milestone-8-forward-operations.md#automated-preparation-and-source-polling) now prepares immutable drafts, configures private source IDs, acquires observations and submits an operator-authenticated pending campaign. A separate source worker reuses existing adapters. The local follow-up passed **657 tests, two PostgreSQL-only skips**, including 11 setup tests. A real ten-candidate source probe imported 31/32 polls; MU action date semantics remain unresolved. No approval or acceptance was inferred. See the [setup report](../reports/milestone8-campaign-setup-2026-10-31.json).

[Hosted CI](https://github.com/MohammedTeir/halal-quant/actions/runs/41211947049) passed **659 tests** on PostgreSQL for source `7422658`, including encrypted backup/isolated restore and all existing offline acceptance steps.
