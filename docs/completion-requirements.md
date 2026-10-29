# Milestone 3–4 completion requirements

The original blueprint's software acceptance is implemented: timestamps,
provenance, freshness, structured classification, injection boundaries and
deterministic event/gate tests pass. Full external sign-off still has two concrete
blockers. Keys, wildcard access and model compatibility are already verified.

## Milestone 3: verified historical coverage

A twelve-month real download/recomputation audit of HistData XAUUSD for 2025 validates
11 months, yielding 5,335 1h and 1,151 4h complete bid bars. October's duplicate and
backward minute labels are rejected. The [annual audit](../reports/gold-history-audit-2025-2026-10-29.json)
therefore fails its full-year structural gate. It does not silently approve a
stitched dataset with the rejected month removed.

To close the stricter historical/source gate:

1. Obtain a corrected October archive or an independently assessed replacement
   with explicit quote basis, timestamps and provenance. Do not guess timestamp
   corrections or mix providers without a source-comparison audit.
2. Obtain a source/venue-specific gold session schedule, including daily breaks,
   holidays and exceptional closures. HistData's public FAQ does not independently
   establish such a schedule. Weekend heuristics cannot prove completeness.
3. Reconcile missing intervals against that schedule, retain unresolved gaps and
   have the reviewer assess whether bid-only/no-volume data suits the intended
   research. A passed structural month is not price/execution certification.

Official FOMC access and eight 2026 date-only events are already validated; the
older Finnhub 403 is not a blocker for that replacement path.

## Milestone 4: independent review

V4's broader frozen real-source pilot failed at 10/16. V5 passes the unchanged
16/16 regression plus 8/8 fresh blind pilot. Labels and failed evidence are retained.
The coding assistant authored both labels and implementation, so these results
cannot establish an author-independent review.

A separate reviewer needs to inspect primary sources/labels first, record
independence and disagreements, then examine outputs and sample omissions. The
[review guide and prepared packet](independent-review.md) make that work concrete.
The existing sample lacks ETF-specific news, secondary-source conflicts and broad
company-event coverage; the reviewer must assess suitability and define/freeze any
additional representative sample before inference. Historical examples may overlap
model pretraining. No statistically representative accuracy is established.

No more API keys or environment publication are required to use the implemented
paths. No environment settings were changed. Live trading remains disabled;
independent review is not a substitute for Milestone 5/6/8/9 controls.
