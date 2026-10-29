# Gold source-session investigation — 2026-10-29

## Result

**Investigation completed; provider-session certification not established.** All
353,940 normalized source-minute observations in the twelve 2025 HistData archives
were compared with independently published regular reference hours. The complete
[minute-gap report](../reports/gold-session-comparison-2025-2026-10-29.json) preserves
all 300 absent runs, including coverage boundaries, source hashes, exact-row
normalization proof, quote/time semantics and the reference snapshot/hash.

| Comparison against the regular reference | Result |
|---|---:|
| Gaps entirely in reference-closed time | 108 |
| Gaps overlapping reference-open and closed time | 157 |
| Gaps entirely in reference-open time | 35 |
| Missing minutes while reference says open | 14,133 |
| Missing minutes while reference says closed | 157,527 |
| Observed quotes while reference says closed | 9,459 |

The reference is the [official OANDA BVI hours table](https://www.oanda.com/bvi-en/cfds/hours-of-operation/),
whose XAU/USD CFD row says New York, Sun–Fri, 18:05–16:59. Snapshot verification
parses the actual table row and rejects absent/duplicate/changed hours or timezone.
New York DST is applied, while HistData timestamps retain their separately declared
fixed EST conversion. Intervals are minute-open `[open, close)`; boundary precision
is not independently established.

## What the comparison cannot establish

OANDA does not establish that it is HistData's quote venue. Its page retrieved in
2026 also does not establish 2025 historical holiday/exception hours. CFD reference
hours do not approve CFD instruments, custody or Shariah compliance. No central
spot-gold schedule is assumed and no CME futures schedule is substituted.

The longest reference-open overlaps include Christmas, Good Friday and New Year's
Day windows; holidays are possible explanations, not verified source exceptions.
There are also shorter reference-open-only gaps, including 2025-03-31 00:00–01:00
UTC, and quotes during reference-closed minutes. Low quote activity, venue timing,
clock conventions, historical holidays or missing data require source-specific
resolution. These counts do **not** prove actual HistData data loss or fraud.

Every gap has `verified_market_closure=false`. Overall source-venue binding,
historical holiday verification, session verification and entry authorization stay
false. No missing quote is filled and no timestamp or price is corrected to make
this comparison pass. The structural 12/12 archive pass remains valid within its
narrow scope; it is not session-completeness certification.

## Reproduce

Acquire into a new evidence directory (fixed official URL, verified TLS/proxy,
no redirects/retries, bounded 2MB response; no project key is sent):

```sh
uv run python -m services.market_data.gold_sessions acquire-reference \
  --output reports/generated/new-session-reference
```

Compare only after the full structural/artifact history audit passes:

```sh
uv run python -m services.market_data.gold_sessions compare \
  --root data/milestone34-exact-normalized-20261029/gold --year 2025 \
  --evidence reports/generated/source-session-review-20261029 \
  --output reports/generated/new-session-comparison.json
```

Use the retained evidence directory for exact historical reproduction; a fresh
snapshot is a new observation. Acquisition exits 0 on successfully archived,
recognized rule. Comparison deliberately exits 1 after saving a diagnostic because
it cannot certify provider sessions; invalid inputs exit 2. Existing outputs and
source snapshots are never overwritten.

To close source-session suitability, obtain HistData's source/venue-specific 2025
session and exception evidence, or acquire a separately reviewed source with its
own schedule. Then reconcile every remaining interval with that evidence. A
technical reviewer cannot invent the missing provider documentation.
