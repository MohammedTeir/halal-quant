# Advisory intelligence and deterministic decisions — Milestone 4

Status: classification contracts, source grounding, immutable persistence, event
policies and research decision gates are implemented and locally validated. A [Gemini backend adapter](gemini.md) now implements structured
inference with durable claims and mocked provider acceptance. No live account/model
or model-quality evaluation has been validated. There is no AI acquisition worker;
this remains a research integration boundary, not a validated AI trading system.

## Trust boundary

Raw news and model output are untrusted analytical data. The model is never asked
to supply cash, owned holdings, compliance, instrument permissions or execution
authority. None of those fields are accepted by its schema. Only the application
constructs `TrustedState`; API callers cannot supply it. Every result, including
BUY_CANDIDATE and EXIT_CANDIDATE in pure engine tests, returns `authorized: false`
and requires a separate execution authorization that is not implemented.

The public API currently reports WAIT_DATA for entry evaluations because verified
market data/broker/compliance/instrument/risk authorities are missing. It still
records every gate and the intelligence evidence, so later blockers are visible.
Exit evaluations report WAIT_OWNERSHIP until authoritative sellable ownership
exists. This is deliberate fail-closed behavior, not an AI service outage.

A fourth distinct credential, `ANALYSIS_API_KEY` in `X-Analysis-Key`, permits
assessment import and decision evaluation. Dashboard bearer credentials read
results; data and webhook credentials retain their existing separate roles.
All four values must differ and remain outside source control. No LLM key is required for offline fixture tests. Actual Gemini generation
requires a separate backend GEMINI_API_KEY, configured model and explicit enable flag.

## Strict assessment contract

See [Assessment schema](contracts/assessment-v1.schema.json). The original blueprint
contract is made concrete with explicit asset scope and source-bound quote objects.
It contains schema version, anchor event ID, target symbol/asset class, event type,
sentiment/score, relevance, severity, confidence, source IDs, quoted evidence,
market impact, recommended policy and human-review flag. Confidence/relevance are
0–1; sentiment score is -1–1 and must agree with positive/negative/neutral labels.
Human-review flags must be JSON booleans. Numeric confidence/relevance/sentiment
fields reject booleans and numeric strings. Unknown fields are forbidden.

`event_id` and `source_ids` reference immutable server-issued news `source_id`
values, now included in fact-read responses. Every source ID must have evidence;
the anchor must be among those sources. Evidence is an exact, case-sensitive
substring of its cited headline or summary, between 8 and 2000 characters. Sources
must support the target symbol and any declared asset class; class-only news is
accepted only when it has no explicit symbols and its class matches. All sources
must exist, be currently known at submission, and be the latest known revisions.
Invented sources/quotes and stale-revision submissions return 422.

Quotes establish textual provenance, not entailment, truth or provider authenticity.
A model can still misinterpret a genuine quote. Those quality checks require
real datasets, a selected model and evaluation before deployment.

The raw output parser accepts one JSON object, at most 64 KiB UTF-8. It rejects
markdown wrappers, duplicate keys (including nested keys), non-finite numbers,
unknown fields, invented policy values, tool calls and permission/order fields.
It does not execute code, resolve URLs, invoke tools or try to repair malformed
responses into an accepted result.

`build_prompt` keeps a fixed system instruction separate from JSON-encoded source
documents and supplies the response schema. The adapter protocol accepts that
prompt and returns text; tests use fixture adapters and HTTP-mocked Gemini. The
Gemini production path uses target-bound prompt version news-classification-v2. Adapter implementations
are trusted application code, while their output is untrusted. Prompt-injection
tests demonstrate boundary isolation and denial of privileged output; they do not
establish that an untested real model is immune to prompt injection.

## APIs and history

| Method and path | Credential | Behavior |
|---|---|---|
| `POST /api/v1/news/classifications` | X-Analysis-Key | Parse/ground and atomically store a classification plus audit |
| `GET /api/v1/news/classifications` | Dashboard bearer | Immutable model/version history; optional aware `as_of`, exact `symbol`, bounded `limit` |
| `POST /api/v1/decisions/evaluate` | X-Analysis-Key | Evaluate a stored signal using server state and record evidence/audit |
| `GET /api/v1/decisions` | Dashboard bearer | Recorded evaluations available by `as_of`, newest first, bounded `limit` |
| `GET /api/v1/decisions/{evaluation_id}` | Dashboard bearer | The exact immutable recorded evaluation |

[ClassificationRequest](contracts/classification-request-v1.schema.json) contains a
unique classification ID, declared model name/version, declared prompt version
`news-classification-v1` or `news-classification-v2`, and **raw_output as a JSON string**. Model provenance is
supplied metadata, not independent evidence that the named model was actually used.
Source snapshots, raw output, parsed assessment, model/prompt versions and server
receipt time are retained. New model outputs require new IDs and never overwrite
old ones. Exact retries are no-ops even after a source correction; new submissions
against that superseded source are rejected.

