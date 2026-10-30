# Milestone 5: stored compliance and risk workflow

The controls core now has role-separated persistence, qualified-review **attestation**
interfaces, a fixed-host read-only broker capture, server-sourced checks, serialized
research capacity holds, and revalidation in the existing decision evaluator.
All outputs remain `authorized=false`. Real issuer truth, reviewer qualification,
account contracts, Shariah approval and execution authority are not invented by code.

## Trust boundaries and setup

Apply migration `0006_controls`. It adds append-only `control_revisions`, durable
`broker_captures`, recorded `control_checks`, `control_reservations`, and a seeded
`control_lock`. Readiness checks the head, tables and lock row. Existing signals,
facts/classifications/jobs are preserved; downgrade deletes the new controls ledger.
Do not downgrade operational data merely to reset failed jobs or reservations.

Configure distinct backend credentials/identities (empty roles deny all access):

| Role | Header | Backend configuration | Authority |
|---|---|---|---|
| Reviewer | `X-Controls-Reviewer-Key` | `CONTROLS_REVIEWER_KEY`, `CONTROLS_REVIEWER_IDENTITY` | Attest methodology/asset/risk-policy/reconciliation; explicitly clear kill switch |
| Risk operator | `X-Controls-Operator-Key` | `CONTROLS_OPERATOR_KEY`, `CONTROLS_OPERATOR_IDENTITY` | Engage kill switch; release research-only holds |
| Broker reader | `X-Controls-Broker-Key` | `CONTROLS_BROKER_KEY` | Start fixed server GET captures; cannot upload broker balances or positions |
| Analyst | `X-Analysis-Key` | Existing analysis key | Request controls/check and decision evaluation; cannot approve reviews |
| Dashboard | `Authorization: Bearer …` | Existing dashboard key | Read histories and redacted capture status |

Keys must also differ from existing dashboard/webhook/data/analysis credentials.
The server records its configured actor and receipt time; body-provided actor or
receipt fields cannot supply application authority. Identities/configured keys are
not external authentication of an actual scholar or evidence truth. Select the
qualified methodology/reviewer and verify the evidence outside model output.
These app settings do not edit or publish the cloud environment configuration.

## Review and loss-state records

Reviewer endpoints:

- `POST /api/v1/controls/reviews/methodologies`
- `POST /api/v1/controls/reviews/assets`
- `POST /api/v1/controls/reviews/policies`
- `POST /api/v1/controls/reviews/risk-reconciliations`

Each record has an immutable revision ID, request hash, actor, references/note, server receipt,
effective time, expiry and audit. Same ID/input replays; changed input conflicts.
Latest known effective revisions win. Expired, rejected or missing current records
never silently fall back to old approval. Future effective reviews remain inactive
until their effective time; no backdated receipt grants historical knowledge.

No default religious methodology is selected. Methodologies have a stable `methodology_id`, separate immutable revision `record_id`, and APPROVED/PENDING/REVOKED status (default PENDING). Withdrawal/expiry invalidates existing asset approvals; current assets pin the precise reviewed methodology revision. A reviewer defines denominator basis
(total assets/average market cap), debt/interest-asset/impure-revenue thresholds,
strict/inclusive boundary and divestment guidance. For stock APPROVED submissions,
the engine calculates ratios from supplied financial inputs and rejects mismatched
basis or threshold failure. Business/financial/structure/possession checks must also
pass. This validates declared figures/rules; it does not independently collect or
audit financial statements, compute market-cap averages or grant an automated fatwa.
ETF mandate/holdings/structure/supervision and gold custody/possession/redemption
remain explicit reviewer evidence. An XAUUSD chart does not become owned gold.

Risk policies require reviewer credentials; version must equal immutable record ID.
Reconciliations explicitly attest the New York trading day, start/peak equity,
realized PnL, consecutive losses, last-loss time and complete history. The operational policy is restricted to America/New_York for the current adapter; the capture retains its activity day/window, and mismatched days block. The state is
bound to the broker activity-set hash: a changed/incomplete set invalidates it until
reviewed again. Server-observed account equity history prevents lowering a known
peak via a fresh reconciliation. This is a reviewed reconciliation workflow, not
an automatically reconstructed full FIFO/cash/fill ledger (the latter belongs to
paper execution/reconciliation work). No unverifiable reset is inferred from LLMs.

When a non-approved asset revision affects a last-observed positive holding, the
store creates an audited `divestment` REVIEW_REQUIRED record with the selected
methodology guidance and source capture. It neither orders immediate liquidation
nor infers indefinite permission to hold. Qualified disposition remains required.

Read `GET /api/v1/controls/history?kind=…&scope=…&as_of=…` with dashboard auth.
Historical receipt and effective/expiry times remain visible; the view is bounded.
The database/audit is append-only through these APIs, not immutable against DBAs.

## Broker and quote observations

`POST /api/v1/controls/broker/refresh` takes only `refresh_id`.
`POST /api/v1/controls/quotes/refresh` takes `refresh_id` and a supported symbol.
Both require the broker-reader role. No input URL, key, price, cash, holdings or
trust flag is accepted. Status is readable at
`GET /api/v1/controls/broker/captures/{refresh_id}` with dashboard auth; it hides
balances, account number, raw positions and provider error bodies.

