# HALAL QUANT

Research-first, compliance-gated quantitative trading platform. The backend foundation
and three executable Python strategies follow [the supplied blueprint](docs/blueprint-v2.md).
Python is the primary research workflow; Pine Script is optional. **It does not authorize or execute trades.**
Live mode is rejected at configuration validation. No strategy has demonstrated the
research performance gates or received a Shariah approval.

## Current progress

Milestones 1–2 are implemented and locally validated. Milestone 3 includes
versioned facts, scoped feeds, earnings/actions and real split/session audits.
Free HistData XAUUSD bid history and the official Federal Reserve calendar now
provide validated gold/FOMC sample paths. An explicit exact-duplicate normalization now validates all 12 months of 2025,
retaining raw archives and removal proof. Session/source certification remains open. Volume is
explicitly unavailable for HistData.
Milestone 4 includes grounded Gemini generation and deterministic gates. A blind
real-source review exposed instruction and sentiment weaknesses. Prompt v5 passes
an unchanged 16-case regression and a separate 8-case fresh blind pilot. See the
[source and label review](docs/source-and-label-review.md): this is AI-assisted
review, not independent human sign-off or broad source-completeness certification.
A user-selected [separate AI technical review](docs/independent-technical-review-2026-10-29.md)
is now complete with conditional research-only acceptance. The [gold session audit](docs/gold-session-review.md)
records all 300 gaps without certifying unknown provider/holiday closures.
An additional external original-human-label sentiment benchmark passes 30/30;
[its research scope and limits](docs/external-label-evaluation.md) remain explicit.
Milestone 6 remains an early single-instrument research prototype.
[Milestone 5 now has a stored controls workflow](docs/milestone-5-operations.md): versioned review/policy/loss state, read-only broker capture, serialized research reservations and server decision revalidation. Qualified review and real cash/custody contract proofs remain required; execution is disabled.

[Milestone 6 research](docs/milestone-6-research.md) now includes shared-cash portfolio replay, training-only walk-forward selection, historical evidence gates and seeded trade-order Monte Carlo. Representative real-history and out-of-sample performance acceptance remain pending.
Milestones 7–8 have not started; optional live integration (Milestone 9) is disabled.

The full suite has **484 passing tests**, including research, data integrity,
advisory-output security and deterministic decision checks. All three
default strategies and cost-matched buy-and-hold baselines execute on synthetic
fixtures, finish flat, and reproduce reports byte-for-byte. These are software
acceptance checks, not evidence of real-world returns or paper-trading readiness.
GitHub Actions passed for commit `8afc05d`; verification of this follow-up follows
its push. See [source/label review](docs/source-and-label-review.md),
[gold acceptance](reports/gold-source-acceptance-2026-10-29.json) and
[the fresh v4 pilot](reports/real-primary-v4-fresh-pilot-2026-10-29.json).

The [first-four completion checklist](docs/first-four-acceptance.md) records the remaining
real-provider, coverage and independent model-quality gates. Setup commands are in
[data providers](docs/data-providers.md) and [model evaluation](docs/model-evaluation.md).

See the [documentation guide](docs/README.md) for project specifications, architecture,
API contracts, strategy rules, compliance/risk requirements and operations. The
[milestone tracker](docs/milestones.md) is the source of truth for progress.

## Start research without TradingView

After installing dependencies as below, run:

```sh
uv run python -m scripts.research_smoke --output reports/generated/first-run
```

This generates synthetic candles, runs the stock/ETF/gold strategies and baselines,
repeats each report, and checks reproducibility and end-of-window order state.
Choose a new output directory each time. No API, credentials or database is needed
for this research command. See [Python research](docs/python-research.md) for actual
CSV contracts, configurations, individual runs and model limitations.

## Develop

Research requirements: Python 3.12+ and uv 0.12.23. The API stack additionally
uses Docker with Compose and PostgreSQL 16.

