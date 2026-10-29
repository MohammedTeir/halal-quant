# External human-label research benchmark

FinancialPhraseBank v1.0 supplies original human sentiment labels independent of
HALAL QUANT's implementation author and configured Gemini model. The all-agree
subset uses unanimous annotations. The dataset documentation describes overlapping
annotations by 16 researchers/business students with financial knowledge.

Sources: [dataset/card](https://huggingface.co/datasets/takala/financial_phrasebank),
[original paper](https://arxiv.org/abs/1307.5336). Attribution: Malo, Sinha, Takala,
Korhonen and Wallenius (2013). The retained original archive has SHA-256
`0e1a06c4900fdae46091d031068601e3773ba067c7cecb5b0da1dcba5ce989a6`.

## Scope and frozen selection

Ten cases per sentiment are selected by fixed SHA-256 rank of seed plus text,
without model outputs or manual case selection. Identical duplicate text/label pairs
are sampled once; conflicting labels are rejected. Original human labels are never
changed. Corpus bytes, seed, archive hash, licensing and a 90% sentiment/100% valid
response research threshold are frozen before inference. The original all-agree
subset has 2,264 rows; the manifest separately records unique texts.

The synthetic `EVAL_ONLY` target is a schema anchor, not a claimed company ticker.
Only sentiment is independently annotated. Event/policy expectations are deliberately
unconstrained and must not be described as external policy validation. The separate
adversarial/decision suites remain mandatory. General `acceptance_pass` remains false
because this corpus has no attacks; `external_sentiment_gate_pass` is a separate check.

## Licensing and deployment limits

The archive includes CC BY-NC-SA 3.0 and asks users to contact authors for commercial
or other non-academic use. This optional evaluation is isolated noncommercial research.
The data is not shipped as application runtime/news and corpus/model text is not
committed. Retain original license/README and attribution. No production data license
or individual publisher receipt/provenance is established by this benchmark.

The news concerns OMX Helsinki companies, rather than representative US stocks,
ETFs and gold. Historic/public examples may be in model pretraining. A balanced small
sample estimates neither natural-frequency production accuracy nor calibration, and
the original annotators have not approved this project.

## Reproduce offline preparation and score

With the independently obtained original archive and a new local output directory:

```sh
uv run python -m services.news_intelligence.external_benchmark freeze \
  --archive reports/generated/independent-labels-20261029/source.zip \
  --output reports/generated/new-frozen-external-sample
```

Collect explicitly using the existing collector (can consume quota), adding
`--min-interval-seconds 8` for conservative pacing. The interval is between request
starts and does not override provider quota/Retry-After behavior. Provider failures
still stop; no automatic resume/regeneration is introduced.

```sh
uv run python -m services.news_intelligence.external_benchmark score \
  --corpus reports/generated/new-frozen-external-sample/corpus.json \
  --freeze reports/generated/new-frozen-external-sample/freeze.json \
  --responses reports/generated/new-live-run/responses.json \
  --output reports/generated/new-external-score.json
```

The actual run retained a quota rejection after 15 completed cases. An explicit
paced follow-up includes 14 previously unattempted cases and the known quota-rejected
case; no ambiguous timeout is recalled. Original runs/labels are retained and combined
response origin is hash-bound in the final report. These are operator evidence,
not cryptographic authentication of provider calls or independent project sign-off.


## Observed result

The unchanged v5 model produced **30/30 valid, human-label-correct responses**,
including ten cases per sentiment. This passes the pre-frozen external sentiment
research threshold. [Final report](../reports/financial-phrasebank-v5-external-2026-10-29.json)
retains both run hashes, corpus hash, actual model version, original quota rejection
and the explicit paced follow-up. [Initial incomplete score](../reports/financial-phrasebank-initial-2026-10-29.json)
remains unchanged. No independent human project sign-off or production accuracy is
claimed, and no prompt/label was changed in response to this benchmark.
