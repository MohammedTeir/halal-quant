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
