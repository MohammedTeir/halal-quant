# Documentation guide

Start with the [project README](../README.md) for installation and commands, then
read [milestones](milestones.md) for implementation status and acceptance evidence.

| Document | Purpose |
|---|---|
| [حالة المراحل الأربع بالعربية](first-four-status.ar.md) | ملخص الجاهزية البرمجية وحدود اعتماد البحث والتشغيل |
| [Gold session investigation](gold-session-review.md) | All 2025 minute gaps, bounded official reference and unresolved source/holiday binding |
| [نتيجة تدقيق جلسات الذهب](gold-session-review.ar.md) | توضيح عربي للنتائج وحدود اعتماد الإغلاقات |
| [Independent technical review](independent-technical-review-2026-10-29.md) | Separate AI reviewer findings, evidence and conditional research-only verdict |
| [المرحلة الخامسة بالعربية](milestone-5-controls.ar.md) | المنجز في الجزء الأول وما تبقى قبل الاعتماد التشغيلي |
| [إغلاق المرحلة الخامسة تشغيليًا](milestone-5-release-handoff.ar.md) | الأدلة المطلوبة والمسؤوليات وفجوة مصدر النقد وخطوات التحقق |
| [Stored Milestone 5 workflow](milestone-5-operations.md) | Versioned reviewer controls, broker captures, risk state, reservations, verification and release boundary |
| [M5 independent technical review](milestone-5-independent-review-2026-10-29.md) | Separate AI review, six resolved software findings and remaining release limits |
| [Milestone 5 controls](milestone-5-controls.md) | Hypothetical compliance/risk API and CLI, acceptance, explicit conventions and remaining authority work |
| [Master blueprint v2](blueprint-v2.md) | Original full project requirements and acceptance gates |
| [External human-label evaluation](external-label-evaluation.md) | Independent original sentiment labels, frozen research sampling and limits |
| [Independent review packet](independent-review.md) | Prepared blind labels, separate model results and reviewer procedure |
| [Source and label review](source-and-label-review.md) | Verified gold/FOMC paths, real-source labels, failure findings and review independence |
| [Remaining completion requirements](completion-requirements.md) | Exact provider access and independent-review gates |
| [First four acceptance](first-four-acceptance.md) | Exact local evidence and external completion blockers |
| [Data providers](data-providers.md) | Free-tier starting recommendations, read-only acquisition, sessions and restart-safe worker |
| [Model evaluation](model-evaluation.md) | Frozen corpus, real-response collection and adversarial/quality scoring |
| [Milestones](milestones.md) | Progress, verification evidence, pending gates and next work |
| [Architecture](architecture.md) | Current module boundaries, storage and intended evolution |
| [Gemini backend](gemini.md) | Project key/model setup, structured inference, durable replay, cost behavior and mocked acceptance |
| [Intelligence and decisions](intelligence-decisions.md) | Advisory output contracts, evidence grounding, event policies, gate traces and missing authorities |
| [Data ingestion](data-ingestion.md) | Versioned facts, receipt/publication timing, freshness, split audits and remaining provider work |
| [Dashboard](dashboard.md) | English default, Arabic option, authentication and read-only workflow |
| [المرحلة السابعة بالعربية](milestone-7-dashboard.ar.md) | تشغيل لوحة التحكم وحدود معاينات التنبيه وما تبقى للتسليم |
| [المرحلة السادسة بالعربية](milestone-6-research.ar.md) | المنجز البرمجي وحدود قبول الأداء |
| [Portfolio and validation research](milestone-6-research.md) | Shared-cash replay, historical gates, training-only selection and Monte Carlo |
| [Walk-forward research](walk-forward-research.md) | Fixed parameters, disjoint chronological tests and separate final holdout |
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

- [Milestone 7 accounts, Telegram and deployment guide](milestone-7-accounts-telegram.md)

- [النشر على Vercel وRender مع Neon أو Supabase](deploy-vercel-render.ar.md)

- [Free Render API deployment without Blueprint](deploy-render-free.md)

- [Telegram worker on an existing computer or Termux](telegram-worker-computer-termux.md)

- [Finish Milestone 7 live operational acceptance](milestone-7-operational-acceptance.md)

- [Milestone 8 internal paper simulator and remaining forward acceptance](milestone-8-paper-trading.md)
