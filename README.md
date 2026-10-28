# HALAL QUANT

Research-first, compliance-gated quantitative trading platform. This first increment
implements the backend foundation and drafts three Pine Script v6 strategies from
[the supplied blueprint](docs/blueprint-v2.md). **It does not authorize or execute trades.**
Live mode is rejected at configuration validation. No strategy has demonstrated the
research performance gates or received a Shariah approval.

## Current progress

Milestone 1 is implemented and locally validated. Milestone 2 has three strategy
scripts drafted, with TradingView compilation and replay acceptance pending.
Milestones 3–8 have not started; optional live integration (Milestone 9) is disabled.
This is one locally validated milestone out of nine, not a percentage estimate of
engineering effort or production readiness.

Validation recorded for the first increment: 29 tests pass on PostgreSQL, migration
upgrade/downgrade and schema checks pass, and the containerized API passes actual
HTTP ingestion/replay/audit and restart-persistence checks. A GitHub Actions workflow
is included; its hosted result has not been verified here.

See the [documentation guide](docs/README.md) for project specifications, architecture,
API contracts, strategy rules, compliance/risk requirements and operations. The
[milestone tracker](docs/milestones.md) is the source of truth for progress.

## Develop

Requirements: Python 3.12+, uv 0.12.23, Docker with Compose, and PostgreSQL 16.

```sh
cd /workspace/halal-quant
export UV_CACHE_DIR=/tmp/halal-quant-uv-cache
uv sync --frozen
cp .env.example .env  # only if .env does not already exist
# Set distinct random DASHBOARD_API_KEY and TRADINGVIEW_WEBHOOK_KEY in .env.
docker compose up -d --wait postgres
uv run alembic upgrade head
uv run uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

The default database credentials are for loopback-only local development. Override
credentials and configure TLS and access controls before deployment. Never expose
this development stack to the Internet. Missing API credentials deny access.

Alternatively, `docker compose up --build -d --wait` runs PostgreSQL, a one-shot
migration, and the API. `HALAL_CA_BUNDLE` selects a trusted CA bundle for container
builds (default: system bundle); keep the managed proxy configuration intact.
The Compose database volume persists across restarts. `docker compose down` stops
services; **do not use `down -v` unless intentionally deleting development data**.

## Validate

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Default tests use isolated SQLite files for fast local feedback. To exercise the
actual PostgreSQL dialect and migration upgrade/downgrade, create a **dedicated,
disposable** test database and use:

```sh
docker compose exec postgres createdb -U halal halal_quant_test
TEST_DATABASE_URL=postgresql+psycopg://halal:halal@localhost:5432/halal_quant_test uv run pytest -q
```

These integration tests downgrade tables between tests. Never point
`TEST_DATABASE_URL` at a database containing data you want to keep. CI uses a
fresh PostgreSQL 16 service. TradingView validation is a separate manual gate;
Python source checks do not compile Pine.

## Interfaces

- `GET /health/live`: process liveness and research mode.
- `GET /health/ready`: database, tables and migration revision readiness.
- `POST /api/v1/webhooks/tradingview`: `X-Webhook-Key` authentication; validated,
  recent, timezone-aware signals; durable event ID deduplication; audit logging.
- `GET /api/v1/signals` and `GET /api/v1/audit`: dashboard bearer credential,
  bounded `limit` of 1–100.
- `/docs`: generated API documentation.

Accepted candidates always return `authorized: false`. Same ID and payload is a
no-op; same ID with different payload returns 409. New signals older than 15
minutes or over 30 seconds in the future return 422. Entry and exit candidates
are technical observations, never broker orders. The freshness restriction on
webhook observations is not a protective-order or portfolio-risk policy.

See [milestones and acceptance evidence](docs/milestones.md),
[architecture](docs/architecture.md), [Pine validation](docs/pine-validation.md),
and [operations](docs/operations-runbook.md).

A real local API smoke check is available as `.venv/bin/python scripts/smoke.py`;
export the same dashboard and webhook credentials used by the running API. It writes
one clearly named synthetic `smoke:*` event and audit record to the development DB.
