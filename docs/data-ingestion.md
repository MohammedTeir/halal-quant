# Market, news and economic data — Milestone 3

Status: provider-neutral ingestion and point-in-time reads are implemented and
locally validated. No production provider is connected. All checked-in examples
and recorded smoke observations are synthetic. This is not a complete real-data,
corporate-action or historical news validation pipeline.

## Data contracts

Historical OHLCV uses the [CSV research contract](python-research.md#historical-csv-inputs).
The metadata now explicitly declares `volume_basis`: `as_reported` (default) or
`split_adjusted`, independently of the OHLC price basis. Existing metadata remains
compatible; a declaration alone does not verify corporate-action arithmetic.

Facts use [DataBatch](contracts/data-batch-v1.schema.json), containing one provider,
one kind (`news`, `calendar`, `corporate_actions`), an idempotent `batch_id`, a
`synthetic` label, and up to 100 matching records. Every record must match the batch
provider, kind and synthetic label. Unknown fields and client-supplied `received_at`
are rejected. The server assigns receipt time. Use a new source revision for a
correction and a new batch ID for a later successful poll.

- [News](contracts/news-event-v1.schema.json): provider/item/revision, publication,
  source name, HTTPS attribution URL, headline, optional summary and explicit
  symbol/asset-class relevance tags. Whitespace is normalized in headline/source.
  URLs with credentials are rejected and are never fetched by this service.
- [Economic calendar](contracts/economic-event-v1.schema.json): provider/item/revision,
  publication, scheduled time, type, severity, relevance tags and cancellation flag.
  Schedules may be in the future. A cancellation/reschedule is a new immutable
  revision; historical queries keep the schedule known at their requested time.
  Actual-versus-forecast economic results are not implemented.
- [Corporate actions](contracts/corporate-action-v1.schema.json): symbol, publication,
  effective time, split ratio **new shares / old shares**, or USD cash dividend.
  Forward/reverse splits require a positive non-unit ratio. Cash dividends require
  a positive cash amount and no split ratio. Other action types remain unsupported.

News/calendar tags are supplied assertions, not an implemented company/entity or
ETF-holdings relevance engine. Provider names, content and authenticity are not
independently verified. News text remains untrusted data; there is no LLM or order
execution hook in ingestion.

## Import and read

The running API uses distinct external credentials:
`DASHBOARD_API_KEY`, `TRADINGVIEW_WEBHOOK_KEY`, `DATA_INGESTION_KEY` and
`ANALYSIS_API_KEY` (see the intelligence guide). The new key
is only for importing facts; it cannot read dashboard routes. Dashboard and webhook
credentials cannot import data. Blank credentials deny access. Configure values
in your local environment or preserved `.env`; never commit or paste credentials.

Start/migrate the stack as documented in README. Import a synthetic example with
an already-exported data key:

```sh
curl --fail-with-body http://127.0.0.1:8000/api/v1/data/import \
  -H "Content-Type: application/json" \
  -H "X-Data-Key: ${DATA_INGESTION_KEY}" \
  --data-binary @examples/data/news-batch.json
```

Calendar and corporate-action batch examples are beside it. These example
publication timestamps must already have occurred when submitted. Do not change
a stored source revision in place; conflicts return 409. Duplicate batches return
the original receipt/counters and do not write another audit or refresh a feed.
A new batch containing unchanged source records can record a successful poll with
zero inserts and duplicate-record counts. An empty batch is an explicit successful
no-news poll. Invalid records or immutable conflicts roll back the entire batch,
including feed freshness and audit writes. Concurrent identical imports produce a
single stored batch and audit. This behavior is tested against PostgreSQL and SQLite.

Dashboard bearer authentication protects:

| Route | Semantics |
|---|---|
| `GET /api/v1/news` | Latest known source revisions, grouped by canonical article URL with all source observations |
| `GET /api/v1/economic-events` | Latest known schedule/cancellation revisions |
| `GET /api/v1/corporate-actions` | Latest known source action revisions |
| `GET /api/v1/data/status?provider=...&kind=...` | Point-in-time successful-poll age and feed availability |

Fact reads accept `as_of` (aware, not in the future), `symbol` and `limit` 1–100;
news/calendar also accept `asset_class`. Tags match exactly; combined filters use
AND. Calendar-wide macro events without explicit symbols require asset-class or
unfiltered reads. Results include receipt time, immutable server `source_id` and provenance. These
are bounded inspection endpoints, not a complete paginated archive export.

## Point-in-time behavior and deduplication

A source revision is visible only when **publication <= as_of and server receipt
<= as_of**. Among visible revisions, the highest provider/item revision wins.
An older revision arriving late cannot replace a higher known revision. Late
historical imports are not backdated: news first imported in 2026 does not become
available to a 2020 simulation. Historical research needs verified historical
availability/receipt evidence and a dedicated replay design; neither provider
publication alone nor a hand-edited timestamp establishes that evidence.

News URL normalization removes fragments, `utm_*`, `fbclid` and `gclid`, sorts
remaining query parameters, and preserves parameters that may identify an article.
Equivalent URLs group into one story while retaining each provider's source
observation. Corrections remain immutable rows. Same-story text appearing at
unrelated URLs is not semantically deduplicated. Provider adapters must assign
stable IDs and monotonic revision numbers when content changes.

Feed age measures the most recent successful poll, not the newest article's age.
`maximum_age_seconds` ranges from 1–86400 (default 900); the boundary is inclusive.
Missing polls return MISSING; old polls return STALE. A successful recent poll is
FRESH, even if it returned no articles. Synthetic polls can be FRESH but always
return `required_feed_available: false`. `provider_independently_verified` and
`authorized_for_entry` remain false. A fresh non-synthetic poll proves only that
an authenticated caller supplied a successful observation, not provider health,
news completeness, instrument compliance or permission to trade. Provider failure
recording, worker retries and actual feed health probes remain adapter work.

## Split-adjustment audit

A runnable synthetic example checks raw against adjusted OHLCV:

```sh
uv run python -m services.market_data.validate_actions \
  --raw-csv examples/data/raw.csv --raw-metadata examples/data/raw-metadata.json \
  --adjusted-csv examples/data/adjusted.csv \
  --adjusted-metadata examples/data/adjusted-metadata.json \
  --actions examples/data/action-observations.json \
  --as-of 2020-01-08T00:00:00Z --output reports/generated/split-audit.json
```

Use a new output path each time. The action file contains
[ActionObservation](contracts/action-observation-v1.schema.json) objects: nested
`action` plus explicitly asserted `received_at`. This offline ledger format is not
accepted as a client receipt override by the API. Production replay must obtain
those observations from authoritative storage or verified historical archives.

Raw/adjusted snapshots must match source, symbol, asset class, timeframe and close
index. The checker applies only known splits effective by the final bar: earlier
OHLC prices are divided by cumulative split ratios; effective-bar prices are not
adjusted for that split. Volume is multiplied by the ratio only when its declared
basis is split-adjusted. Multiple chronological splits compose; conflicting source
revisions, duplicate split instants, invalid timestamps and unsupported numerical
precision fail. Comparisons use relative tolerance 1e-7 and absolute tolerance 1e-8.

The audit saves input/ledger hashes, applied revisions, basis and consistency flags.
It exits 0 on a match, 1 on an arithmetic mismatch (with a saved report), or 2 on
invalid inputs/existing output. No files are overwritten. Raw equity loading is
permitted only through the explicit audit override and remains rejected by the
research strategies. Total-return/dividend arithmetic, action-ledger completeness,
provider authenticity and issuer verification are not established by this audit.
Cash-dividend facts can be stored but are not used to adjust prices here.

## Acceptance and operations

The data increment added 17 ingestion/API tests and 11 split-audit tests.
The current full suite has 153 passing tests. It covers migrations/drift, preserving existing signals through
upgrade, concurrent idempotency, receipt/publication timing, corrections,
attribution, scope filters, stale/missing/synthetic feeds, invalid/atomic batches,
forward/reverse splits, volume, revisions and CLI exit codes. An actual full-stack
HTTP smoke and API restart check also pass; see [recorded data evidence](../reports/data-ingestion-smoke.json)
and [split-audit evidence](../reports/split-audit-smoke.json).

With matching credentials exported for the running local API, run
`uv run python -m scripts.data_smoke --output reports/generated/data-smoke.json`.
It intentionally persists three synthetic facts and their audits. The additive
migration is `0002_data_events`. Current API readiness additionally requires `0003_intelligence`; see the intelligence guide. Downgrading
to 0001 removes data-event tables and their contents, so only test that path against
disposable databases. Existing signal/audit tables are retained by that downgrade.

Remaining Milestone 3 work: select and verify real data sources, handle source
licensing/quality, implement fetch workers and health/failure observations, validate
actual corporate actions and exchange sessions, and acquire trustworthy historical
news availability. The research runner is still technical-only and does not yet
consume these fact stores or enforce event windows. Milestone 4 now adds advisory contracts and deterministic entry restrictions; real
model validation and Milestone 5 compliance/risk authorities remain necessary before
paper promotion.
