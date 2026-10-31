# Internal forward campaign operations

This is an internal US stock/ETF cash simulator using read-only Alpaca IEX quotes.
No orders are sent to Alpaca. English remains the default; Arabic is available.
The operator must configure and review the campaign before enabling its worker.
No credentials, cloud configuration or source approvals were published by the
implementation. No real emails or Telegram messages were sent in its tests.

## Deploy and configure privately

1. Preserve an encrypted backup and a tested restore before upgrading. Pull the
   new source on the API host and phone, install frozen dependencies and apply
   `alembic upgrade head` (`0009_paper_forward`). Render's existing migration/start
   command performs this during deployment. Vercel uses the existing repository
   static build; it now includes `paper.js`. Verify `/health/ready` after deployment.
2. Update the existing Telegram worker source before restarting it: older
   preflight versions recognize only schemas 0007/0008. The current notification
   worker and backup utility accept 0007, 0008 and 0009. Preserve historical M7
   evidence; it does not prove a fresh operator backup on the new schema.
3. In the private API and Debian worker environments, set `PAPER_TRADING_ENABLED`
   and `PAPER_FORWARD_ENABLED` to `true`, retaining `LIVE_TRADING_ENABLED=false`.
   Defaults are both false. Restart processes after changing settings. Configure
   the worker's `DATABASE_URL`, `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` privately;
   use read-only access where supported. Keep credentials out of browser build
   variables, commands shared in chat, Git and reports. Provider hosts are fixed
   by code; the worker has no external order operation.
4. Keep the existing acquisition/scheduling, signal and classification/decision
   producers configured. The paper worker reads stored signals, decisions and
   news/calendar/FOMC/earnings/corporate-action evidence. It does not create these
   upstream inputs. See [data providers](data-providers.md),
   [intelligence](intelligence-decisions.md) and [controls](milestone-5-operations.md).
   Missing, synthetic, stale, unclassified or uncovered inputs block entries.

Deployment access and private source configuration are operator actions. A passing
local test does not establish that the phone or production has these settings.

## Create and review a campaign

Use administrator invitations for separate enabled `operator` and `reviewer`
accounts. Keep an administrator account for account management. Permissions are
backend enforced; assigning a role is not qualified compliance approval.

In the Paper dashboard as operator, create a **forward** account with immutable
virtual cash, symbol-to-sector universe, stock/ETF types, provider ticker mapping,
policy and settlement days (default T+1). Choose at most ten distinct US tickers.
Names are not recommendations or compliance screening. Match the stored asset,
methodology and policy reviews to the account's actual instruments and policy.

Propose a forward protocol using the dashboard form or authenticated session/CSRF
API. Its strict fields are visible in `/docs` (`ForwardProtocol`):

- `run_id`, `account_id`, provider `alpaca_iex`;
- `minimum_sessions` at least 20; `minimum_round_trips` default 10, minimum 3;
- cadence default 60 seconds, maximum allowed gap default 180 seconds;
- whole-share `quantity_per_decision` default 1, stop fraction default 0.05;
- `feed_providers`: exact stored provider IDs for `news`, `calendar`, `fomc`,
  `earnings`, `corporate_actions`;
- `data_review`: every named provider, including `alpaca_iex`, mapped to the SHA256
  of an actual reviewed evidence document; `source_limitations` and credential-free
  HTTPS evidence `references`; decision maximum age default 300 seconds.

Do not put dummy hashes or pretend approvals into a deployment. Review the IEX
coverage/entitlement, timestamp/session suitability, sector/class mappings,
corporate-action coverage and proposed observation thresholds explicitly. A
separate reviewer approves the exact returned protocol SHA, with explanatory note
and expiration within 90 days. Renewal/rejection is recorded; account/protocol
configuration is immutable. Use a new isolated account/run to change it.

Paper-scoped source review permits only the specifically reviewed
`PROVIDER_UNVERIFIED` assumption for that campaign. It does not change the global
source-verification flag, research decision authorization, earlier independent
source/compliance/performance acceptance or live execution authority. All other
freshness, news, event, ownership and risk gates still apply.

## Run on the configured phone

First use the Debian shell in `/root/halal-quant`, replacing `YOUR_RUN_ID` with the
reviewed ID. The check reads configuration/database only; it makes no provider
call, takes no worker lease and sends no messages:

```sh
.venv/bin/python -m services.paper.worker --run-id YOUR_RUN_ID --check
```

Require enabled/configured/current-review results before starting a new entry
campaign. For a foreground run, use the following once, then Ctrl+C to stop it
before installing supervision:

```sh
.venv/bin/python -m services.paper.worker --run-id YOUR_RUN_ID
```

For supervision run this in **main Termux**, not inside Debian. This assumes the
existing M7 Debian checkout, private environment and dependencies are installed:

```sh
pkg install -y proot-distro termux-services procps
export SVDIR="$PREFIX/var/service"
termux-wake-lock
. "$PREFIX/etc/profile.d/start-services.sh"
proot-distro login debian -- cat /root/halal-quant/infra/termux/install-paper-worker.sh > "$TMPDIR/halal-install-paper-worker.sh"
bash "$TMPDIR/halal-install-paper-worker.sh" YOUR_RUN_ID
for attempt in $(seq 1 20); do
  [ -p "$SVDIR/halal-paper/supervise/ok" ] && break
  sleep 1
done
sv-enable halal-paper
sv -w 30 up "$SVDIR/halal-paper"
sv status "$SVDIR/halal-paper"
```

