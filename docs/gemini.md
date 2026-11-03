# Gemini integration — project backend

The project now has a Gemini Developer API REST adapter, an authenticated generation
endpoint and durable generation records. The adapter was checked against Google's
[maintained SDK types](https://github.com/googleapis/python-genai/blob/main/google/genai/types.py)
and [REST converters](https://github.com/googleapis/python-genai/blob/main/google/genai/models.py).
All automated provider tests use mocks. A separate [one-article Termux live check](../reports/milestone8-live-news-check-2026-11-03.json)
on November 3 successfully stored an advisory assessment using
`gemini-3.5-flash-lite`. This is one observed account/model workflow, not a claim of
general compatibility, free-tier quota, billing eligibility or model quality.

## Configure your backend

Store the key on **your project backend**, using your deployment's secret manager
or an ignored local `.env`. Never put it in chat, source control, a `NEXT_PUBLIC_*`
variable, browser bundle, Pine script, news record or API request body.

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | Empty | Server-only Gemini credential; masked in settings representations |
| `GEMINI_MODEL` | Unconfigured | Bare `gemini-...` model ID available to your Google AI Studio account |
| `GEMINI_ENABLED` | false | Explicitly enables billable generation requests |
| `GEMINI_TIMEOUT_SECONDS` | 60 | Per-phase HTTP inactivity timeout; range 0.1–120 seconds |
| `GEMINI_MAX_OUTPUT_TOKENS` | 4096 | Response token ceiling; range 512–8192 |

Set the key and a JSON-output-capable model available to your account, then set
`GEMINI_ENABLED=true` and restart the backend. There is no hardcoded default model
because availability, retirement dates and free-tier access vary. Use a bare model
ID without a `models/` prefix, slash, URL or method suffix. The backend deliberately
reads `GEMINI_API_KEY`, not a fallback credential from another Google application.
The key is separate from the four local API access keys.

Native FastAPI loads `.env` through the existing settings layer. Compose passes
these backend variables at container creation; recreate the API after changes with
`docker compose up -d --build --wait`. The key is excluded from the build context
and is not baked into an image. Avoid dumping Compose configuration or process
metadata that could reveal environment values.

Runtime egress must permit HTTPS to `generativelanguage.googleapis.com`. The adapter
uses inherited proxy/CA settings, TLS verification and a fixed endpoint. Compose
mounts the trusted `proxy_ca` bundle read-only and sets `SSL_CERT_FILE` for runtime
HTTPS; `HALAL_CA_BUNDLE` selects the host bundle when needed. Keep the managed
Docker proxy configuration intact. No redirects or client-selected URLs are used.
The bundle is public trust material, not the API key.

Gemini is optional: missing key/model or a disabled feature does not stop API
liveness/readiness or other research work. New generation requests return 503
without creating a job or contacting Google until configured and enabled.

## Request an assessment

### One-article check from Termux

The phone can use its private `.env` and database directly for one advisory news
classification, without configuring an API analysis credential. First preview:

```sh
proot-distro login debian -- bash -lc 'cd /root/halal-quant && git pull --ff-only && .venv/bin/python -m services.news_intelligence.classify_one --symbol NVDA --classification-id termux-nvda-first-news-v1'
```

Add `--generate` to start one job using the phone's configured Google account:

```sh
proot-distro login debian -- bash -lc 'cd /root/halal-quant && git pull --ff-only && .venv/bin/python -m services.news_intelligence.classify_one --symbol NVDA --classification-id termux-nvda-first-news-v1 --generate'
```

This may consume quota or incur charges; model-metadata HTTP 200 does not prove
free-tier eligibility or remaining quota. The existing adapter's bounded HTTP
retry policy applies within the new job. There is no scheduler, loop or automatic
new classification ID. The command selects a current Finnhub revision explicitly
scoped to the stock, with publication and receipt in the preceding 24 hours and
`synthetic=false`. These labels and provider facts are not independently certified
truth. Missing qualifying news produces a blocker before any generation.

The existing generation service validates target scope, source revisions, strict
output schema and exact quoted evidence. Invalid output creates no assessment.
Rerunning the **same ID** inspects an existing succeeded, failed or running job
without another model call. Do not change IDs merely to clear a failure or an
ambiguous interruption; inspect the recorded status/provider usage first. A
changed target under an existing ID is rejected. A completed job missing its
assessment is reported as inconsistent rather than accepted.

Output contains a short advisory summary and fixed error/status codes, not keys,
raw provider errors, prompts or article URLs. A news recommendation of `ALLOW`
is not a company-screening approval or trading permission. This command creates
no signals, decisions, approvals, orders or notifications and starts no worker.
Keep paper entries blocked while independent financial/business screening,
review and source-coverage requirements remain unmet. One successful generation
does not validate model quality or complete Milestone 8.

Validation: 60 CLI/adapter/integration checks passed with mocked model responses,
including source filtering, real grounding validation, successful/failed/running
job inspection, and secret-safe configuration errors. No live generation or
production write was used to test this change. Lint and formatting passed.

### Observed first live phone result

The job `termux-nvda-first-news-v1` completed at **11:48 on November 3, 2026
(Asia/Jerusalem)**. A subsequent read-only database inspection confirmed its
stored success, provider/model metadata and grounded citations without another
model call. Reported usage was 1,015 prompt tokens plus 478 candidate tokens,
1,493 total; this does not establish a currency cost or remaining quota.

The supplied article headline was “Nvidia tells data center partners to limit
China sales- FT.” Finnhub labeled the source Yahoo; its short summary attributed
the news to Investing.com citing a Financial Times report based on unnamed
sources. Both model quotations are exact substrings of the stored headline or
summary. A primary Nvidia statement and the full underlying report were not
independently verified by this inspection.

The model returned negative sentiment, medium severity, uncertain market impact,
`REVIEW`, and `requires_human_review=true`. Its 0.9 confidence is a model-reported
value, not a calibrated truth probability, predicted return or independent
accuracy measurement. The assessment supports retaining review, not automatically
clearing it. It supplies no missing financial/business revenue allocation and
does not change NVDA's insufficient-evidence screening outcome.

At observation there were zero paper orders, zero cycles and zero control review
records. Human review remains uncleared, virtual entries blocked and Milestone 8
incomplete. The existing fixed ID can be inspected again without starting another
generation; do not choose a new ID merely to seek a more favorable assessment.

### API request

Import source news first, then read its current immutable `source_id` from
`GET /api/v1/news` using your dashboard credential. Submit:

```http
POST /api/v1/news/classifications/generate
X-Analysis-Key: <your project analysis credential>
Content-Type: application/json
```

```json
{
  "classification_id": "your-unique-generation-id",
  "source_id": "<64-character source ID returned by your backend>",
  "symbol": "EXAMPLE",
  "asset_class": "stock"
}
```

The [request schema](contracts/generation-request-v1.schema.json) accepts only these
four fields. The [checked-in request example](../examples/intelligence/gemini-generation-request.json)
references `examples/data/news-batch.json`; import that synthetic batch first if
using the example. A real enabled request may consume account quota or incur charges,
even for synthetic source text. Do not run it expecting the mock test behavior.

The backend chooses the model, endpoint, prompt, token limit and key. Caller-supplied
keys, model overrides, tools, endpoints, holdings and approvals are rejected.
`X-Analysis-Key` authorizes your local application operation; it is not the Gemini
key. Read generation status with your dashboard bearer credential:

```http
GET /api/v1/news/classification-jobs/your-unique-generation-id
```

The response shows status, target, selected/reported model, timestamps, safe error
code and token usage when available. It never includes the key, ownership token,
raw provider errors or internal source snapshot. Successful assessments also appear
in the existing classification history with `generation` provenance metadata.
Manual assessment imports have no such generated provenance.

## Durable lifecycle and cost behavior

A generation request commits a RUNNING claim and audit before the HTTP call. No
SQL transaction is held across inference. The source must already exist, be current
and match the target scope. Concurrent callers using the same ID do not start
another generation. Manual imports cannot use an already reserved ID.

On completion, the service parses and grounds the output, rechecks that the source
has not been corrected during inference, and commits the assessment, SUCCEEDED job,
usage metadata and audits together. Model output must use exactly the requested
symbol, asset class, anchor and sole source ID. Invalid quotes, changed targets,
privilege fields, tool output or superseded sources produce a FAILED job and no
assessment. Available completion metadata is retained even when grounding fails.

An exact successful replay returns the stored assessment with `duplicate: true`
without another model call, even if deployment configuration later changes.
Changed input under the same ID returns 409. Existing RUNNING or FAILED IDs also
return 409; there is no automatic regeneration/reset endpoint. Inspect the job
before deliberately choosing a new ID. A completed assessment whose job ledger
was removed by rollback still reserves its classification ID.

There are at most two HTTP attempts per newly claimed job. Only transient HTTP
429/500/502/503/504 or connection-establishment failures may get one short retry.
A numeric Retry-After up to one second is honored; longer/invalid values stop the
request rather than sleeping indefinitely or immediately retrying. Redirects,
credentials/model errors, blocked/truncated output and invalid assessments are
not retried. Read/write/protocol failures after possible delivery are treated as
ambiguous and are not automatically retried.

This prevents duplicate calls from local request replays, not a guarantee of
exactly-once billing at Google. A transient response or timeout may follow provider
work. An interrupted process or ambiguous DB commit can leave a job RUNNING;
there is intentionally no lease-expiry auto-recall. Check your backend/provider
usage before issuing another ID. Set account-level budgets/quotas yourself;
this increment is not a global rate limiter or pricing calculator. Reported token
counts are not a dollar estimate, and thought-token usage depends on the model.

This API is synchronous; the job table is a durable inference record, not an
implemented background worker/queue. Per-phase timeouts are not a hard total
wall-clock deadline. Production scheduling, cancellation, account quotas and
operator recovery workflows remain future operational work.

## Structured output and security boundary

The adapter calls the fixed v1beta `generateContent` endpoint with one candidate,
JSON MIME type, temperature 0 and a target-bound JSON schema. It sends the key only
in `x-goog-api-key`, never a URL or prompt. Tools, function calling, URL fetches and
execution capabilities are not supplied. Google-supported JSON Schema keywords
are used; omitted string-pattern/length constraints remain enforced locally.

Prompt version `news-classification-v2` adds an explicit fixed target to the earlier
advisory system instruction. News stays JSON-encoded untrusted data. Upstream schema
enums constrain target fields, and local validation checks them again. Old manual
v1 prompt records remain readable. Output must have one complete STOP candidate,
model-role text and a reported Gemini model version. Thought text, function calls,
refusals, ambiguous candidates, missing provenance or malformed JSON are rejected.
Opaque provider thought signatures are ignored, never interpreted as instructions.

Source/target documents are capped at 64 KiB, decoded provider responses at 256 KiB,
and final assessment JSON at 64 KiB. No output repair or additional paid self-correction
loop is implemented. Error messages expose fixed application codes, not Google
response bodies or HTTP exceptions containing credentials.

Generated assessments still pass the exact quote/source/field checks described in
[intelligence and decisions](intelligence-decisions.md). Temperature 0 does not
promise deterministic or truthful model output. Quotes establish provenance, not
semantic correctness or provider accuracy. A positive model response cannot clear
calendar windows, unverified feeds, compliance, risk or ownership gates. Every
decision remains `authorized: false`; live trading remains disabled.

## Validate without a key or charges

```sh
uv run pytest tests/gemini tests/integration/test_gemini_api.py -q
uv run python -m scripts.gemini_mock_smoke --output reports/generated/gemini-mock.json
```

The smoke uses a temporary SQLite database, nonfunctional fixture key and
`httpx.MockTransport`. It does not read or use your Gemini key for inference and
makes zero real provider calls. It exercises API import → generated structured
response → evidence validation → durable job/replay → blocked decision. Choose a
new report path each time; outputs are not overwritten.

Historical adapter-increment acceptance: 201 tests overall, including 31 transport/schema/config tests
and 17 generated-assessment API tests. All 57 API tests also pass on SQLite.
[Mock evidence](../reports/gemini-mock-smoke.json) and
[disabled-container evidence](../reports/gemini-container-smoke.json) distinguish
mocked inference from deployment startup. The latter checks API readiness, CA
loading and disabled generation with no job/model call.

Apply Alembic head `0005_feed_coverage` before current readiness. Migration `0004_gemini_jobs` introduced the generation ledger. It preserves existing facts,
classifications and decisions. Downgrading to 0003 deletes generation claims; do
not use it on operational data without backup/recovery planning, since deleting
failed/in-flight history destroys replay protection. Never automatically recall
ambiguous requests after restoring an older database snapshot.

Real-account authentication and selected-model structured-output compatibility now
have live evidence below. Independent quality/robustness review and quota behavior
remain separate concerns; mocked checks do not establish them.

## Frozen quality evaluation

[Model evaluation](model-evaluation.md) documents the synthetic adversarial corpus,
one-shot real-response collector and offline semantic/evidence scorer. Live runs
require explicit backend enablement and consume quota. Live diagnostic scores are recorded below; independent reviewer approval remains
open.

The first live follow-up confirmed `gemini-3.5-flash-lite` metadata and structured
generation; [the diagnostic failed](../reports/gemini-live-diagnostic-2026-10-29.json).
Model compatibility on this sample is not a release-quality or robustness pass.

## Version 3 completion pass

That increment used `news-classification-v3`. It explicitly
requires conservative review for conditional/uncertain impact and instruction-only
source attacks. Legacy v1/v2 imports and historical results remain readable. Failed
v2 jobs/runs were not restarted. A separate v3 experiment on unchanged frozen
labels passes [12/12 diagnostic cases](../reports/gemini-v3-diagnostic-2026-10-29.json).
A [real-news API check](../reports/gemini-real-news-api-2026-10-29.json) confirms
durable success/replay without a second provider call and a blocked decision.
Default timeout is 60 seconds; a smaller explicitly configured value still applies.
This fixes observed timeout sensitivity but does not promise future requests cannot
time out. Ambiguous requests retain their failure/claim and are not auto-regenerated.
Independent real-world holdout/source review remains required; see
[completion requirements](completion-requirements.md).

## Historical prompt v4

The following increment used `news-classification-v4`. A primary-source
pilot found a mixed factual-news/instruction-attack case that v3 did not restrict.
V4 requires review for that combination while preserving factual sentiment/event
type. V3 text and failed pilot evidence are retained. See
[source/label review](source-and-label-review.md) for 8/8 regression, 4/4 fresh
pilot and the explicit independence limits.


## Current prompt v5

The active server generation prompt and collector default are
`news-classification-v5`. Broader real-source evaluation exposed v4 sentiment errors
(10/16), while all eight attacks requested review. V5 defines year-over-year
financial sentiment, avoids inferred gold direction from macro readings, and keeps
injected control text separate from financial facts. All legacy prompt versions
retain their original text and stored history.

V5 passes 16/16 exposed regression and 8/8 separately frozen fresh pilot. The current
full suite passes 334 tests. [Source review](source-and-label-review.md) retains
failures and independence limits; [review packets](independent-review.md) remain
PENDING. These scores are not representative accuracy or independent approval.
