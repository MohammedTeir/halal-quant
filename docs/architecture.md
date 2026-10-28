# Architecture

A modular monolith: FastAPI ingress, explicit Pydantic contracts, SQLAlchemy storage,
Alembic migrations, and pure Python indicators. PostgreSQL is the system of record.
The first migration creates signals and audit logs; the second adds immutable
news/calendar/corporate-action revisions and successful data-import observations.
The third migration adds immutable model classifications and recorded decisions. Domain
schemas will be added alongside their implementations rather than creating empty
trading subsystems that imply unimplemented guarantees.

`apps/api` owns HTTP authentication, ingestion, and reads. `packages/schemas`
owns the shared candidate contract; `packages/config` owns configuration and the
live-mode guard; `packages/indicators` owns causal reference calculations. `pine`
contains optional independently configurable TradingView strategies.
`services/market_data` validates CSV provenance, audits split adjustments and
atomically stores versioned source facts;
`services/technical_signals` calculates causal Python strategy candidates;
`services/backtesting` runs single-instrument experiments through Backtesting.py.
`services/news_intelligence` normalizes attribution URLs and groups point-in-time
news observations; `services/macro_intelligence` reads calendar revisions. These
modules now validate source-bound advisory output and calendar facts.
`services/decision_engine` applies deterministic event restrictions and mandatory
research gates, preserving a complete decision snapshot. No real LLM is connected;
classification adapters currently have only a text-in/text-out boundary and fixture tests.
There is no acquisition worker, portfolio research engine or broker adapter yet. The research
CLI is independent of HTTP ingestion and cannot authorize paper orders.

Flow: closed chart bar → technical candidate → authenticated ingress → validated
signal and audit transaction. Later milestones add authoritative point-in-time
data, intelligence, compliance, risk and a decision engine **before** paper order
authorization. Dashboard, Redis, Telegram, workers and live adapters are deferred
according to the milestone tracker.

A dashboard credential grants read access; the webhook credential grants only
technical signal ingestion; a third data credential grants source-fact imports,
and a fourth analysis credential grants classification/evaluation writes. These development service credentials are not production RBAC or
session management. Database errors fail readiness. Event IDs provide atomic
idempotency through the primary key and transaction rollback on races. Database
and audit tables are not immutable against administrators; production retention,
backup, access policy and tamper resistance remain future work.

The supplied blueprint is the design source. Provider, broker, gold ownership
structure and scholarly screening methodology remain unselected. The platform
must not invent those approvals or treat a chart's ticker as verified ownership.
