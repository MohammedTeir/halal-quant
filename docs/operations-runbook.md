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
Read-only acquisition and a restart-safe file worker are documented in
[data providers](data-providers.md). Real production coverage and scheduling are
unverified; current read
endpoints are bounded inspection views, not paginated archival exports.

## Advisory intelligence

Apply Alembic head `0003_intelligence` before readiness. ANALYSIS_API_KEY is a fourth
distinct credential for assessment/evaluation writes; it is not a broker key.
Optional NEWS_PROVIDER/CALENDAR_PROVIDER select server-side fact providers for
research snapshots; blank means unconfigured and neither setting verifies a source.
See [intelligence and decisions](intelligence-decisions.md).

For synthetic local HTTP acceptance, configure both provider IDs as synthetic_smoke
in the API environment and export four matching keys to the shell. Run
`uv run python -m scripts.decision_smoke --output reports/generated/new-decision-smoke.json`.
It persists offline-fixture assessments and blocked research decisions, never calls
a real model, and never authorizes orders. Choose a new output path. Positive
classification text must not be used to work around WAIT_DATA or WAIT_OWNERSHIP.
Those statuses reflect missing verified market/broker/compliance/risk/ownership
authorities, not a reason to inject approval flags into a request.

New model outputs require new classification IDs; they do not overwrite history.
Source corrections or expired assessments require a new classification. Exact
retries use the old receipt/result and do not refresh evidence. Downgrading to 0002
destroys model/decision tables but retains earlier facts/signals and audit logs.

## Gemini backend operations

Read [Gemini setup](gemini.md). Apply head `0004_gemini_jobs`. Set server-only
GEMINI_API_KEY, an account-available GEMINI_MODEL and GEMINI_ENABLED=true only when
you intend generation requests. No key or enablement is needed for automated mock
tests. Do not put the key in chat, Git, browser variables or an API body.

Compose mounts the host's trusted CA bundle at runtime and uses SSL_CERT_FILE for
HTTPS; preserve proxy settings and never disable verification. Restart/recreate
the API after changing its environment. Keep Gemini disabled for environment smoke
checks that should not contact the provider.

Generation records transition RUNNING → SUCCEEDED/FAILED; a crash may leave RUNNING.
Inspect the dashboard-authenticated classification-jobs endpoint before creating
another ID. Never implement a blind restart/expiry retry over ambiguous requests.
Read errors/timeouts can follow a billable provider execution. Failed grounding
never stores an assessment; available token usage can still be recorded.

`uv run python -m scripts.gemini_mock_smoke --output reports/generated/new-gemini-mock.json`
uses an isolated temporary DB, fixture key and MockTransport; zero real provider
calls. Existing generation IDs and output report paths must not be overwritten.
The jobs table is not an implemented scheduler/worker. Production quotas, operator
recovery and model-quality validation remain pending.

## First-four completion gates

Use [the acceptance checklist](first-four-acceptance.md) before marking the first
four milestones complete. Live provider acquisition and model evaluation are
explicit commands, never startup smoke tests. Keep their archives and inspect
failed/ambiguous runs before deliberately retrying. Enter provider credentials only
in backend/deployment secrets or secure environment settings. The cloud draft
contains the required destinations and secret requirements; saving a draft does
not activate access or publish a snapshot.
