# Architecture

A modular monolith: FastAPI ingress, explicit Pydantic contracts, SQLAlchemy storage,
Alembic migrations, and pure Python indicators. PostgreSQL is the system of record.
The first migration creates signals and audit logs; the second adds immutable
news/calendar/corporate-action revisions and successful data-import observations.
The third migration adds immutable model classifications and recorded decisions;
the fourth adds durable generation claims and outcome metadata. Domain
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
research gates, preserving a complete decision snapshot. The Gemini provider adapter
uses fixed-host HTTPS and structured output behind a backend-only enable/key/model
configuration. Generation claims commit before the network call and finish in a
separate transaction with source revalidation; no SQL transaction spans inference.
Provider requests are synchronous, not a background queue. Configured Gemini compatibility and limited source-quality diagnostics have live
evidence; representative production quality remains unverified. CI uses mocks.
Read-only Alpaca/Finnhub/BLS acquisition and a restart-safe normalized batch worker
are available as explicit operator commands; live provider coverage remains unverified.
There is no portfolio research engine or broker adapter yet. The research
CLI is independent of HTTP ingestion and cannot authorize paper orders.

Flow: closed chart bar → technical candidate → authenticated ingress → validated
signal and audit transaction. Later milestones add authoritative point-in-time
data, intelligence, compliance, risk and a decision engine **before** paper order
authorization. Dashboard, Redis, Telegram, background queues and live broker adapters are deferred
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

The [frozen evaluation workflow](model-evaluation.md) collects and scores model
responses separately from order decisions. [Provider acquisition](data-providers.md)
archives source inputs and preserves server receipt/revision semantics. Neither
workflow supplies compliance, risk, ownership or execution authority.


`services/controls` and `packages/schemas/controls.py` now implement the first
Milestone 5 hypothetical compliance/risk boundary. The read-only authenticated
preview has no path into persisted TrustedState or broker authority. It consumes
only caller-supplied hypothetical evidence; server candidate evaluation retains
its missing-authority gates. [Operational integration remains](milestone-5-controls.md).
