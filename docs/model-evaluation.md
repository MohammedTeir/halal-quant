# Frozen model-quality and adversarial evaluation

Milestone 4 has a reproducible evaluator and a one-shot Gemini collector. Neither
mock outputs nor this developer-authored corpus establish real-model quality.
The first four milestones remain subject to [external acceptance](first-four-acceptance.md).

## Frozen inputs and labels

[The diagnostic corpus](../examples/intelligence/evaluation/corpus-v1.json) has 12
synthetic cases: positive/negative/mixed earnings, neutral company news, Fed/CPI
uncertainty, and six instruction attacks (role spoofing, tool calls, JSON boundary
escape, fabricated evidence, secret exfiltration and markup). Labels specify
acceptable sentiment, event type and recommended policy **before inference**.
These labels are developer-authored and need independent domain review. This small
corpus is a diagnostic, not a representative statistical benchmark.

Add independently labeled, legally usable real sources and a held-out adversarial
set; freeze corpus bytes and review the labels before selecting prompt/model
versions. Do not tune against the frozen holdout and call it unseen evaluation.

## Collect real responses explicitly

Configure backend Gemini as described in [Gemini setup](gemini.md), including an
account-available model and enabled flag. This command makes real requests and can
consume quota; it is never run by startup or CI:

```sh
uv run python -m services.news_intelligence.collect_evaluation \
  --corpus examples/intelligence/evaluation/corpus-v1.json \
  --run-dir reports/generated/unique-live-evaluation
```

The run directory must be new. The manifest and per-case started marker are written
before inference. Each result retains raw output, actual model version and usage.
The exact corpus is copied; no credential is included. A process crash leaves its
started marker. Reusing a run directory always fails without recalling the model;
there is no automatic resume. Inspect ambiguous runs before creating any deliberate
new run. The existing Gemini adapter's maximum two bounded HTTP attempts still
apply, so this is not a promise of exactly-once provider billing.

Provider failure stops the run rather than consuming quota on remaining cases.
Missing responses count as failed quality cases. Version drift prevents writing a
homogeneous response artifact; preserve per-case records for review. Runs are
limited to 100 cases per explicit invocation. Local files are operator evidence,
not independently authenticated attestations of live traffic.

## Score supplied responses

```sh
uv run python -m services.news_intelligence.evaluation \
  --corpus examples/intelligence/evaluation/corpus-v1.json \
  --responses reports/generated/unique-live-evaluation/responses.json \
  --output reports/generated/unique-live-quality-report.json
```

The evaluator verifies the frozen corpus hash, forbids unknown/duplicate case IDs,
and tests strict schema, exact target/source IDs, quoted evidence and semantic
labels. Missing, malformed, wrong-target, invented-evidence and wrong-label answers
fail acceptance. Rejected attack responses can count as **contained at the boundary**
but never count as correct classification. A missing attack response is not proof
of containment. The diagnostic gate requires every case valid and label-correct,
with at least one attack case; exit 0 passes, 1 saves failed metrics, 2 rejects input.

Reports preserve model/prompt versions, input hash, response origin, per-case
outcomes and counts. `deployment_approved`, `independently_reviewed` and
`authorized_for_entry` always remain false—even for a perfect diagnostic score.
Human review, real-data holdout accuracy/calibration and source credibility remain
separate release gates. Deterministic policy tests establish enforcement boundaries;
model text cannot invent compliance, risk, ownership or execution permissions.

Automated tests use fixture responses and fake adapters only. They intentionally
exercise wrong labels, missing responses, fabricated quotes, target changes,
privileged fields, crashes and versioned run claims. No live score is claimed.

## Offline example without keys

The [mock responses](../examples/intelligence/evaluation/mock-responses-v1.json)
are constructed synthetic fixtures, not output from any model. CI scores them to
exercise the CLI. Run the scoring command above with this file as `--responses`
and a new output path to verify local setup. A perfect fixture score proves only
that the evaluator accepts the supplied labels. Negative tests verify it rejects
wrong labels, missing cases, invented evidence and changed targets.

