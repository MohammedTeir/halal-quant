# Architecture

A modular monolith: FastAPI ingress, explicit Pydantic contracts, SQLAlchemy storage,
Alembic migrations, and pure Python indicators. PostgreSQL is the system of record.
The first migration intentionally creates only signals and audit logs. Domain
schemas will be added alongside their implementations rather than creating empty
trading subsystems that imply unimplemented guarantees.

`apps/api` owns HTTP authentication, ingestion, and reads. `packages/schemas`
owns the shared candidate contract; `packages/config` owns configuration and the
live-mode guard; `packages/indicators` owns causal reference calculations. `pine`
contains independently configurable TradingView strategies. `services` reserves
future module boundaries; there is no worker or broker adapter yet.

Flow: closed chart bar → technical candidate → authenticated ingress → validated
signal and audit transaction. Later milestones add authoritative point-in-time
data, intelligence, compliance, risk and a decision engine **before** paper order
authorization. Dashboard, Redis, Telegram, workers and live adapters are deferred
according to the milestone tracker.

A dashboard credential grants read access; the separate webhook credential grants
only ingestion. These development service credentials are not production RBAC or
session management. Database errors fail readiness. Event IDs provide atomic
idempotency through the primary key and transaction rollback on races. Database
and audit tables are not immutable against administrators; production retention,
backup, access policy and tamper resistance remain future work.

The supplied blueprint is the design source. Provider, broker, gold ownership
structure and scholarly screening methodology remain unselected. The platform
must not invent those approvals or treat a chart's ticker as verified ownership.
