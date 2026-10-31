# Milestone 8: internal paper simulator

Milestone 8 has started. The first implementation is an internal **synthetic cash
simulator**, with durable order and ledger state and a read-only English-default /
Arabic dashboard panel. It has no order-submission transport to Alpaca or any
other broker. It does not promote signals, real assets, compliance attestations,
or AI decisions into execution authority. Stable forward-test acceptance remains
**not established**, and Milestone 8 is not marked complete.

## Implemented scope

- Separate accounts with immutable initial virtual cash, a fictional symbol/sector
  universe and simulation policy. No edits, deposits, margin, lending, short sales,
  fractional shares, derivatives, gold custody or real settlement are modelled.
- Market and limit buy/sell orders, accepted/rejected/partially filled/filled,
  cancelled and expired states. Buy orders need a planned stop. That stop is a
  risk-sizing input, **not an automatic protective stop order**.
- A market buy reserves a maximum price from the submission ask plus configured
  slippage. A later quote above that bound does not fill. A limit order never
  fills beyond its bound or at an invented better-than-quote price. Prices include
  the configured spread/slippage; per-order fees are charged on the first fill,
  per-share fees on each fill. Average cost includes entry fees; realized P&L
  includes exit fees. Arithmetic uses Decimal without a real broker's rounding rules.
- Persistent cash/share reservations prevent duplicate spending or selling the
  same shares twice. Whole-share fills consume available synthetic quote sizes
  across all orders; replaying a fill command cannot consume liquidity again.
- Sale proceeds stay in an unsettled ledger until an explicit tick after the
  configured elapsed delay (default 172800 seconds). This is a simulation delay,
  not a verified exchange holiday calendar or proof of T+1/possession.
- Server receipt times, latest strictly increasing quote observations, freshness,
  order/quote symbol and account matching, and no pre-order observations as fills.
  Client input cannot select a past execution timestamp. A regressed server clock
  blocks new commands. Expiry/settlement is processed by tick, or order expiry at
  a fill attempt; there is no autonomous market-data/paper worker yet.
- Existing deterministic risk sizing checks run on server-owned simulator cash,
  positions, reservations and immutable simulation policy at submission and again
  before buy fills: position/sector/open-risk/cash limits, realized daily loss,
  drawdown and consecutive-loss cooldown. Existing account-scoped controls kill
  switches are rechecked. A paper halt cancels pending buys and prevents entries;
  owned exits/cancellation remain available. Adding to a position cannot widen
  its planned stop. Fictional holdings and policy are not qualified reviews.
- Transactional, append-only API journal with command IDs and request hashes,
  chained entry hashes, fill references, actor and timestamps. Conflicting command
  ID reuse returns 409. Duplicate accepted commands return the original result.
  State, order and quote projections are reconciled against journal replay before
  each new mutation; drift blocks changes without automatic repair. Shared control
  locking serializes concurrent writes, including kill-switch races. This is
  internal simulator reconciliation, not external broker reconciliation. Database
  owners can alter records; hashes are not an independent tamper-proof signature.
- Authenticated workspace-wide read views; only the `operator` role can mutate,
  using server sessions and CSRF. Administrators do not implicitly acquire the
  operator role. Dashboard service keys are read-only here. The dashboard panel
  shows accounts, cash/holds/equity/P&L/fees, positions, orders and reconciliation.
  Controls for placing orders are available through authenticated API contracts;
  the dashboard is read-only in this first iteration.

## Run isolated acceptance without configuration

From the repository, after `uv sync --frozen`:

```sh
uv run python -m scripts.paper_smoke --output reports/generated/paper-simulator-smoke.json
uv run pytest -q tests/paper
```

The smoke runner creates and removes its own temporary SQLite database and ignores
production DATABASE_URL. It simulates 20 days/round trips with partial fills,
costs, duplicate-fill replay, daily reconciliation, final settlement and flat
holdings. It never calls a broker, emails or Telegram. Dates/prices are injected
synthetic fixtures: **20 simulated days are not 20 days of actual forward testing**.
Generated synthetic profit is not strategy performance evidence.

## Deploy and exercise the API deliberately

Default `PAPER_TRADING_ENABLED=false` keeps all simulator writes disabled. Apply
`alembic upgrade head` (`0008_paper_simulator`) before running the new API. Render's
existing startup migration command applies this automatically on deployment;
Vercel publishes the additional panel from the normal static build. No provider
credentials or hosting configuration were changed by this implementation.