Structural schemas: [corpus](contracts/evaluation-corpus-v1.schema.json) and
[responses](contracts/evaluation-responses-v1.schema.json).

## First live diagnostic (2026-10-29)

The configured `gemini-3.5-flash-lite` model was confirmed through its metadata
endpoint and returned structured responses. The frozen diagnostic **did not pass**:
8 of 12 cases have valid grounded responses, 7 match the frozen labels. The Fed
uncertainty case returned a policy outside its expected label. Two adversarial
requests timed out with ambiguous delivery and were not recalled; two cases remain
unattempted. Missing answers do not establish attack containment.

Only previously unattempted cases were collected in a second exclusive run; no
case was sent twice by the evaluation collector. Combined scoring preserves both
run manifest/response hashes and the original frozen corpus hash. See the
[per-case live report](../reports/gemini-live-diagnostic-2026-10-29.json).
These are synthetic diagnostic cases, not an independent real-news holdout.
Investigate latency and prompt/policy behavior, keep prompt versions distinct for
changes, and review ambiguous upstream requests before any deliberate regeneration.
Do not change frozen labels to turn this failed run into a pass.

## Version 3 diagnostic follow-up

The original corpus/labels remain unchanged. A new v3 experiment with a 60-second
HTTP inactivity timeout returned 12 valid, label-correct results (12/12). The CLI
now defaults to `--prompt-version news-classification-v3 --timeout-seconds 60`;
v2 remains selectable for historical comparisons. Result files include elapsed
seconds. API generations pin and retain their actual prompt version and timeout.
The earlier failed runs are preserved; this is a new experiment after code changes,
not automatic job regeneration. [Passing diagnostic](../reports/gemini-v3-diagnostic-2026-10-29.json).
Because this diagnostic informed prompt tuning, it cannot be claimed as an
independent holdout. Complete [independent review](completion-requirements.md) before
claiming full Milestone 4 quality sign-off.

## Real-primary-source review and v4

[Source and label review](source-and-label-review.md) documents frozen real excerpts,
label provenance, independence limits and the retained 7/8 v3 failure. V4 adds
mandatory review for embedded control instructions even alongside positive facts.
It passes the exposed 8-case regression and a fresh 4-case blind pilot. The CLI
now defaults to `--prompt-version news-classification-v4`; legacy versions remain
selectable. The original labels and failed results were not altered.

Reproducible corpora:
[primary pilot](../examples/intelligence/primary-review/primary-pilot-v1.json) and
[fresh pilot](../examples/intelligence/primary-review/fresh-pilot-v2.json). Their
adversarial variants are explicitly synthetic. Scores do not assert independent
human review; the coding assistant was blind to Gemini predictions but was also
the implementation author.

## Broader source evaluation and v5

V4's expanded real-source pilot scored 10/16; all eight attacks requested review,
but financial/macro sentiment was inconsistent. Labels and original responses are
retained. V5 adds precise year-over-year earnings and factual-macro sentiment rules,
passes the unchanged 16-case regression and a fresh 8-case pilot. The collector now
defaults to `news-classification-v5`; v2/v3/v4 remain selectable unchanged.
See [source review](source-and-label-review.md) and [review packets](independent-review.md).

The scorer additionally requires `requires_human_review=true` for attack quality
acceptance. Containment is measured separately through REVIEW/RESTRICT plus human
review, or a rejected malformed output; sentiment errors still fail quality.
Per-event/sentiment support counts expose missing categories. They do not make a
small purposive sample representative or grant independent approval.


## External original-human labels and quota pacing

[FinancialPhraseBank research](external-label-evaluation.md) adds a balanced fixed
30-case original-human-label check: v5 passes 30/30 without label/prompt changes.
It is separate from project policy/adversarial acceptance and does not approve
source suitability or deployment. Text stays outside tracked/runtime files.

The collector optionally accepts `--min-interval-seconds 8` (0..60; default 0).
It spaces starts, retains the interval in the manifest, stops on provider failure,
and never auto-resumes a run. The API adapter's bounded retry rules are unchanged.
