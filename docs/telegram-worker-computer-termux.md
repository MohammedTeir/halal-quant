# Telegram worker on your computer or Termux

Deployment: `https://halal-quant.vercel.app`, bot **@halalquant_bot**, and the same
Neon PostgreSQL database already connected to Render. The worker connects directly
to PostgreSQL and Telegram. It does not keep Render awake and does not require a
paid Render worker. One polling worker per bot must run at a time.

An always-on computer is preferable. Android can stop Termux, even with a wake
lock or disabled battery optimizations. Phone hosting is temporary and does not
prove continuous or timely alert delivery. Actual Termux/Android installation
has not been tested in this development environment.

## Existing computer

Install Git, Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Then, in a terminal:

```sh
git clone --branch main https://github.com/MohammedTeir/halal-quant.git
cd halal-quant
uv sync --frozen --no-dev --python 3.12
```

If you already have a checkout, preserve any local work and use
`git pull --ff-only` instead of cloning over it. For a private repository,
authenticate to GitHub on your own device; do not paste a GitHub token into chat
or embed it in the clone URL.

Continue at **Private worker settings** below. On Windows run the worker with
`uv run --no-sync python ...` in place of `.venv/bin/python ...`.

## Termux: use Debian instead of Android-native Python packages

The application includes packages with compiled dependencies. Installing them
directly into Android's native Python can fail or require lengthy Rust/C builds.
Use Debian under `proot-distro` so the normal Linux wheels can be used.

