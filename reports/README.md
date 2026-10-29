# Research evidence

`synthetic-smoke.json` records execution counts and run identities from the first
Python acceptance run. It is software evidence only, not historical returns or
proof of profitable expectancy. Full reports and input CSVs are generated locally
under ignored directories; reproduce them using [the research guide](../docs/python-research.md).

No report currently authorizes paper or live trading. Use new output filenames to
preserve prior experiments, retain source/configuration/data hashes, and document
real holdout selection before evaluating it.

`data-ingestion-smoke.json` records a real local HTTP check of synthetic fact imports,
replay/audit behavior, point-in-time exclusion, synthetic feed guard and restart
persistence. `split-audit-smoke.json` records the checked-in synthetic raw/adjusted
example's arithmetic result. Neither verifies an external provider or real data.

`decision-smoke.json` records a synthetic offline-fixture classification-to-decision
HTTP run: positive advisory output cannot clear an earnings window or missing
authorities, forged approval fields are rejected, and recorded decisions survive
restart. No real model was invoked, and every result denies authorization.

`gemini-mock-smoke.json` proves the isolated API → HTTP-mocked Gemini → grounded
assessment → stored job/replay → blocked decision path. The model/version and token
counts are fixture data, not live provider results or charges.
`gemini-container-smoke.json` verifies the rebuilt stack, runtime CA bundle loading
and disabled generation without a job or real model call.

`evaluation-harness-smoke.json` scores the explicitly synthetic mock response file
against the frozen synthetic corpus. Its perfect fixture score is evaluator
software evidence only; no real model was called and no independent review or
deployment approval is implied. `first-four-acceptance.json` records current local
checks and the unpassed external gates; milestones 3 and 4 remain open.

`live-provider-acceptance-2026-10-29.json` records real sample acquisition and
provider/model metadata responses after published credentials became ready. It
contains counts/hashes, not credentials or licensed news content.
`gemini-live-diagnostic-2026-10-29.json` records failed real-model diagnostic
acceptance, including ambiguity/missing cases and run provenance. Historical
`first-four-acceptance.json` describes the earlier local-only pass and is superseded
by these follow-up results for credential/access readiness. Neither live report
establishes complete data coverage, independent model quality or trading approval.

`gemini-v3-diagnostic-2026-10-29.json` records the 12/12 passing v3 live diagnostic
against unchanged synthetic labels; it is a tuned diagnostic, not an independent
holdout. `gemini-real-news-api-2026-10-29.json` records actual grounded durable
generation/replay and the unauthorized decision. `aapl-live-split-audit-2026-10-29.json`
records the real raw/adjusted 4-for-1 audit, explicit rounding bound and volume check.
`milestones-3-4-followup-2026-10-29.json` records scoped data/earnings/action progress
and the still-blocked gold/FOMC and independent-review requirements.
