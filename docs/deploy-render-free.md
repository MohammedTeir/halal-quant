# Free Render API deployment (without Blueprint)

Use this path for a free web service. The repository's `render.yaml` describes
paid starter services; do not use it for this setup. Vercel hosts the static
frontend, and Neon or Supabase stores PostgreSQL data outside Render.

## Create the API manually

In Render choose **New → Web Service**, connect GitHub, and select
`MohammedTeir/halal-quant`:

| Setting | Value |
|---|---|
| Branch | `main` |
| Language/runtime | Python |
| Root directory | Repository root (leave empty) |
| Instance type | Free |
| Build command | `pip install uv==0.12.23 && uv sync --frozen --no-dev` |
| Start command | `.venv/bin/alembic upgrade head && .venv/bin/uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT` |
| Health check | `/health/ready` |

Free services do not provide the paid pre-deploy command, so the single API
instance applies migrations before starting. Do not run another migration process
at the same time. Back up existing databases before deploying schema changes.

Set these environment variables in Render's dashboard:

| Variable | Value |
|---|---|
| `PYTHON_VERSION` | `3.12.12` |
| `DATABASE_URL` | Your secret external Neon/Supabase PostgreSQL connection string |
| `SESSION_COOKIE_SECURE` | `true` |
| `PUBLIC_BASE_URL` | `https://localhost` initially; replace with the actual HTTPS Vercel origin before administrator setup |
| `GEMINI_ENABLED` | `false` |
| `LIVE_TRADING_ENABLED` | `false` |

Do not add the bot token to the API or any secrets to Vercel. Keep shared API keys
unset unless explicitly configuring a machine integration. See the
[provider connection notes](deploy-vercel-render.ar.md#1-قاعدة-البيانات) for Neon
Direct connections or Supabase Session pooler connections.

Deploy and check `https://YOUR-API.onrender.com/health/ready`. Share only the public
Render API URL so the Vercel rewrites can be configured. Continue with the
[Vercel instructions](deploy-vercel-render.ar.md#4-تحديد-عنوان-render-وربط-vercel).

## First administrator without Render Shell

Render's free web service does not include the paid interactive Shell. Run the
existing administrator CLI on a trusted local computer with this repository and
its dependencies installed. Configure the same external `DATABASE_URL` and actual
Vercel `PUBLIC_BASE_URL` in a private, ignored local `.env` file, then run:

```sh
uv sync --locked
uv run python -m services.accounts.cli YOUR_ADMIN_EMAIL
```

This command accesses the shared external database; do not point it at a separate
local database. Open the printed link privately to set the password. Keep the
connection string and one-time link out of chat, screenshots, Git and shared logs.
There is no public registration or bootstrap endpoint.

## Telegram and free-tier limits

A free Render web service sleeps when idle and cannot provide reliable continuous
background polling or timely notifications. PostgreSQL state survives because it
is external; the web service's own filesystem is temporary.

Render background workers require a paid plan. Do not run the Telegram worker in
the web start command or add artificial keep-alive requests to bypass sleeping.
To finish live Telegram acceptance, use either a paid Render worker or another
server you control that can run the existing worker continuously with the same
external database. Keep its bot token in that server's secret settings. Account
and outbox software remains available while the worker is absent, but delivery
and new linking-code verification will wait for a worker.

This free API setup therefore does **not** complete Milestone 7's real-delivery
acceptance. No real messages are sent by following the API-only setup. Choose and
configure the worker host before enabling destinations and approving a concrete
real-message acceptance check.

### From a phone: Neon SQL Editor instead of a local terminal

A privileged database operator can bootstrap a **new, empty account table** using
[infra/sql/bootstrap_admin.sql](../infra/sql/bootstrap_admin.sql). This is an
alternative to the CLI, not an additional account to create after CLI bootstrap.

1. In Render API environment settings, set `PUBLIC_BASE_URL` to
   `https://halal-quant.vercel.app` (without `/dashboard`) and save/redeploy.
2. In Neon open the SQL Editor for the **same database/branch used by Render**.
3. Paste the entire SQL file. Replace only `YOUR_ADMIN_EMAIL` in the final SELECT
   with your administrator email. The default site origin matches this deployment;
   change it only if deliberately deploying to a different HTTPS origin.
4. Run the whole script once. Open its returned `setup_link` privately within
   30 minutes, choose a password in the dashboard, and sign in. No email is sent.
5. If any account already exists, the script refuses bootstrap. Do not delete
   users to bypass that guard. Use existing administrator recovery instead.

The helper function exists only in the SQL connection's temporary schema and
runs with the SQL operator's existing permissions. It uses the application's
access lock, stores a SHA-256 token hash, and creates an administrator with no
usable password until single-use redemption. It logs the account ID but never
writes the raw setup token into application audit logs. The link is returned only
to your SQL Editor result: do not share that result or screenshots containing it.
The SQL text contains no database connection string or account password.
