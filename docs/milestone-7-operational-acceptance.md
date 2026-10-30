# Milestone 7: finish the deployed acceptance checks

The UI, backend permissions, sessions, expiring links and persistent Telegram
outbox are implemented and tested. Vercel/Render reachability, owner login,
Termux preflight, private destination verification and one received setup message
are already evidenced. This guide covers the remaining operator-owned checks.
It does not treat the existence of scripts or mock tests as live acceptance.

All commands below run on your own Termux/Debian host using its existing private
`.env`. The agent has no copy of your Neon credentials, bot token or owner
password and cannot run these commands on your device remotely. Do not paste
those credentials into chat. Reports contain summaries, never cookies/passwords.

## 1. Deployed accounts and session controls

From the main Termux shell:

```sh
proot-distro login debian -- bash -lc 'cd /root/halal-quant && git pull --ff-only && .venv/bin/python -m services.operations.live_accounts --run'
```

This explicitly creates disposable `@acceptance.invalid` accounts, authenticates
through the actual HTTPS Vercel origin, and tests cookie flags, CSRF, invitation
single-use/expiry, recovery single-use/expiry, password revocation, session
revocation, disablement, all six backend roles, logout and no public registration.
No emails or Telegram messages are sent. It does not request the owner's password.
The runner is pinned to `https://halal-quant.vercel.app` so its temporary admin
credentials cannot accidentally be posted to another host.

The runner removes only its own fixture accounts, sessions, tokens and any
fixture destinations/outbox records in `finally`, retaining an audit cleanup
entry. It never deletes real user accounts or changes their roles/passwords.
Keep real-user administration unchanged while it runs. It requires an existing
active owner administrator and refuses unsafe cleanup if that owner is removed
concurrently. Do not interrupt the run; if it fails, report the sanitized error
and inspect fixture cleanup before retrying. If login throttling returns 429,
wait for the budget to reset rather than resetting production counters.

Success: `status: PASSED`, all checks true and `temporary_accounts_removed: true`.
This is live HTTP acceptance, separate from isolated CI tests.

## 2. Encrypted backup and actual isolated restore

Inside Debian, install the tools once:

```sh
apt update
apt install -y age postgresql-client
cd /root/halal-quant
.venv/bin/python -m services.operations.backup --run
```

Use PostgreSQL clients matching your server major version for this same-version
restore test. The runner automatically selects matching Debian binaries under
`/usr/lib/postgresql/VERSION/bin` if installed. A version mismatch
is reported without connection credentials; install the matching official
PostgreSQL client before retrying. The operator role must have permission to
create a temporary database in the same PostgreSQL project/branch.

The command exports one read-only repeatable-read snapshot, uses `pg_dump` custom
format, encrypts it with `age`, decrypts into a private temporary directory, and
actually restores into a newly generated `hq_restore_*` database. It compares
all non-system table row counts against the exported snapshot and checks the
application migration revision, then removes only that temporary restore DB.
The source database is never a restore/clean/drop target. Plaintext temporary
archives are removed on normal completion; keep the private backup directory
private if a process/device is abruptly killed during a backup.

DB passwords are passed to libpq in the child environment, never command-line
arguments. Remote database backups require TLS. Archives and key files live
outside the checkout under `~/halal-backups`, with private permissions. Neither
file belongs in Git, Vercel, a public URL, chat or screenshots.

Success: `status: PASSED`, `snapshot_row_counts_match: true`,
`temporary_restore_database_removed: true`, `source_database_restored_over: false`.
If Neon disallows temporary database creation, the backup is not counted as
restore-verified; arrange an isolated target/branch with your provider instead.

**Backup arrangement is not complete until you copy the `.dump.age` archive to
private off-device storage and keep `backup-key.txt` separately and privately.**
The key is necessary for recovery. Never share the entire backup folder, since
it contains that key. This command does not confirm Neon plan retention/PITR,
create paid storage or upload anything. Confirm the off-device copy or your
provider-managed recovery retention separately. Choose a backup schedule and
repeat restore verification after material schema changes.

## 3. Supervise the worker on Termux

A tmux session keeps a terminal alive; it does not restart an exited worker.
Install Termux's supported runit supervisor for process restart. First stop the
old worker with Ctrl+C, so only one polling process uses this bot.

In the **main Termux shell**, not Debian:

```sh
pkg install termux-services procps
exec bash -l
```

