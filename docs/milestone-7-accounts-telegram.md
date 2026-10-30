# Milestone 7: accounts and Telegram

The English-default dashboard now supports Arabic/RTL, invitation-only accounts,
server-side sessions, role administration, and persistent Telegram delivery.
Software acceptance and live deployment acceptance are separate. No public
registration endpoint exists. No mail service is invoked: invitations and password
recovery are **administrator-assisted links**, shared through your trusted channel.
Do not paste real credentials into this chat or commit them.

## Recovery investigation

The supplied checkout had a clean worktree at `3d45ad3`, no stashes, and no
unreachable objects reported by `git fsck --no-reflogs --unreachable`. Its reflog
contained older committed states, not the missing accounts/Telegram implementation.
Fetching `origin/main` confirmed `3d45ad3`. No tool exposed the unavailable prior
runtime or its uncommitted filesystem. The missing work was reimplemented here;
no environment was deleted, reconfigured, or published. Preserve any separately
accessible old runtime until this implementation is pushed and verified.

## Server setup

Install with `uv sync --locked`, configure `DATABASE_URL`, and run
`uv run alembic upgrade head` (`0007_access_delivery`). Back up the database first.
The migration is additive; downgrading it deletes account/delivery state, including
delivery deduplication records. Never downgrade/recreate these tables on a running
notification deployment. `/health/ready` requires the new revision and tables.

Serve the API and worker against the same persistent database. Use HTTPS and keep
`SESSION_COOKIE_SECURE=true` (default). Only for isolated localhost HTTP testing,
set it to `false`. Set `PUBLIC_BASE_URL` to your HTTPS application origin for CLI
links. Do not trust arbitrary forwarded client IP headers: login throttles use the
actual ASGI client address, so configure your trusted reverse proxy explicitly.
The default session lifetime is 12 hours; `SESSION_HOURS` allows 1–168 hours.

Bootstrap the first administrator on the server:

```sh
uv run python -m services.accounts.cli admin@example.com
```

The command refuses bootstrap if any account exists. Its output is a short-lived
one-time credential. Open the printed `/dashboard#recover=...` link privately and
set a password of at least 12 characters. The fragment is cleared immediately by
the dashboard and never sent to the web server as a URL. Do not store links in
logs/screenshots/tickets. If every administrator loses access, a server operator
can issue a recovery link for an existing enabled administrator:

```sh
uv run python -m services.accounts.cli admin@example.com --recover
```

In **Account & Telegram**, administrators invite users, assign roles, enable or
disable accounts, revoke sessions, and issue recovery links. Invitations expire
in 24 hours; recovery links in 30 minutes; CLI setup links in 30 minutes. A new
link of the same kind invalidates the earlier one. Redemption is serialized and
single-use, and consumes all outstanding links for that account. Disabled users
cannot redeem links or sign in. Password changes/recovery, disabling, and role
changes revoke existing sessions. Password changes also invalidate outstanding
links. The last enabled administrator with a set password cannot be removed.

Each user can list/revoke their sessions and change their password. Lock session
revokes the current server session and clears displayed data. Reload resumes a
valid cookie session; expired/revoked sessions fail closed. Cookies are HttpOnly,
SameSite=Strict and Secure by default. Every authenticated mutation also requires
the session's CSRF header. Only opaque session/token hashes and scrypt password
hashes are stored; session credentials never enter browser local storage.
Persistent per-client/account login budgets limit repeated attempts. Expired
sessions/tokens can be purged in maintenance; they are already rejected on use.

## Backend permissions

All enabled users can view the research dashboard and manage **their own** sessions
and Telegram destinations. Destinations and delivery history are account scoped.

| Role | Additional authority |
|---|---|
| admin | Invite, assign roles, disable users, revoke any user's sessions, issue recovery links |
| analyst | Existing analysis/classification/evaluation/control-check endpoints |
| reviewer | Existing control attestations and kill-switch clearing; actor is the account ID |
| operator | Engage kill switch and release reservations; actor is the account ID |
| broker_reader | Existing read-only broker and quote capture endpoints |
| viewer | No additional write authority |

