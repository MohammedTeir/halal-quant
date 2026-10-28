"""Read-only Finnhub company-news adapter; credentials remain in an HTTP header."""

from datetime import UTC, date, datetime

import httpx
from pydantic import SecretStr

from packages.schemas.data_events import NewsEvent
from services.market_data.event_store import digest

MAX_BYTES = 4 * 1024 * 1024


class FinnhubError(RuntimeError):
    pass


class FinnhubNews:
    def __init__(self, token: SecretStr, *, transport=None):
        if not token.get_secret_value():
            raise FinnhubError("FINNHUB_NOT_CONFIGURED")
        self._token, self._transport = token, transport

    def fetch(self, symbol: str, asset_class: str, start: date, end: date, *, now: datetime):
        if (
            not symbol.isascii()
            or not symbol.replace(".", "").replace("-", "").isalnum()
            or len(symbol) > 32
            or asset_class not in ("stock", "etf")
            or start > end
            or now.tzinfo is None
            or end > now.date()
        ):
            raise ValueError("Valid equity symbol/date range and aware acquisition time required")
        try:
            with (
                httpx.Client(
                    timeout=20,
                    verify=True,
                    trust_env=True,
                    follow_redirects=False,
                    transport=self._transport,
                ) as client,
                client.stream(
                    "GET",
                    "https://finnhub.io/api/v1/company-news",
                    headers={"X-Finnhub-Token": self._token.get_secret_value()},
                    params={"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()},
                ) as response,
            ):
                if response.status_code != 200:
                    raise FinnhubError("FINNHUB_REQUEST_REJECTED")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise FinnhubError("FINNHUB_RESPONSE_TOO_LARGE")
            # HTTPX exposes its JSON decoder; use a response without transport state.
            items = httpx.Response(200, content=bytes(raw)).json()
        except (httpx.HTTPError, ValueError):
            raise FinnhubError("FINNHUB_RESPONSE_UNAVAILABLE") from None
        try:
            if not isinstance(items, list) or len(items) > 10000:
                raise TypeError("Expected bounded news list")
            events, seen = [], set()
            for item in items:
                if type(item["datetime"]) is not int or type(item["id"]) is not int:
                    raise TypeError("Provider ID and publication time must be integers")
                published = datetime.fromtimestamp(item["datetime"], UTC)
                if published > now or not start <= published.date() <= end:
                    raise ValueError("News publication outside requested window")
                event = NewsEvent(
                    provider="finnhub",
                    item_id=str(item["id"]),
                    published_at=published,
                    source_name=item["source"],
                    url=item["url"],
                    headline=item["headline"],
                    summary=item["summary"],
                    symbols=[symbol],
                    asset_classes=[asset_class],
                )
                # Preserve target scope in source identity when polling multiple symbols.
                event = event.model_copy(
                    update={"item_id": digest([symbol, asset_class, event.item_id])}
                )
                if event.item_id in seen:
                    raise ValueError("Duplicate provider news ID")
                seen.add(event.item_id)
                events.append(event)
        except (ValueError, KeyError, TypeError, OverflowError, OSError):
            raise FinnhubError("FINNHUB_INVALID_OBSERVATIONS") from None
        return events
