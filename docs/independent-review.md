# Independent source and classification review

The author cannot sign off their own implementation as independently reviewed.
The current artifacts explicitly retain `independent_of_implementation_author=false`
and `human_review_completed=false`. No approval has been granted.

## Prepared material

Local, ignored evidence directories contain:

- `reports/generated/expanded-review-20261029/independent-review-v5/`
- `reports/generated/fresh-v5-review-20261029/independent-review-v5/`

Each packet has `blind-labels.json`, `model-results.json`, `review-form.json` and
instructions. The source freeze binds exact corpus/excerpt/HTML hashes, URLs,
rationales and limitations. Forms are PENDING with blank reviewer/approval fields.
They are operator evidence, not cryptographically authenticated reviewer identities.
The downloadable local archive is `reports/generated/milestone34-review-20261029.zip`.
Raw downloaded HTML, gold archives and full model responses remain local; short
real-source corpora, review freezes, hashes and aggregate/per-case scores are tracked.

## Reviewer procedure

1. Read the blind labels first and check each short excerpt against the linked
   primary release. Distinguish issuer claims, official statistics and forecasts.
2. Record disagreements and source limitations without modifying the frozen corpus.
   Embedded attack variants are synthetic, not publisher-authored statements.
3. Assess missing categories: ETF/company events, secondary reporting, conflicting
   sources, cancellations/corrections, language/time regimes and larger samples.
   Define additional acceptance criteria and freeze new cases before inference.
4. Open model results. Review failures/missing outputs and separate sentiment
   quality from safe policy containment. A regression exposed to prompt tuning
   cannot be described as an untouched holdout.
5. Record reviewer identity, date, independence, decisions and unresolved issues in
   the form. A completed form is a claim to review, not automatic trading authority.

The gold review also needs corrected/replacement October data and a verified
source-specific session schedule; the annual report deliberately records failure.

## Reproduce preparation

After collecting responses into a new directory as documented in
[model evaluation](model-evaluation.md):

```sh
uv run python -m services.news_intelligence.review_packet \
  --corpus examples/intelligence/primary-review/fresh-v5-pilot-v4.json \
  --freeze reports/fresh-v5-label-freeze-2026-10-29.json \
  --responses reports/generated/fresh-v5-review-20261029/gemini-v5/responses.json \
  --output reports/generated/new-independent-review-packet
```

This is offline and does not call Gemini. Preparation verifies corpus/response
binding and every real excerpt's source-review hash. Existing packets are never
overwritten. Neither this command nor a perfect score grants independent approval.