[EvaluationRequest](contracts/evaluation-request-v1.schema.json) accepts only an
evaluation ID, existing signal ID, finite numeric score 0–1 and optional aware
`as_of` no later than now. The signal must already have been received by that time.
No compliance/risk flags, holdings or policy overrides are accepted. Score is an
opportunity input, not evidence or permission to trade.

Identical IDs/requests return the original result with `duplicate: true`; changed
content under an existing ID returns 409. Successful first writes produce exactly
one audit. Writes are transactional; unique-key races retry after rollback.
Invalid source/output/input returns 422, invalid credentials 401, missing recorded
evaluation 404, and write-store failure 503. Replayed evaluations use their stored
snapshot, not today's state.

Classifier receipt time is authoritative. An assessment produced after an as-of
cutoff cannot influence that earlier evaluation. Source corrections invalidate
old-revision classifications for new evaluations. Recent assessments from all
model versions are considered conservatively; a newer positive opinion does not
erase an adverse recent opinion. Stored prior decisions remain unchanged.

## Fixed deterministic policies

`decision-v1` is server-owned code; there is no API for weakening it.

| Rule | Initial default |
|---|---|
| Minimum opportunity score | 0.65, checked after mandatory gates |
| Minimum model confidence | 0.70; lower values require review |
| Minimum relevance | 0.50; lower values require review |
| Earnings window | Matching stock: 24h before through 24h after, inclusive |
| High-impact macro window | Applicable high-severity calendar event: 2h before through 1h after, inclusive |
| Recent news | Previous 24 hours of publication, also received by cutoff |
| Assessment validity | Created by cutoff and no older than 60 minutes, with current source revisions |
| Feed age | Successful news and calendar polls no older than 15 minutes |

Cancelled events do not restrict entries. Earnings for a different explicitly
named issuer do not block the candidate. Missing earnings issuer scope applicable
to stocks triggers review. Macro scope uses explicit symbols/classes; events
without any scope trigger conservative review. Tags are still provider assertions;
sector/ETF holdings/rate-sensitivity mapping remains future work.

REVIEW/RESTRICT recommendations, human-review flags, low confidence, uncertain
relevance/impact, mixed sentiment or high-severity adverse news add restrictions.
Opposing positive/negative active assessments trigger conflict review. Positive
ALLOW text never clears calendar windows, missing/stale/synthetic/unverified
feeds, unclassified news, compliance, instrument or risk gates. No numerical
confidence adjustment is invented to disguise a conflict.

Entry gate order is data freshness → APPROVED compliance → permitted instrument →
news/event restrictions → risk limits → score. Every check is recorded; the first
failed gate determines the primary status. The pure engine can produce
BUY_CANDIDATE when *trusted* application state satisfies every gate, but still
cannot authorize an order. The current API has no authority to construct that
approved state, so it never does.

Protective exits use a separate ownership check. Verified positive sellable
quantity can produce EXIT_CANDIDATE even when entry gates are blocked; unverified
or zero ownership produces WAIT_OWNERSHIP. News windows and entry loss guards do
not disable that path. Broker execution, quantity authorization and actual owned
positions remain Milestone 5/8 work; this increment sends no orders.

## Reproduce local checks

With four matching credentials exported for a running API, set server-side
`NEWS_PROVIDER=synthetic_smoke` and `CALENDAR_PROVIDER=synthetic_smoke` before
starting Compose, then run:

```sh
uv run python -m scripts.decision_smoke --output reports/generated/decision-smoke.json
```

The script persists clearly labelled synthetic news/calendar/signal/classification
and decision records. It uses an offline fixture, never a real LLM. It checks role
separation, forged-approval rejection, positive-advisory versus earnings-window
behavior, replay, retrieval and unverified ownership. Choose a new output path.
The recorded full-stack run also verifies persistence across an API restart.

Checked-in [assessment](../examples/intelligence/assessment.json),
[classification envelope](../examples/intelligence/classification-request.json)
and [evaluation request](../examples/intelligence/evaluation-request.json) show the
contracts. The classification sample references the immutable source ID of
`examples/data/news-batch.json`; import that batch first. Replace the evaluation
sample's signal placeholder with an actual known signal ID. Old article examples
may fall outside the recent-news window even though their classification can be
stored. Do not backdate receipt times or mutate existing source revisions.

The intelligence increment added 51 schema/parser/policy/core tests and 13
assessment/decision API tests. That historical adapter increment had 201 passing tests, including
48 Gemini-specific mocked checks. The full PostgreSQL suite, targeted final
source-scope checks and SQLite API workflow pass. Migrations preserve existing
facts/signals; concurrent replays create one classification/decision audit.
[Recorded smoke evidence](../reports/decision-smoke.json) is synthetic software
acceptance, not model accuracy or market performance.

Migration `0003_intelligence` creates these records; current API readiness requires
head `0005_feed_coverage`, including `0004_gemini_jobs`. Downgrading to 0002
removes classifications and decisions while preserving earlier facts/signals;
its audit entries remain. Use rollback tests only on disposable databases and
back up real data before any schema change. Production RBAC, review workflows,
paginated archives, real source verification, live Gemini/model-quality evaluation,
portfolio risk, compliance and broker authorization remain unfinished.