The separate service is `halal-paper`; the Telegram worker remains `halal-quant`.
Never run a second foreground worker alongside it. Lease fencing prevents two
owners from committing, but duplicate processes are an operational problem.
The service termination hook forwards TERM through proot to Python; allow its
current transaction/read to finish. Stop/restart with full service paths:

```sh
sv -w 60 down "$PREFIX/var/service/halal-paper"
sv -w 60 up "$PREFIX/var/service/halal-paper"
```

Do not force kill a worker just to update code with pending orders. Halt entries,
review holdings and perform a controlled restart first. Android can terminate
Termux despite wake-lock/runit; this is not an uptime guarantee. Full-session
coverage may require a reliable always-on host. A short recent heartbeat cannot
prove future availability or receipt of a Telegram message.

## Observe, recover and finish

Export without provider calls or mutations, from Debian:

```sh
.venv/bin/python -m services.paper.status --run-id YOUR_RUN_ID
```

The dashboard exposes the same campaign report. Inspect blockers, worker state,
actual completed sessions, quote/source gaps, critical violations, reconciliation,
round trips and recovery. Source errors pause entries; usable fresh symbols can
still exit. Partial quotes never authorize new buys. Review expiry stops entries
but preserves protective management for previously approved campaigns. Keep the
worker running with positions. The database halt cancels pending buys and blocks
new risk across worker processes. Liquidation records owned-only exit intent;
it requires subsequent fresh regular-session quotes and is not an instant fill.
Disabling HTTP entry flags is not a substitute for a persistent halt.

Corporate-action policy excludes entries from three days before through one day
after known events and requests owned exits beforehand. A held position across
an effective known split/dividend event is critical, not silently adjusted.
Polling stops can gap; simulated T+1/calendar settlement is not real custody,
beneficial possession, exchange execution or real-world cash availability.

For recovery evidence, restart the supervised worker deliberately with an
unexpired pending order or owned position, then confirm a successful different
worker instance continues the same reconciled ledger. Source interruption,
stale data, cancellation, halts and lease failures are covered by isolated tests;
record actual host incidents/recovery separately. Do not fabricate outages, move
server clocks, alter journals or manufacture trades to satisfy counts.

Finalization requires at least 20 complete observed market sessions, at least 20
actual elapsed days, the reviewed completed-exit threshold, recorded restart
recovery, current reviews, recent worker evidence, matching ledger, no critical
violations, no open orders/holdings/unsettled proceeds. The operator finalizes in
the dashboard (or POST `/api/v1/paper/runs/{run_id}/finalize`). The resulting report
is frozen and hash-bound; later exports retain its acceptance-time scope. Archive
it privately and publish only a redacted evidence summary. Wait for genuine
coverage rather than lowering thresholds or counting accelerated fixtures.

## API additions

All suffixes are under `/api/v1/paper`; reads require authenticated workspace
access. Writes require a server session and CSRF. Operator owns account creation,
synthetic orders/quotes/fills, `/accounts/{id}/decision-orders`, cancellation,
tick, halt and `/accounts/{id}/liquidate`. Raw forward quotes/orders/fills are
worker-only. `/runs` GET lists protocols/configuration and POST proposes one;
`/runs/{id}` GET reports evidence; `/runs/{id}/review` POST requires the distinct
reviewer; `/runs/{id}/finalize` POST requires operator. See `/docs` for exact bodies.

A 200 response can contain a domain rejection or unmet acceptance; inspect the
returned status/blockers. Do not retry with new IDs to bypass deduplication.
Milestone 8 remains in progress until genuine forward acceptance is recorded;
Milestone 9 remains disabled.

## Prepared ten-company candidate account

The user delegated choosing ten companies. The prepared
[account draft](../examples/paper/largecap-account-draft.json) contains AAPL, NVDA,
MSFT, GOOGL, AMZN, TSLA, META, AVGO, LLY and MU. These are the ten largest reported
market capitalizations within an explicit 18-company US non-financial shortlist,
using read-only Finnhub profiles observed October 31. This is not an exhaustive
all-market ranking. Profile observation time is not proof of the underlying
financial data's as-of date. See the [selection evidence](../reports/milestone8-candidate-universe-2026-10-31.json).

The file is a draft API body, not a created account or approved universe. Its
methodology is deliberately unset. Select and review the methodology/policy and
instrument screening before creating the immutable account; do not simply submit
it and attempt to bypass blockers. A large market cap does not prove compliant
business activity, financial ratios, purification or settlement/possession.

A read-only development-environment Alpaca clock/calendar probe passed; the next
reported regular session is November 2, 2026. It does not verify the phone's
credentials, production database access, quote freshness or feed coverage.

To discover the actual phone deployment's next blockers, run in main Termux:

```sh
proot-distro login debian -- bash -lc 'cd /root/halal-quant && git pull --ff-only && .venv/bin/python -m services.paper.preflight'
```

This inventory does not change flags, apply migrations, create accounts, acquire
leases, contact providers or send messages. Its output omits credential values,
URLs and user identities and can be shared for diagnosis. Configuration present
is not source coverage or forward acceptance. A campaign still needs actual
elapsed sessions and reviews; a missing production binding here cannot be fixed
by connecting the worker to a disposable development database.
