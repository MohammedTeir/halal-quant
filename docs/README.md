# Documentation guide

Start with the [project README](../README.md) for installation and commands, then
read [milestones](milestones.md) for implementation status and acceptance evidence.

| Document | Purpose |
|---|---|
| [Master blueprint v2](blueprint-v2.md) | Original full project requirements and acceptance gates |
| [Remaining completion requirements](completion-requirements.md) | Exact provider access and independent-review gates |
| [First four acceptance](first-four-acceptance.md) | Exact local evidence and external completion blockers |
| [Data providers](data-providers.md) | Free-tier starting recommendations, read-only acquisition, sessions and restart-safe worker |
| [Model evaluation](model-evaluation.md) | Frozen corpus, real-response collection and adversarial/quality scoring |
| [Milestones](milestones.md) | Progress, verification evidence, pending gates and next work |
| [Architecture](architecture.md) | Current module boundaries, storage and intended evolution |
| [Gemini backend](gemini.md) | Project key/model setup, structured inference, durable replay, cost behavior and mocked acceptance |
| [Intelligence and decisions](intelligence-decisions.md) | Advisory output contracts, evidence grounding, event policies, gate traces and missing authorities |
| [Data ingestion](data-ingestion.md) | Versioned facts, receipt/publication timing, freshness, split audits and remaining provider work |
| [Python research](python-research.md) | Primary strategy workflow, CSV contracts, costs, reproducible reports and limitations |
| [Strategy specifications](strategy-specs.md) | Strategy defaults, entry/exit behavior and deferred gates |
| [Compliance policy](compliance-policy.md) | Required screening and transaction rules; implementation status |
| [Risk policy](risk-policy.md) | Initial risk limits and required exit protections |
| [API contracts](api-contracts.md) | Implemented routes, authentication, payload and errors |
| [Signal JSON Schema](contracts/signal-v1.schema.json) | Generated structural signal contract |
| [Pine acceptance](pine-validation.md) | TradingView compilation/replay protocol and limitations |
| [Operations runbook](operations-runbook.md) | Startup, migrations, troubleshooting and security boundaries |

The blueprint describes the target system. The milestone tracker describes what
exists. A written policy is not an implemented or independently reviewed control.

When completing a milestone, update its state, record the exact checks and outcomes,
and distinguish local validation from hosted CI and external platform acceptance.
Keep API, strategy and policy documents aligned with the implementation. Never
mark a manual gate complete without its evidence.
