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
