# First four milestones: completion checklist

The first four milestones are **not all complete**. Local automated acceptance is
recorded below; external evidence cannot be replaced by fixtures or documentation.
Milestones 1 and the agreed Python version of 2 meet their local acceptance gates.
Optional Pine compilation is not required for the agreed Python workflow.

| Milestone | Local evidence | Remaining completion gate |
|---|---|---|
| 1: foundation | API/container startup and persistence previously passed; current full PostgreSQL regression, migrations and schema-drift checks pass | Hosted CI passed for `68ab48f`; final fix revision still needs its own hosted result. |
| 2: strategies | All three Python implementations execute long-only; causal/future-mutation tests, synthetic default train/holdout runs and repeatability pass | No outstanding local implementation gate. Real-data profitability belongs to Milestone 6 and is not claimed here. |
| 3: data | Alpaca/Finnhub/BLS adapters pass mocked HTTP/normalization tests; atomic revisioned imports, resumable file worker, action arithmetic, retrieval cutoffs, session/DST/early-close/missing-bar checks pass | Real acquisition passed for 17 AAPL IEX candles, 108 news observations and 313 BLS events. Broader entitlements/provenance remain unverified. Obtain complete action history and spot-gold candles. Complete company-earnings/FOMC calendar coverage and per-target feed-health verification. Audit real raw/adjusted snapshots and retained historical receipt evidence. |
| 4: intelligence/decisions | Strict evidence/target contracts, deterministic gates, durable Gemini jobs, adversarial boundary tests, frozen quality scorer and crash-safe collector pass | Configured model metadata and real generation pass; the frozen diagnostic fails (7/12 label matches, 8 valid responses, two ambiguous timeouts and two unattempted cases). Diagnose latency/policy behavior without automatically recalling ambiguous cases. Independently review labels, source credibility, representative held-out quality and adversarial results; retain actual model versions/usage and human review evidence. |

## What changed in this completion pass

- Read-only, bounded/paginated Alpaca IEX daily acquisition with raw archives,
  hashes and session-label-to-close conversion. Finite OHLCV and full schedule
  coverage are validated; incomplete/duplicate/current-day data fail.
- Finnhub company-news acquisition and BLS schedule acquisition with local content
  revisions, authoritative server receipts and atomic multi-batch poll persistence.
- Restart-safe provider-normalized file worker; malformed/conflicting batches cannot
  refresh feed health; replays do not invent a new receipt.
- Retrieval cutoff enforcement and sourced exchange-session audit tooling.
- Frozen model-quality/adversarial corpus, strict scorer and exclusive-run Gemini
  collector. Mock acceptance cannot become a live-quality or approval claim.
- Provider/key instructions, limits and reproducible commands in
  [data providers](data-providers.md) and [model evaluation](model-evaluation.md).

## Published configuration and remaining external gates

1. Alpaca/Finnhub credentials are now ready and real requests succeeded. Confirm
   account entitlements, coverage and current free-tier limits beyond this sample.
2. Gemini credentials/model/enablement are ready; `gemini-3.5-flash-lite` metadata
   and generation succeeded. Resolve the failed diagnostic and independently review quality.
3. Provider HTTPS destinations are now active. TLS verification and the proxy
   were preserved. No environment configuration was edited or published during testing.
4. Run the acquisition/audit and live evaluation commands in the linked guides;
   preserve reports and independently review the source/model limitations.
5. Fill the missing gold/action/FOMC/earnings and per-target coverage gates before
   declaring Milestone 3 complete. No API key alone fills these data requirements.

Keep this checklist open until its evidence exists. Live trading remains disabled;
no data/model test establishes Shariah approval or permission to execute an order.

## Recorded live follow-up (2026-10-29)

See [provider results](../reports/live-provider-acceptance-2026-10-29.json) and
[Gemini diagnostic](../reports/gemini-live-diagnostic-2026-10-29.json). The current
regression passes 259 tests on isolated SQLite with real credentials removed from
the test process. BLS lacks source publication stamps in this response; the fix
marks first observation explicitly and preserves existing payload identities.
A real unchanged re-poll preserves event revisions. Raw source archives and the
isolated acceptance database remain in ignored local data directories.
