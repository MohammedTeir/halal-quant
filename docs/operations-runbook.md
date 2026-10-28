# Development operations

Use the existing checkout: each cloud task is already isolated; do not create a
Git worktree unless explicitly requested. Install from the frozen uv.lock. Apply
`uv run alembic upgrade head` in the repository root before starting the API.
`uv run alembic check` detects model/migration drift. Readiness must return 200;
a listening port or liveness response does not prove the schema is ready.

Container path: `docker compose up --build -d --wait`. Native path: start the
Compose postgres service, migrate, then run Uvicorn as shown in README. Processes
must restart in new tasks; installed dependencies and files are reusable. Keep
credentials external and distinct; blank credentials deliberately fail closed.
The system refuses `LIVE_TRADING_ENABLED=true`.

On ingestion failure check authentication, UTC bar close, freshness (15 minutes),
schema version and event ID conflicts. Retry the identical payload to avoid duplicate
audits. Do not rename events just to bypass deduplication. Ingestion does not pass
any compliance or risk gate and cannot create orders.

Check `docker compose ps`, `docker compose logs api migrate postgres`, and readiness
for startup diagnosis. Do not log authentication headers, URL credentials or process
environments. Migrations run once before API startup in Compose. Before a future
schema upgrade, back up the database and test restoration; downgrade destroys the
first increment's tables. CI databases are disposable; development data is not.

Production remains blocked on RBAC/session security, trusted webhook gateway,
rate/body limits, durable audit controls, backup/restore verification, monitoring,
provider and compliance decisions, research acceptance and paper reconciliation.

## Python research

The research CLI needs neither running services nor authentication. After frozen
dependency installation, run `uv run python -m scripts.research_smoke --output
reports/generated/new-run` in the repository root (on one line). Choose a new
output path to preserve experiments. See [Python research](python-research.md) for
individual strategies, historical CSV metadata, costs and date limits. Reports
and input datasets are separate from the API database and are not submitted as
orders. Generated data/reports are ignored by Git and excluded from Docker context.

## Versioned data ingestion

Keep DATA_INGESTION_KEY distinct from dashboard/webhook keys and outside source
control. Apply Alembic head (`0002_data_events`) before readiness. New data-fact
tables do not replace signal/audit tables. See [data ingestion](data-ingestion.md)
for import examples, timestamp rules, split audits and feed-state interpretation.

Run `uv run python -m scripts.data_smoke --output reports/generated/new-data-smoke.json`
with matching dashboard/data credentials exported to test actual local HTTP imports.
It persists clearly labelled synthetic facts; they never authorize trading. Reusing
a batch ID is a replay and does not act as a new health heartbeat. A new successful
poll requires a new ID. Never falsify receipt time to make historical replay pass.

Back up data before schema changes. Downgrading to 0001 deletes imported fact/feed
observations, while preserving signal/audit tables; full downgrade deletes those too.
Production providers and failure/retry workers are not connected, and current read
endpoints are bounded inspection views, not paginated archival exports.