Install Termux from its [official F-Droid listing](https://f-droid.org/packages/com.termux/).
In the **Termux shell** run:

```sh
pkg update
pkg install proot-distro tmux
proot-distro install debian
termux-wake-lock
tmux new -s halal-worker
proot-distro login debian
```

Now, **inside Debian**, run:

```sh
apt update
apt install -y git python3 python3-venv ca-certificates nano
python3 -m venv /opt/halal-tools
/opt/halal-tools/bin/pip install uv==0.12.23
git clone --branch main https://github.com/MohammedTeir/halal-quant.git
cd halal-quant
/opt/halal-tools/bin/uv sync --frozen --no-dev --python 3.12
```

`uv` can download Python 3.12 if Debian's default Python is older. The Debian
installation and Python dependencies require storage and an initial download.
If installation fails, share only the error after removing credentials; do not
replace this with a native Android `pip install` of the entire project.

Disable battery optimization for Termux in Android settings and keep a stable
connection. Frequent database polling can keep Neon compute active and consume
your plan's compute allowance; review Neon usage for a worker that runs for long
periods. To detach tmux, press **Ctrl+B**, then **D**. To return later, use
`tmux attach -t halal-worker` in the Termux shell. A wake lock does not guarantee
that Android will keep the worker running or that Wi-Fi/mobile data stays connected.

## Private worker settings

Create a `.env` file **inside the cloned repository on the worker device**, not on
Vercel. Use a local text editor; do not put secrets in shell commands/history.
On Linux/Termux Debian, for a new `.env`:

```sh
umask 077
nano .env
```

Enter these two settings with the real values privately:

```dotenv
DATABASE_URL=YOUR_EXISTING_NEON_POSTGRESQL_CONNECTION_STRING
TELEGRAM_BOT_TOKEN=YOUR_BOTFATHER_TOKEN_FOR_HALALQUANT_BOT
```

In nano, save with **Ctrl+O**, Enter, then exit with **Ctrl+X**. Then run:

```sh
chmod 600 .env
```

Use the **same database/branch as Render**, with its existing `sslmode=require`
and `channel_binding=require` options. Do not create a fresh local SQLite database
or run migrations from this worker. The API deployment manages migrations.
The `.env` file is ignored by Git. Do not share it, its contents, or screenshots
showing its values. On Windows restrict the file to your local account using file
permissions. Keep the computer/device and its backups private.

## Step 1: read-only check (no messages, no consumed updates)

```sh
.venv/bin/python -m services.notifications.worker --check --expected-bot halalquant_bot
```

This checks the database revision/worker state, reads the number of queued/retry
messages, verifies `getMe` identifies **@halalquant_bot**, and checks for an existing
webhook. It does not call `getUpdates`, create/claim outbox messages, or send any
message. A successful result includes:

```json
{"database":"ready","bot":"@halalquant_bot","pending_messages":0,"webhook":false,"messages_sent":0}
```

Your pending count may differ. Review it before enabling full delivery. Existing
webhooks or the wrong bot cause a failure; the check never removes a webhook for
you and never prints a webhook URL, database password or bot token.

## Step 2: link-only worker (still no message delivery)

```sh
.venv/bin/python -m services.notifications.worker --link-only --expected-bot halalquant_bot
```

Leave this running. It consumes Telegram updates and verifies linking codes,
but **never calls the outbox delivery function**.

1. Open [@halalquant_bot](https://t.me/halalquant_bot) and press **Start**.
2. In the Vercel dashboard open **Account & Telegram → Create Telegram linking code**.
3. Send the displayed `/link CODE` to the bot's private chat within ten minutes.
4. Refresh settings in the dashboard. The verified destination should appear,
   initially disabled. A group requires you and the bot to be administrators.
5. Choose notification language/types, but keep the destination disabled until
   the real-message acceptance destination and event have been agreed.

No confirmation message is sent by the bot during linking; the dashboard is the
confirmation. Do not share the linking code or use two polling workers at once.

## Step 3: preview and explicitly authorize one setup message

The setup check writes only a clearly labelled outbox record. It does not insert
trading signals, decisions, broker facts or risk-stop records. It uses one of the
destination's selected notification categories so normal preference checks still
apply. Its deterministic ID permits only one setup record per linked destination.

From the repository, preview the text without creating an outbox record or
calling Telegram (replace CHAT_ID with the verified destination shown in settings):

```sh
.venv/bin/python -m services.notifications.setup_check --chat-id CHAT_ID --expected-bot halalquant_bot
```

After approving that one real message, enable the verified destination in the
dashboard, select at least one notification type, and save. Stop the link-only
worker with Ctrl+C if it occupies your terminal. Then explicitly opt in:

```sh
.venv/bin/python -m services.notifications.setup_check --chat-id CHAT_ID --expected-bot halalquant_bot --send
```

**The `--send` command sends a real message.** It verifies the bot identity and
absence of a webhook, queues the setup check, and attempts delivery of only that
record. It cannot drain other queued events or destinations. It respects the
existing global/chat rate limits and conservative uncertainty rules. It does not
start a continuous delivery loop.

The English message is:

> HALAL QUANT: This is a one-time notification setup check. Not a trading signal or order.

Arabic is used if selected for the destination. A successful result has `SENT`
and a Telegram `message_id`. Verify the message in the private chat and refresh
dashboard delivery history. Repeating the exact command never creates a second
setup record and never resends `SENT` or `UNCERTAIN` messages. `QUEUED` or `RETRY`
can be retried later with the same command; `UNCERTAIN` must be investigated,
never reset to queued. A confirmed terminal failure is retained for review.

## Step 4: normal ongoing delivery

Once the approved setup check has been received and ongoing notifications are
wanted, run the regular worker:

```sh
.venv/bin/python -m services.notifications.worker --expected-bot halalquant_bot
```

This command **can send all queued messages** to enabled destinations, including
normal events waiting while the worker was in link-only mode. Review pending
messages and preferences first. Never run two polling workers for the same bot.
Never manually reset `SENDING`/`UNCERTAIN` records to queued to force resend.
After an interruption, restart using the same database; abandoned sends remain
uncertain and are not automatically repeated.

A laptop that sleeps or a phone that is suspended stops polling and delivery.
Restart after resolving connection failures. For permanent operation, use an OS
service supervisor on an always-on computer/server. One approved setup delivery was operator-confirmed on Termux (`SENT`, message ID
`4`, one attempt). Ongoing hosting reliability remains unverified. Automated
development tests sent no real email or Telegram messages; the live setup check
was a separate, explicit operator action.
