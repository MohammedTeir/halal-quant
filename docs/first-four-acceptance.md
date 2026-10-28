# First four milestones: completion checklist

The first four milestones are **not all complete**. Local automated acceptance is
recorded below; external evidence cannot be replaced by fixtures or documentation.
Milestones 1 and the agreed Python version of 2 meet their local acceptance gates.
Optional Pine compilation is not required for the agreed Python workflow.

| Milestone | Local evidence | Remaining completion gate |
|---|---|---|
| 1: foundation | API/container startup and persistence previously passed; current full PostgreSQL regression, migrations and schema-drift checks pass | Hosted CI for the final pushed revision must be observed. GitHub API access currently returns Forbidden in this environment. |
| 2: strategies | All three Python implementations execute long-only; causal/future-mutation tests, synthetic default train/holdout runs and repeatability pass | No outstanding local implementation gate. Real-data profitability belongs to Milestone 6 and is not claimed here. |
| 3: data | Alpaca/Finnhub/BLS adapters pass mocked HTTP/normalization tests; atomic revisioned imports, resumable file worker, action arithmetic, retrieval cutoffs, session/DST/early-close/missing-bar checks pass | Configure provider accounts and network access; verify actual responses/entitlements and provenance. Obtain complete action history and spot-gold candles. Complete company-earnings/FOMC calendar coverage and per-target feed-health verification. Audit real raw/adjusted snapshots and retained historical receipt evidence. |
| 4: intelligence/decisions | Strict evidence/target contracts, deterministic gates, durable Gemini jobs, adversarial boundary tests, frozen quality scorer and crash-safe collector pass | Configure Gemini model/key/network; run the frozen diagnostic against the real model. Independently review labels, source credibility, representative held-out quality and adversarial results; retain actual model versions/usage and human review evidence. |

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

## Required external configuration

1. Create/select Alpaca and Finnhub accounts; confirm current free-tier entitlements.
   Configure `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `FINNHUB_API_KEY` server-side.
2. Configure `GEMINI_API_KEY`, a JSON-capable `GEMINI_MODEL` and explicitly enable
   `GEMINI_ENABLED` only for intended inference/evaluation runs.
3. Allow the provider HTTPS destinations through the cloud's supported environment
   configuration. Preserve TLS verification and the proxy. Current enforced policy
   has no provider destinations or ready credentials; no real provider requests
   were sent during this pass.
4. Run the acquisition/audit and live evaluation commands in the linked guides;
   preserve reports and independently review the source/model limitations.
5. Fill the missing gold/action/FOMC/earnings and per-target coverage gates before
   declaring Milestone 3 complete. No API key alone fills these data requirements.

Keep this checklist open until its evidence exists. Live trading remains disabled;
no data/model test establishes Shariah approval or permission to execute an order.
