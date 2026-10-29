# Data acquisition and acceptance

Milestone 3 now includes read-only Alpaca daily candles, Finnhub company-news and
BLS release-calendar adapters, an atomic ingestion worker, and exchange-session
validation. A live follow-up passed on 2026-10-29: 17 AAPL IEX daily candles, 108 company-news
observations and 313 BLS calendar events. Sample compatibility is established;
complete historical coverage, account entitlements, provider accuracy and action
completeness remain unverified. The original first-four completion request remains open until
[the external acceptance checklist](first-four-acceptance.md) passes.

## Recommended starting combination

| Need | Starting source | Limit that must be validated |
|---|---|---|
| U.S. stock/ETF daily candles and sessions | [Alpaca Basic](https://docs.alpaca.markets/docs/about-market-data-api) | IEX coverage is a subset of U.S. trading; historical access, delay and quotas depend on account entitlement. This adapter requests split adjustment, not total return. |
| Company news | [Finnhub](https://finnhub.io/docs/api/company-news) | Free-tier availability, archive depth and quotas must be checked for your account; publication metadata does not establish publisher credibility or complete target coverage. |
| CPI and employment release schedule | [BLS](https://www.bls.gov/schedule/news_release/) | Public calendar, no API key. It does not supply FOMC meetings, company earnings or a comprehensive economic calendar. |
| FOMC releases/schedules | [Federal Reserve](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) | Official reference; automatic adapter not yet implemented. Use verified normalized calendar imports until implemented. |
| Spot gold and complete corporate actions | Provider selection still required | IEX equity candles do not supply spot gold. A gold ETF must not silently substitute for the blueprint's gold instrument. Corporate-action completeness requires separate evidence. |

These are starting recommendations, not a claim that all required historical data
is available free. Confirm current terms, allowed use and pricing before deployment.
A comprehensive point-in-time history of news and ownership/compliance data may
require paid sources. Broker credentials here are used only for read-only calendar
access; no order endpoint exists in the adapter.

## Backend configuration

Set `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` and `FINNHUB_API_KEY` in the backend's
ignored `.env` or deployment environment. Commands read the same Pydantic settings
as the API. Never put values in command arguments, Git, frontend bundles or chat.
In this managed cloud, allow HTTPS destinations `data.alpaca.markets`,
`paper-api.alpaca.markets`, `finnhub.io`, `www.bls.gov`, and
`generativelanguage.googleapis.com` through environment configuration. These provider domains are now active in the published cloud environment. Keep the proxy and TLS verification.

## Acquire and audit candles

```sh
uv run python -m services.market_data.acquire_alpaca \
  --symbol YOUR_SYMBOL --asset-class stock \
  --start 2023-01-01 --end 2024-12-31 \
  --output data/alpaca/unique-snapshot
```

Use a real symbol and a historical date window ending before today's New York date.
The command requests `1Day`, `feed=iex`, `adjustment=split`; follows bounded pagination;
rejects redirects; and never retries provider failures automatically. It preserves
raw pages, calendar, CSV, metadata and checksums in a new directory. It converts
midnight New York session labels to actual exchange closes using the returned
calendar, preserving DST and early closes. It validates finite OHLCV, retrieval
cutoffs, ordering and the **entire declared schedule coverage**, including missing
first/last sessions. A failed post-download validation leaves the archive for review.

```sh
uv run python -m services.market_data.validate_sessions \
  --csv data/alpaca/unique-snapshot/bars.csv \
  --metadata data/alpaca/unique-snapshot/metadata.json \
  --schedule data/alpaca/unique-snapshot/schedule.json \
  --as-of 2026-10-28T00:00:00Z --output reports/generated/session-audit.json
```

Use an as-of at or after both snapshot receipt times. Exit 0 means the arithmetic
and schedule agree; 1 saves a mismatch report; 2 means invalid input. Explicit
schedule coverage must end before candle retrieval. Daily candles close at session
close; intraday candles use full intervals anchored at session open (partial final
bars are excluded). Weekly and extended-hours aggregation remain unsupported.
Schedule correctness itself needs independent exchange verification.

Also run the existing [split audit](data-ingestion.md). Provider-adjusted values alone
do not prove the action ledger is complete, historically available or correctly
adjusted. Do not promote these snapshots to release-quality research on this basis.

## Acquire and version news/calendar

Run migrations first. Each command writes a new archive and commits its entire
poll atomically using the existing event/audit ledger:

```sh
uv run python -m services.market_data.acquire_news \
  --symbol YOUR_SYMBOL --asset-class stock --start 2026-10-20 --end 2026-10-27 \
  --archive data/finnhub/unique-poll
uv run python -m services.macro_intelligence.acquire_bls \
  --archive data/bls/unique-poll
```

Finnhub requires an explicitly scoped company request. Its upstream item ID plus
target identifies a local source. BLS uses iCalendar UID; UTC/TZID dates, folded
lines, cancellations and source stamps are checked. Unsupported recurrence,
unknown timezone, malformed/empty calendars or future source stamps fail the poll.
BLS `LAST-MODIFIED`/`DTSTAMP`, when present, is labeled `publication_basis=provider_timestamp`;
it is not independently verified publication evidence. The actual live calendar
has no such stamp: `published_at` then records first observation with explicit
`publication_basis=observed_at`. Source publication time remains unknown. Unchanged
polls preserve the first observed event time; corrections receive a new revision
and observation time. No historical receipt is backdated. Legacy normalized events
without this optional field serialize exactly as before, preserving import IDs.

Adapters without monotonic upstream revisions receive a locally assigned revision
when observed content changes. Unchanged polls preserve earlier event receipts;
new poll records indicate successful acquisition. One failed chunk rolls back all
records, audits and health updates. Racing corrections fail rather than overwrite.
Archives preserve failed-import input; inspect the ledger before a deliberate retry.
No automatic download loop or API-startup calls consume provider quotas.

The existing `NEWS_PROVIDER`/`CALENDAR_PROVIDER` can select `finnhub`/`bls` for
research snapshots, but **do not treat these polls as complete required coverage**:
a company poll is not an all-symbol news feed, and BLS is not a complete calendar.
Provider-independent verification remains false and public decision data gates
remain closed. Complete per-target/source coverage verification before wiring them
to a trusted entry-data authority.

## Restart-safe normalized batch worker

For provider-produced files matching the [DataBatch contract](data-ingestion.md):

```sh
uv run python -m services.market_data.worker \
  --inbox data/inbox/news --provider YOUR_PROVIDER --kind news --limit 100
```

Publish complete files by writing a temporary non-JSON filename and atomically
renaming it to `.json`. The worker reads at most 4 MiB per file, rejects duplicate
JSON keys and wrong provider/kind, imports each file in one transaction, and
continues after failed files. It emits safe status/error codes and exits nonzero on
failure. Source files are preserved. The database ledger is its durable checkpoint;
a rerun of an old batch cannot refresh feed freshness. Genuine polls need new batch
IDs even when no events changed. An oversized inbox fails explicitly rather than
silently starving files beyond the limit; partition/archive acknowledged files.

A deployment scheduler may invoke this one-shot worker repeatedly. Serialize each
live provider poll and monitor its exit code, archive and `/api/v1/data/status`.
A stalled/failed schedule must become stale. Scheduling, live quotas, provider
completeness, restart drills and real history remain acceptance work.

The [schedule JSON Schema](contracts/session-schedule-v1.schema.json) describes
provider-normalized session inputs. It does not attest to their provenance.

## Corporate actions, date-only earnings and scoped freshness

Run Alembic head `0005_feed_coverage` before acquisition/API startup.

```sh
uv run python -m services.market_data.acquire_actions \
  --symbol AAPL --start 2020-08-01 --end 2020-09-04 \
  --archive data/alpaca/unique-actions
uv run python -m services.macro_intelligence.acquire_earnings \
  --symbol AAPL --start 2026-10-01 --end 2026-11-30 \
  --archive data/finnhub/unique-earnings
```

Actions support positive forward/reverse splits and USD cash dividends; unsupported
action types/foreign structures fail instead of silently asserting completeness.
Publication time is unknown and explicitly marked as first observation.
Earnings use stable symbol/fiscal-year/quarter IDs so a date correction becomes
a new revision. Before/after-market tags do not invent an exact release time:
`scheduled_precision=date` and `scheduled_timezone=America/New_York` conservatively
block the whole date plus configured margins. Absence from a later poll does not
silently cancel a known event. This adapter covers US-stock date semantics only.

`acquire_alpaca --adjustment raw` saves unadjusted audit inputs; strategy loading
still rejects them. The split-adjusted adapter declares
`adjustment_rounding_quantum=0.01`. The audit allows at most half this quantum only
on bars changed by split factors, checks their rounded grid, and keeps unchanged
bars/volume strict. Old snapshots without the declaration keep strict arithmetic.
The declaration cannot exceed one cent. The real AAPL 2020 split/volume audit
passes; that arithmetic does not establish a complete historical action ledger.

News, BLS, earnings and action commands attach target/purpose/window coverage to
successful polls. `GET /api/v1/data/coverage` requires dashboard authentication and
`provider`, `symbol`, `asset_class`, `purpose`, `window_start`, `window_end`; optional
`as_of` and `maximum_age_seconds` select point-in-time freshness. Coverage describes
the provider query window, not a guarantee of upstream completeness. It never
grants independent provider verification or trading permission. Macro-only polls
cannot satisfy earnings; old unscoped imports cannot satisfy target coverage.
Use `EARNINGS_PROVIDER=finnhub_earnings` to select the earnings source in decisions.
Spot-gold and broad Finnhub economic-calendar requests currently return 403. See
[remaining source requirements](completion-requirements.md).

## Free XAUUSD reference history and official FOMC replacement

```sh
uv run python -m services.market_data.acquire_gold \
  --year 2025 --month 9 --output data/gold/unique-september
uv run python -m services.macro_intelligence.acquire_fomc \
  --year 2026 --archive data/fomc/unique-2026
```

Gold uses HistData's normal free XAUUSD ASCII M1 download form; no account key or
payment is sent. Metadata records `quote_basis=bid` and
`volume_semantics=unavailable_zero_placeholder`. Source labels are fixed EST
without DST. Complete UTC buckets only are emitted; gaps/partial buckets are
reported. ZIP size/member and timestamp/OHLC checks fail closed; no files are
extracted using untrusted ZIP paths. September 2025 passes; October fails conflicting
duplicate-time checks. This conditional reference source is not certified execution
or liquidity data. See [source assessment](source-and-label-review.md).

FOMC uses the official calendar and imports observed-time, whole New York dates.
Cross-month meetings use the final calendar date. Unknown markup/dates, duplicates
or missing selected-year rows fail. Configure `FOMC_PROVIDER=federal_reserve` in
the backend to select scoped FOMC availability; all known calendar restrictions
are considered even without selecting this source. No announcement hour is invented.

## Recompute year-wide gold evidence

Downloaded HistData monthly directories use `YYYY-MM/source.zip`, derived candle
CSVs, metadata and manifests. Recompute every month rather than trusting manifests:

```sh
uv run python -m services.market_data.validate_gold_history \
  --root data/milestone34-20261029/gold --year 2025 \
  --output reports/generated/new-gold-year-audit.json
```

Exit 0 requires twelve structurally valid, matching monthly artifacts. Exit 1 saves
an audit with missing/rejected months and fails the annual gate; exit 2 rejects
invalid inputs/output paths. Source, derived candle and metadata hashes are checked;
artifact tampering cannot pass by editing a summary count. Existing reports are
never overwritten. This is offline and does not download or repair source files.
The actual 2025 audit validates 11 months and rejects October. Session certification,
continuous-year approval and execution authorization remain false.