Administrator authority does not silently grant qualified control-review powers.
Existing separate machine API keys remain supported for integrations. The service
key dashboard option remains available; a valid service key grants the previously
documented access. Leave `DASHBOARD_API_KEY` unset if all human access must use
accounts. A present session cookie must validate; an invalid cookie cannot fall
back to an API key. Account administration never accepts the shared dashboard key.
Roles do not provide compliance approval, execution authority, or milestone sign-off.

## BotFather walkthrough (your configuration required)

1. In Telegram open the verified **@BotFather** account and send `/newbot`.
2. Choose the bot's display name and a unique username ending in `bot`.
3. Copy the token directly into your **server secret manager** as
   `TELEGRAM_BOT_TOKEN`. Supply that secret to the worker process. Do not put the
   value in a dashboard field, Git, shell command/history, or browser storage.
   A local `.env` is ignored by Git but should be restricted to its server owner;
   a production secret manager is preferred. Revoke/rotate leaked tokens through
   BotFather and restart the worker with the replacement.
4. For a private chat, open your bot and press Start. For a group, add the bot
   and promote it to administrator. Keep BotFather privacy mode enabled; linking
   uses explicit `/link` commands. The sender must also be a group administrator.
5. This implementation uses `getUpdates` polling. Ensure no webhook or other
   consumer is configured for this bot. Remove a previous webhook through your
   approved Telegram administration procedure before starting this worker.
6. Start one supervised worker, with automatic process restart and sanitized logs:

   ```sh
   uv run python -m services.notifications.worker
   ```

   It requires outbound HTTPS to `api.telegram.org`. The web process does not need
   the bot token. `--once` is an operator diagnostic that **can make real Telegram
   calls and send queued notifications**; it is not a dry-run command.

No bot was created and no token or external environment settings were changed in
development. BotFather requires your Telegram account; these steps cannot be
completed by the repository alone.

## Link and enable a destination

Sign in, open **Account & Telegram**, and create a linking code. Send the displayed
`/link CODE` command to the bot in the intended private chat or group. The code is
valid for ten minutes, hashed on the server, and single-use. The worker accepts
only updates fetched from Telegram, never a user-supplied chat-ID verification
request. For private chats the sender and chat IDs must match. For groups the
worker asks Telegram for the sender's and bot's current administrator membership;
failed/unavailable verification leaves the code unconsumed. Channels are unsupported.
An existing linked chat cannot be taken over by another account; its owner must
unlink it first. Treat the linking code as a secret and delete it from group
history if appropriate.

Refresh settings to see the verified destination. Destinations begin **disabled**.
Choose English or Arabic and any of `signal`, `decision`, `risk_stop`, then enable.
A signal means a research trading candidate; a decision remains a research result;
risk-stop alerts are generated when a persisted kill switch is engaged, or a
stored server control check reports a kill switch, daily-loss limit, drawdown
limit or consecutive-loss cooldown. A new check is a new event; replaying the
same check does not enqueue another alert. These
messages do not authorize orders. New events are queued in their original database
transaction, with deterministic per-event/destination IDs. Historical records are
not automatically backfilled on linking. Text/language are frozen at enqueue time;
changing language affects future messages. Filtering/unlinking/disabling cancels
applicable queued/retry work. Disabling an account also cancels its pending work.
A send already in flight may still arrive. Unlinking hides that destination's
history from the user interface; retained outbox records remain in the database.

## Delivery behavior and operations

The separate worker commits an exclusive `SENDING` claim before network access.
Database write locks serialize claims on both PostgreSQL and SQLite. It paces all
sends at at most one per second, and each chat at one per three seconds. A confirmed
Telegram 429 with a valid `retry_after` delays the **whole outbox** until after that
window. Connection establishment/pool failures are safe to retry with a delay.
Safe retries stop after five attempts. The database and outbox survive web/worker
restarts; polling offsets are durable. Run one polling worker per bot to avoid
Telegram's competing-consumer conflicts. No webhook endpoint is exposed.

