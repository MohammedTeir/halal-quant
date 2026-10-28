# API contracts — first increment

FastAPI generates OpenAPI at `/openapi.json` and interactive documentation at `/docs`.
Only the following routes are implemented; the other blueprint endpoints remain
future work. No endpoint authorizes an order.

| Method and path | Authentication | Result |
|---|---|---|
| `GET /health/live` | None | Research mode and live execution disabled |
| `GET /health/ready` | None | 200 when DB/tables/migration match; otherwise 503 |
| `POST /api/v1/webhooks/tradingview` | `X-Webhook-Key` | Validated technical observation and atomic audit |
| `GET /api/v1/signals` | `Authorization: Bearer …` | Stored candidate payloads, newest first |
| `GET /api/v1/audit` | `Authorization: Bearer …` | Ingestion audit records, newest first |

Read routes accept `limit` from 1–100, default 50, and return `{"items": [...]}`.
No cursor pagination, account scoping or production RBAC is implemented. Webhook and
dashboard credentials must differ; missing configuration denies access. Never put
real credentials in documentation or Pine scripts.

Example payload (replace event ID and timestamp for a current request):

```json
{
  "schema_version": "1.0",
  "event_id": "adaptive_pullback|NASDAQ:EXAMPLE|240|unique-bar|ENTRY_CANDIDATE",
  "strategy": "adaptive_pullback",
  "strategy_version": "1.0.0",
  "asset_class": "stock",
  "symbol": "NASDAQ:EXAMPLE",
  "timeframe": "240",
  "action": "ENTRY_CANDIDATE",
  "bar_time": "2026-10-28T12:00:00Z",
  "price": "100.25"
}
```

The [JSON Schema](contracts/signal-v1.schema.json) documents structural fields.
Runtime Pydantic validation additionally enforces finite positive decimal prices,
timezone-aware timestamps and strategy/asset consistency. Delivery validation
rejects new events over 15 minutes old or more than 30 seconds in the future.
Unknown fields and unsupported schema/strategy versions are rejected. Allowed
actions are ENTRY_CANDIDATE and EXIT_CANDIDATE.

First acceptance returns HTTP 200:

```json
{"event_id": "example-id", "duplicate": false, "authorized": false}
```

The same event ID and canonical payload returns `duplicate: true` without writing
another signal/audit. Reusing an ID with different content returns 409. Invalid
credentials return 401; invalid bodies or new stale/future events return 422.
Duplicate lookup precedes freshness validation, so an identical previously accepted
payload remains a no-op even after its freshness window. This never creates orders.

TradingView cannot attach the custom authentication header directly. A trusted,
TLS-protected gateway must authenticate the source and forward the header. That
gateway and its delivery acceptance are not implemented. Public production ingress
also needs rate/body limits, operational monitoring and production access controls.

## Data-fact API increment

The following routes now supplement the first increment. See [data ingestion](data-ingestion.md)
for the full contracts, examples, revision rules and remaining provider limitations.

| Method and path | Credential | Behavior |
|---|---|---|
| `POST /api/v1/data/import` | `X-Data-Key` | Atomic, idempotent batch for one provider/kind; server receipt and audit |
| `GET /api/v1/news` | Dashboard bearer | Latest known revisions grouped by normalized article URL; attribution retained |
| `GET /api/v1/economic-events` | Dashboard bearer | Point-in-time calendar schedules and cancellations |
| `GET /api/v1/corporate-actions` | Dashboard bearer | Point-in-time split/dividend facts |
| `GET /api/v1/data/status` | Dashboard bearer | Missing/stale/fresh observation and synthetic guard |

Read routes support aware `as_of`; fact lists also accept exact `symbol`, `limit`
1–100, and news/calendar accept `asset_class`. Future/naive cutoffs return 422.
Both publication and server receipt must be <= cutoff. Data imports reject future
publication, supplied receipt times, mixed provider/kind/synthetic labels, invalid
action fields and source-revision mutation. Use a new revision for corrections.

A batch response contains `batch_id`, `duplicate`, original `inserted`/`duplicates`
counters and server `received_at`. HTTP 200 is a durable fact import, not order
approval. Replays do not refresh feeds or duplicate audits. Conflicts return 409,
invalid data 422, invalid credentials 401 and unavailable write storage 503.
The successful new-batch counter `duplicates` counts pre-existing source records;
`duplicate` indicates replay of the entire batch.

Freshness measures a successful poll, not article age. Empty successful batches
are allowed. Synthetic feeds never satisfy `required_feed_available`; provider
verification and entry authorization remain false. Data import is not available
to dashboard/webhook credentials. Source failures and production rate/body limits
remain future adapter/operations work. Current API readiness requires `0003_intelligence`.

## Advisory intelligence and decisions

See [intelligence/decisions](intelligence-decisions.md) for the complete contracts.
`POST /api/v1/news/classifications` and `POST /api/v1/decisions/evaluate` require the
fourth distinct `X-Analysis-Key`. The former accepts a classification ID, declared
model/prompt versions and a strict JSON `raw_output` string referencing current
news `source_id` values with exact evidence quotes. The latter accepts only an
evaluation ID, stored signal ID, finite numeric score and optional aware cutoff.
No caller-supplied holdings, approvals or policy overrides are accepted.

Dashboard bearer reads are `GET /api/v1/news/classifications`, `GET /api/v1/decisions`
and `GET /api/v1/decisions/{evaluation_id}`. Lists accept bounded `limit` and aware
`as_of`; classifications also accept exact `symbol`. Missing recorded evaluations
return 404. Replays return the original immutable result with `duplicate: true`;
changed requests under an existing ID return 409. Invalid untrusted output,
invented citations, stale-source submissions and future/naive cutoffs return 422.
Successful writes and their audits commit together; concurrent repeats are idempotent.

Entry status is the first failed gate in data → compliance → instrument → events
→ risk → score order, with every check retained in `trace`. Positive advisory
recommendations cannot clear gates. The current public API returns WAIT_DATA for
entries and WAIT_OWNERSHIP for unverified exits because trusted authorities do not
yet exist. Every result has `authorized: false`; there is no execution endpoint.
A fresh webhook price is not a verified market snapshot. Prompt-injection text is
stored as source data and cannot add order/permission fields to an assessment.