After the shell restarts, update and install the service:

```sh
proot-distro login debian -- bash -lc 'cd /root/halal-quant && git pull --ff-only'
proot-distro login debian -- cat /root/halal-quant/infra/termux/install-worker.sh > "$TMPDIR/halal-install-worker.sh"
bash "$TMPDIR/halal-install-worker.sh"
termux-wake-lock
sv-enable halal-quant
sv status halal-quant
```

The installer refuses a nested Debian shell, existing unmanaged worker process,
or missing supervisor tools. It writes one disabled service, never embeds tokens
in its run command, and rotates a small private log under
`$PREFIX/var/log/sv/halal-quant`. Starting the service permits normal delivery of
selected queued notifications. `sv down halal-quant` stops it;
`sv-disable halal-quant` also disables automatic startup.

Check activity, perform a controlled restart, and check again:

```sh
proot-distro login debian -- bash -lc 'cd /root/halal-quant && .venv/bin/python -m services.operations.worker_status'
sv restart halal-quant
```

Allow a successful loop, then run a bounded observation (ten minutes):

```sh
proot-distro login debian -- bash -lc 'cd /root/halal-quant && .venv/bin/python -m services.operations.worker_status --observe-seconds 600'
```

Success: `PASSED`, worker state `RECENT`, mode `delivery`, and
`restart_observed: true`. Heartbeats are persisted after successful poll/worker
loops, at most every 15 seconds. `STALE` means no successful activity for over
90 seconds. `UNKNOWN` means no heartbeat yet; a one-off/check mode does not claim
continuous activity. The dashboard exposes the same authenticated status.

This demonstrates a bounded awake-device interval and process restart, **not**
unlimited future uptime. Android can kill the entire Termux app, and runit cannot
restart an app killed by the OS. Disable battery optimization, keep power/network
available, and reopen Termux after OS termination/reboot. Temporary Android
hosting remains an explicit deployment limitation, not a paid-server guarantee.
Frequent polling may keep Neon compute active and consume your plan allowance.

## 4. Approved private and group delivery coverage

The user approved four labelled messages to the existing private chat: signal,
decision, risk-stop and Arabic. These are **transport/category checks**, not real
market events; no source trading records, decisions or risk state are created.
The actual producer-to-outbox paths are covered by isolated application tests.

Preview without sending:

```sh
.venv/bin/python -m services.operations.live_notifications --chat-id PRIVATE_CHAT_ID
```

After the approved destination is enabled and all three types selected/saved:

```sh
.venv/bin/python -m services.operations.live_notifications --chat-id PRIVATE_CHAT_ID --send
```

It sends at most the four deterministic case records for that destination,
obeys rate limits, and cannot drain other queued events. Re-running does not
create duplicates or resend SENT/UNCERTAIN cases. It stops on failure or
uncertainty. It can wait up to 90 seconds for safe delivery/rate-limit pacing;
QUEUED/RETRY may need a later retry using the identical command.

For the group, first the user creates/chooses it, makes themselves and the bot
administrators, links it using a fresh code, and confirms the displayed negative
chat ID. Only after that target is confirmed and enabled, add:

```text
--group-chat-id CONFIRMED_NEGATIVE_GROUP_ID
```

This permits one separately labelled group setup message after the private
suite passes, not a broadcast or automatic group discovery. No messages are
sent to an unlinked/disabled destination. Record SENT/message IDs and recipient
confirmation; group membership/admin checks occur during the real linking flow.

## 5. Dashboard proof and final record

In **Account & Telegram**, click **Refresh settings** and **Verify delivery
history**. The button makes authenticated read-only requests and returns a
sanitized summary of setup history, suite case history, worker mode/activity,
restart observation and interface language. It contains no email, password,
link code, cookie or bot token. Share only that summary and CLI result JSON.
Confirm the Arabic message renders correctly in Telegram. English remains the
default application language, with Arabic/RTL available.

Final evidence must distinguish:

- Isolated CI acceptance from operator-run checks on the live deployment.
- Private/group recipient confirmation from Telegram's API `SENT` response.
- A bounded supervised Termux run from future always-on reliability.
- An encrypted restore-tested archive from its off-device storage/retention.

Until actual operator outputs and the confirmed group target are available,
these remaining deployment checks stay pending. No earlier milestone approval,
compliance/source/performance gate, or real-order authority is granted here.