| State | Meaning / action |
|---|---|
| QUEUED | Persisted and waiting for worker |
| SENDING | Claimed; a network attempt may be in flight |
| SENT | Telegram confirmed success and supplied a message ID; this does not prove the recipient read it |
| RETRY | Confirmed rate limit or connection not established; bounded automatic retry |
| FAILED | Explicit Telegram rejection (400/401/403/404) or safe retries exhausted |
| UNCERTAIN | Timeout/write interruption/5xx/malformed response, or a claim abandoned for 120 seconds; **never automatically resent** |
| CANCELLED | Disabled/unlinked destination, disabled account, or removed notification type |

Delivery status, attempt count, and sanitized errors are available through
`GET /api/v1/telegram/deliveries`; the dashboard shows status/error/history.
Raw provider descriptions, token-bearing URLs and transport exception text are
never persisted as errors. If an outcome is uncertain, inspect the destination
and server evidence manually. There is deliberately no automatic or dashboard
resend button for uncertain messages. Monitor prolonged `SENDING`, `UNCERTAIN`,
`FAILED`, backlog growth and worker health. A crash before the API call may leave
an unsent message uncertain; avoiding duplicate delivery takes precedence.

## Verification and acceptance boundaries

Tests use temporary databases, fake Telegram adapters and `httpx.MockTransport`.
They do not start the worker automatically, call Telegram, or send email.
Automated checks cover token expiry/reuse, revocation, permissions/CSRF, owner
isolation, group verification, transactional event enqueue/deduplication, confirmed
success/rejection, safe retry caps, rate limits, parallel claims, crash uncertainty,
and prohibition on resending uncertain deliveries. Browser verification covers
English/Arabic, invitation/recovery, login, session reload/revocation, linking-code
creation, desktop and mobile. Run `uv run pytest -q` and the repository lint/format checks. The optional
`uv run python -m scripts.dashboard_browser_smoke` uses a temporary SQLite server,
fixture credentials and system Chromium; it requires Node with Playwright available
(`require("playwright")`) and `chromium` on PATH. It never starts a Telegram worker.
See the [dated acceptance report](../reports/milestone7-accounts-telegram-acceptance-2026-10-30.json) for exact results.

**Still required on your deployment:** persistent database backups, HTTPS/proxy
configuration, first administrator bootstrap, trusted sharing of invitation and
recovery links, BotFather/token secret setup, supervised worker, private/group
linking, and an explicitly approved real-message delivery check. Real provider
availability and real delivery are not certified by mocks. Milestone 7 therefore
has software acceptance with deployment delivery acceptance pending.

Earlier milestone evidence and open gates remain in [milestones](milestones.md),
[completion requirements](completion-requirements.md), and their linked reports.
The documented source/session, qualified compliance, operational cash/custody,
and untouched out-of-sample performance gates remain open. Nothing in account or
Telegram functionality supplies those approvals or starts milestone 8 trading.

New account/Telegram APIs are under `/api/v1/auth`, `/api/v1/admin` and
`/api/v1/telegram` in `/docs`. Administrators issue links through the dashboard;
API clients use `POST /admin/invitations` and
`POST /admin/users/{id}/recovery`. The returned raw token is shown once, then
redemption uses `POST /auth/recover`. No bot token is exposed by any endpoint.

For the selected Vercel/Render hosting with external Neon or Supabase PostgreSQL, see the [deployment walkthrough in Arabic](deploy-vercel-render.ar.md). Hosting account linking, secrets, actual service URLs and real-delivery acceptance remain operator steps.

For the selected temporary computer/Termux worker and @halalquant_bot, follow the
[worker setup guide](telegram-worker-computer-termux.md). Use `--check` for read-only
checks, then `--link-only` while verifying the destination. Neither setup mode
sends outbox messages. Full delivery remains an explicit later step.