The adapter issues verified TLS/proxy GETs only to `paper-api.alpaca.markets` and
`data.alpaca.markets`. It never sends/cancels an order or follows redirects. It
reads account, positions, open orders/configuration, a bounded current-day activity
set and repeated position fields; it captures IEX bid/ask separately. A full capped
page is incomplete. Changed repeated position fields are incomplete; matching reads
are not a promise of atomic broker state. Unowned/short/unsupported positions never
become positive owned-long evidence. Negative cash does not erase long holdings
needed for protective-exit review.

Claims commit before HTTP. No database transaction spans requests. Success/failure
and audit commit after observation. Replaying a successful, failed or RUNNING ID
never recalls the provider. Ambiguous/crashed jobs need operator investigation;
use a deliberate new ID for a new acquisition. A newer failed/in-progress account
capture blocks reuse of an older success; credentials/account changes do not borrow
a previous account's latest capture. Errors are sanitized.

The actual configured paper account and IEX quote were read successfully on
2026-10-29. The sanitized acceptance reports retain response hashes and capabilities,
not balances/account identity. **Alpaca's reported cash, buying power or multiplier
is not settled-cash/cash-account/lending/custody proof**. This adapter deliberately
leaves those authority flags false; current real BUY controls therefore block.
The fixture broker used by positive tests is not evidence that Alpaca exposes those
contracts. A qualified cash/settlement source is required before real funding can
pass. The adapter cannot attest allocated gold and does not substitute a gold ETF.

A local administrator can explicitly acquire into a migrated isolated database:

```sh
uv run python -m services.controls.acquire_broker --kind account \
  --refresh-id new-read-only-poll --report-output reports/generated/new-broker-report.json
```

The command uses backend settings and no caller-selected endpoint/key. Reports are
sanitized and exclusively created. Full normalized financial observations remain
in the configured private database. Do not commit account databases or raw secrets.

## Server checks, reservations and decisions

`POST /api/v1/controls/check` requires analysis auth and `check_id`, `account_id`,
`signal_id`, optional desired `quantity`/`stop_price`, and `reserve` (default true).
The signal must already be server-stored/current. Symbol/class/action come from it;
sector and compliance come from reviewed records; prices, positions and orders come
from server captures. Stop/quantity remain technical proposals, never broker facts.
The original hypothetical preview still exists and cannot write these authorities.

Entry checks require current policy/method/asset/risk-state/quote/broker observations,
funding/lending contract evidence, complete scope/history, valid stops, known current
position risk and bounded pending buy prices/risk. Missing protective stops, unknown
sectors/risks, invalid pending long stops or unsupported positions block new risk.
Only same-symbol, US-equity, active SELL stop legs covering remaining quantity supply planned protection. Invalid/foreign/canceled/undersized legs retain unknown risk. Unknown/unsupported broker-order asset classes and unowned/oversubscribed SELL roots block new entries. Broker protective-stop assumptions are planned risk only; gaps can exceed buffers.

A database lock serializes **all** control state writes and check/reserve operations:
PostgreSQL row lock, SQLite immediate transaction. The server samples current time **after** lock waits, so a competitor hold/kill committed during a wait cannot be hidden by an earlier call timestamp. Different request/signal IDs cannot
multiply shared cash/risk/exposure. Reviewer updates and kill switches share that lock.
Holds are research-only budget reservations, not orders or broker cash changes. Their
short expiry is clamped to source/review freshness and never extended by replay.
Pending broker orders continue consuming capacity; pending sells do not free buy
exposure before fill. Current owned sellable broker quantity is reduced by separate
research sell holds; no borrowing is inferred.

`POST /api/v1/controls/kill-switch/engage` is operator-only; `…/clear` reviewer-only.
`POST /api/v1/controls/reservations/release` is operator-only with an immutable release
ID/reason. It releases a research hold, not a broker order. Replay exposes the original
expiry/current-active flag, not a renewed authorization. Operational order lifecycle,
reconciliation, cancellation and durable live-order holds remain Milestone 8 work;
do not reuse research TTL release as a broker-order safety guarantee.

`POST /api/v1/decisions/evaluate` optionally references `control_check_id`. It checks
signal binding and an active reservation, then re-derives current controls excluding
its own hold and pins the reserved quantity. New kill/revocation/stale/history changes
cannot be cleared by an old passing result. Owned exits use fresh available long
quantity without entry kill/loss/compliance guards; broker/execution revalidation is
still necessary. Entry market/source/news gates remain independently fail-closed.
No passing controls snapshot bypasses them. Execution always remains unauthorized.

## Completion boundary

Software acceptance is tested separately from real qualification/funding approvals.
Real use still requires named qualified review, selected methodology/asset/custody
evidence, verified cash/settlement/lending contract data and representative operational
acceptance. No default APPROVED asset, reviewer key or live execution is enabled.
Historical quality/session limits from Milestones 3/4 remain. The reviewed APIs and
risk engine cannot turn those missing external facts into approval.


## Recorded verification

Current full isolated regression: **459 passed**, one existing TestClient deprecation.
This increment adds **47** broker/storage/API/time/concurrency checks beyond the
412-test initial-controls checkpoint. Tests use fictional reviewer/qualified-broker
contracts for positive cases; those are not vendor truth. The real read-only probes
succeeded for the observed empty paper account and quote, with funding/lending
proof flags false. [Independent technical review](milestone-5-independent-review-2026-10-29.md)
found six software issues, all resolved and rechecked; its verdict is bounded
research-workflow acceptance, not human/Shariah/execution release. Atomic real
OCO/bracket fills/cancel/settlement and immutable asset-ID continuity remain
execution-release requirements. No order endpoint is implemented.