```sh
cd /workspace/halal-quant
export UV_CACHE_DIR=/tmp/halal-quant-uv-cache
uv sync --frozen
test -e .env || cp .env.example .env
# Set four distinct keys in .env: DASHBOARD_API_KEY, TRADINGVIEW_WEBHOOK_KEY,
# DATA_INGESTION_KEY and ANALYSIS_API_KEY.
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
fresh PostgreSQL 16 service. Python strategy acceptance runs automatically;
TradingView validation is an optional manual gate. Optional Pine source checks do not compile Pine.

## Interfaces

- `GET /health/live`: process liveness and research mode.
- `GET /health/ready`: database, tables and migration revision readiness.
- `POST /api/v1/webhooks/tradingview`: `X-Webhook-Key` authentication; validated,
  recent, timezone-aware signals; durable event ID deduplication; audit logging.
- `GET /api/v1/signals` and `GET /api/v1/audit`: dashboard bearer credential,
  bounded `limit` of 1–100.
- `POST /api/v1/data/import`: separate `X-Data-Key` credential; atomic source batches.
- `GET /api/v1/news`, `/api/v1/economic-events`, `/api/v1/corporate-actions`: point-in-time facts.
- `GET /api/v1/data/status`: missing/stale/synthetic feed checks.
- `POST /api/v1/news/classifications`: grounded advisory assessments via `X-Analysis-Key`.
- `POST /api/v1/decisions/evaluate`: server-owned gates and immutable evidence snapshots.
- `GET /api/v1/news/classifications` and `/api/v1/decisions`: recorded analysis/history.
- `POST /api/v1/news/classifications/generate`: optional server-configured Gemini inference.
- `GET /api/v1/news/classification-jobs/{classification_id}`: durable generation status.
- `/docs`: generated API documentation.

Accepted candidates always return `authorized: false`. Same ID and payload is a
no-op; same ID with different payload returns 412. New signals older than 15
minutes or over 30 seconds in the future return 422. Entry and exit candidates
are technical observations, never broker orders. The freshness restriction on
webhook observations is not a protective-order or portfolio-risk policy.

See [milestones and acceptance evidence](docs/milestones.md),
[architecture](docs/architecture.md), [Pine validation](docs/pine-validation.md),
[data ingestion](docs/data-ingestion.md), [intelligence/decisions](docs/intelligence-decisions.md), and [operations](docs/operations-runbook.md).

A real local API smoke check is available as `.venv/bin/python scripts/smoke.py`;
export the same dashboard and webhook credentials used by the running API. It writes
one clearly named synthetic `smoke:*` event and audit record to the development DB.

The [advisory intelligence guide](docs/intelligence-decisions.md) explains source-bound
quotes, model-version history, event windows and fail-closed decisions. The optional
[Gemini adapter](docs/gemini.md) reads GEMINI_API_KEY and GEMINI_MODEL only on the
backend and stays disabled until GEMINI_ENABLED=true. No real Gemini call has been
used for the recorded acceptance tests. Public entry evaluations currently return WAIT_DATA; exits require
authoritative ownership. Neither a positive model output nor a perfect score can
provide missing compliance/risk/broker evidence or authorize trading.

Test Gemini integration without a key or charges:

```sh
uv run python -m scripts.gemini_mock_smoke --output reports/generated/gemini-mock.json
```

This uses a temporary database and mocked HTTP responses. For actual use, configure
your backend's ignored `.env` or deployment secrets; follow [Gemini setup](docs/gemini.md).
Never expose GEMINI_API_KEY to the frontend, source control or a client request body.

### Dashboard (Milestone 7 initial increment)

Open `http://127.0.0.1:8000/dashboard` after starting the API. Authenticate with your configured `DASHBOARD_API_KEY`; credentials stay in page memory. English is the default; choose العربية in the header for Arabic and RTL layout. Only the language preference is saved in browser storage. This read-only dashboard includes signal/decision views, broker observation freshness, research reports, audit and Telegram text previews. No messages are sent. See the [dashboard guide](docs/dashboard.md) or [Arabic guide](docs/milestone-7-dashboard.ar.md).
