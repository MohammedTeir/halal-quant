# Milestone 5: first controls increment

Status: **started; deterministic hypothetical controls core implemented**. The full
milestone is not complete. No real asset, broker account, instrument or scholarly
methodology is approved by this increment. All results retain `authorized=false`
and `evidence_authority_verified=false`.

## Implemented

- Strict contracts for asset screening, instrument structure, source evidence,
  broker/account/positions/reservations, quotes, candidate and versioned policy.
- Stock business/financial screening assertions; ETF mandate/holdings/structure/
  supervision assertions; gold ownership/possession/custody/settlement/redemption
  assertions. Missing items, wrong scope/methodology, PENDING/REJECTED, future receipt
  and expired evidence block hypothetical entries. These assertions are not computed
  from real financial statements or independently authenticated by this module.
- Cash-account, lending/borrowing, no short/margin/CFD/future/option, settlement and
  whole-unit checks. Unsupported fractions are rejected in this first increment.
- Decimal whole-unit sizing bounded by trade/open risk, settled cash after other
  holds and pending buy costs, single-position and sector capacity. Pending sells
  do not release exposure until filled; pending buys reserve exposure/risk/cash.
- Daily realized loss, drawdown, consecutive-loss cooldown, stale/incomplete broker
  and quote inputs, required-feed flags and kill-switch entry guards.
- Separate hypothetical owned-exit checks: sellable quantity minus pending sells,
  fresh complete ownership snapshot and matching asset class. Entry kill/loss/news
  restrictions and noncompliant status do not automatically prevent reducing owned
  holdings. Broker execution/ownership still needs independent authority.
- Authenticated read-only preview endpoint, offline CLI, schema/example and tests.
  Preview inputs never populate real decision/broker/compliance state or persist
  approvals. Existing signal evaluation keeps its unavailable-authority gates.

## API and CLI

`POST /api/v1/controls/preview` requires `X-Analysis-Key`. The request matches
[ControlScenario](contracts/control-scenario-v1.schema.json). Its only mode is
`hypothetical`; extra privilege fields and coerced authority booleans are rejected.
The API rejects a future `as_of`. Input timestamps are scenario claims, not server-
attested receipts. No provider/LLM/order request or database authority write occurs.

[Example](../examples/controls/hypothetical-entry.json) is a fictional EXAMPLE asset,
demo methodology and account: $10,000 equity, $100 ask, $95 stop and zero costs.
The result is 10 units, $1,000 cash and $50 planned stop risk. This is the blueprint's
arithmetic example, not permission to buy an actual security.

```sh
uv run python -m services.controls.cli \
  --scenario examples/controls/hypothetical-entry.json \
  --output reports/generated/new-controls-preview.json
```

CLI outputs preserve the validated scenario, policy/scenario hashes and reasons.
Repeated identical inputs produce byte-identical reports. Existing files are never
overwritten. Exit 0 means SIMULATION_PASS, 1 saves SIMULATION_BLOCKED, and 2 rejects
input/output. None grants trading authority. CLI can describe future hypothetical
times; the server API permits only known as-of time.

## Provisional engineering conventions

Defaults implement the existing risk specification: 0.5% trade risk, 3% total open
risk, 10% position allocation, 25% sector exposure, 2% daily realized loss and 10%
drawdown. Entry blocks at the daily-loss/drawdown boundary; capacities round down.

The realized-loss denominator is day-start equity for the New York calendar date,
including DST; mismatched day snapshots block. Drawdown uses peak account equity.
Three consecutive losses require a known last-loss time and a full 60-minute
cooldown (the exact deadline clears it). This duration is an explicit provisional
research convention, not a scholarly or performance recommendation. Broker/quote
observation age is at most 30/15 seconds respectively. Evidence expires at the exact
expiry instant. Future recorded/effective evidence is unavailable at as-of.

For ask `A`, stop `S`, slippage fraction `s`, per-unit fee `f` and per-order fee `F`:

- Buffered entry `A(1+s)`, buffered stop `S(1-s)`.
- Planned risk `q × (A(1+s) − S(1-s) + 2f) + 2F`.
- Buy cash `q × (A(1+s) + f) + F`.

Only complete budgets allow positive whole quantity. Costs can make zero quantity
correct; an explicitly requested quantity above capacity is blocked rather than
silently reduced. Stop fills can exceed these assumed buffers. The cash field is
settled cash **before** separately enumerated pending buy reservations; other cash
holds exclude those enumerated reservations, avoiding an implicit double count.
Position market values and open-risk figures are supplied snapshot assertions;
real valuation/stop-risk computation and reconciliation remain to be wired.

The client can vary hypothetical policies, including its kill switch. This never
changes a persisted policy or actual operational kill switch. Limits and windows
need validation and approval before operational use; model confidence supplies none.

## Remaining Milestone 5 work

1. Select a qualified screening methodology/reviewer/provider and verified gold
   structure; calculate/validate the actual screening evidence and purification/
   divestment rules rather than treating arbitrary booleans as authority.
2. Add immutable/versioned database records, role-separated reviewer/operator
   actions and durable operational risk/kill-switch state with audit and replay.
3. Read and reconcile authoritative broker accounts, settled cash, lots, custody,
   sellable holdings and pending orders. Never load preview bodies as broker truth.
4. Maintain loss/peak/reservation/valuation history and revalidate all quantities,
   prices and limits atomically at future execution authorization; prevent concurrent
   candidates from over-reserving shared capacity.
5. Integrate verified controls into server candidate snapshots and complete accepted
   instrument/broker workflows, qualified compliance review and operational tests.

Full regression: **412 tests pass**, including **78 new control/API checks**. CLI
example/repeat is byte-identical. All new acceptance inputs are fictional; no real
compliance approval, ownership, cash, risk authority or order is established.