To enable the internal simulator on a reviewed test deployment, set
`PAPER_TRADING_ENABLED=true` in the server environment, keep
`LIVE_TRADING_ENABLED=false`, and restart the API. An administrator can invite or
assign an operator using the existing account controls. Use that operator's
session/CSRF in the API; never paste cookies into chat or commit them.

New routes:

| Method | Path suffix under `/api/v1/paper` | Behavior |
| --- | --- | --- |
| GET | `/accounts` | Enabled flag and up to 100 account IDs |
| POST | `/accounts` | Create immutable synthetic account/universe/policy |
| GET | `/accounts/{account_id}` | Ledger, holds, orders and reconciliation |
| GET | `/accounts/{account_id}/journal?after=0&limit=50` | Cursor-paged journal |
| POST | `/accounts/{account_id}/quotes` | Record synthetic quote and mark holdings |
| POST | `/accounts/{account_id}/orders` | Submit buy/sell market/limit proposal |
| POST | `/accounts/{account_id}/fills` | Explicitly match one order against a later quote |
| POST | `/accounts/{account_id}/cancel` | Cancel unfilled remainder |
| POST | `/accounts/{account_id}/tick` | Settle due proceeds and expire orders |
| POST | `/accounts/{account_id}/halt` | Halt/resume synthetic entries |

Example bodies (field contracts are in `/docs`; command IDs must be unique per
account across all operations):

```json
{"account_id":"paper-demo","mode":"synthetic","initial_cash":"100000","universe":{"SYNTH":"technology"}}
```

```json
{"command_id":"buy-1","symbol":"SYNTH","side":"BUY","quantity":10,"order_type":"MARKET","stop_price":"95"}
```

A matching fresh quote is needed before submission for sizing. Fills require a
new quote observed and received after submission, then a fresh fill command ID
with the returned `order_id` and `quote_id`. An order does not fill merely because
it was accepted. Review `status` in every response: risk rejection/reconciliation
block is a domain result even with HTTP 200. SQL errors roll back the whole
command; retry with exactly the same ID/body after resolving connectivity. Never
reset fills or edit journal rows to force a retry. Current reconciliation replays
the account history, so this iteration is intended for bounded test accounts,
not high-throughput production use.

The notification worker can preflight either migration 0007 or 0008. Backup
verification supports both and compares the restored migration exactly to the
source snapshot. Earlier Milestone 7 evidence remains historical at migration
0007; it does not claim an operator backup or deployment test of this new schema.

## Remaining Milestone 8 release acceptance

The blueprint requires a simulated broker, lifecycle/reconciliation **and stable
forward testing with no critical operational violations**. This commit implements
the bounded simulator stage only. Still required:

1. Define and approve the forward protocol, instruments, data source/session
   suitability, observation period and operational violation thresholds. Keep
   earlier qualified-review, custody, source and performance gates explicit.
2. Implement the separately gated provider/decision-to-paper integration,
   autonomous processing/recovery, protective exits, market-session/calendar and
   any required corporate-action/settlement rules. No real order adapter is added.
3. Reconcile with an independently captured paper-broker state if an external
   broker is selected. The existing Alpaca adapter remains read-only; internal
   ledger replay is not evidence of external reconciliation.
4. Exercise restart/disconnection/stale-data/kill/cancellation recovery on the
   actual selected host and accumulate an actual elapsed forward run under the
   agreed protocol. Synthetic accelerated tests cannot close this requirement.

Milestone 9 remains disabled. Earlier milestone approvals are not inferred from
this simulator, and no source/compliance/performance gate is marked complete.

## Verified implementation checkpoint

[Final source CI](https://github.com/MohammedTeir/halal-quant/actions/runs/41185718212)
passed **585 tests** on PostgreSQL for source `28c148e`, including encrypted
backup/isolated restore and all **44 paper tests**. The local regression checkpoint
passed 583 with the two PostgreSQL-only checks skipped; focused timing-boundary
tests, lint/format, deployment tests and the English/Arabic/mobile Chromium smoke
also pass. The hosted accelerated paper smoke and existing offline research,
portfolio, Gemini-mock and evaluation steps passed.

Public GET checks observed ready responses from Render and the Vercel proxy, the
new dashboard panel, and 401 for an unauthenticated paper-account request. These
do not verify authenticated operator simulation on the deployment or establish
its exact Git SHA. No server flag was changed, and no new real email/Telegram
messages or external broker orders were submitted by this work. See the
[dated report](../reports/milestone8-paper-simulator-2026-10-31.json).
