"""Finnhub company earnings, conservatively represented as date-only US events."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from packages.schemas.data_events import EconomicEvent
from services.market_data.event_store import digest
from services.news_intelligence.providers.finnhub import MAX_BYTES, FinnhubError, FinnhubNews


class FinnhubEarnings(FinnhubNews):
    def fetch(self, symbol: str, start: date, end: date, *, clock=None):
        if (
            not symbol.isascii()
            or not symbol.replace(".", "").replace("-", "").isalnum()
            or len(symbol) > 32
            or start > end
            or (end - start).days > 366
        ):
            raise ValueError(
                "Valid company symbol and earnings window of at most 366 days required"
            )
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
                    "https://finnhub.io/api/v1/calendar/earnings",
                    headers={"X-Finnhub-Token": self._token.get_secret_value()},
                    params={"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()},
                ) as response,
            ):
                if response.status_code != 200:
                    raise FinnhubError("FINNHUB_EARNINGS_REJECTED")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise FinnhubError("FINNHUB_RESPONSE_TOO_LARGE")
            data = httpx.Response(200, content=bytes(raw)).json()
        except (httpx.HTTPError, ValueError):
            raise FinnhubError("FINNHUB_RESPONSE_UNAVAILABLE") from None
        now = (clock or (lambda: datetime.now(UTC)))()
        try:
            if (
                now.tzinfo is None
                or not isinstance(data, dict)
                or not isinstance(data["earningsCalendar"], list)
                or len(data["earningsCalendar"]) > 1000
            ):
                raise ValueError("Malformed earnings schedule")
            events, seen = [], set()
            for row in data["earningsCalendar"]:
                day = date.fromisoformat(row["date"])
                quarter, year = row["quarter"], row["year"]
                if (
                    row["symbol"] != symbol
                    or not start <= day <= end
                    or type(quarter) is not int
                    or not 1 <= quarter <= 4
                    or type(year) is not int
                    or not 1900 <= year <= 2200
                ):
                    raise ValueError("Invalid company/fiscal period")
                identity = digest([symbol, year, quarter])
                if identity in seen:
                    raise ValueError("Ambiguous duplicate earnings period")
                seen.add(identity)
                events.append(
                    EconomicEvent(
                        provider="finnhub_earnings",
                        item_id=identity,
                        published_at=now,
                        publication_basis="observed_at",
                        title=f"{symbol} fiscal {year} Q{quarter} earnings",
                        event_type="earnings",
                        scheduled_at=datetime.combine(day, time.min, ZoneInfo("America/New_York")),
                        scheduled_precision="date",
                        scheduled_timezone="America/New_York",
                        severity="high",
                        symbols=[symbol],
                        asset_classes=["stock"],
                    )
                )
        except (ValueError, KeyError, TypeError):
            raise FinnhubError("FINNHUB_INVALID_EARNINGS") from None
        return bytes(raw), events, now


def coverage_window(symbol, start, end):
    from packages.schemas.data_events import FeedCoverage

    zone = ZoneInfo("America/New_York")
    return FeedCoverage(
        symbols=[symbol],
        asset_classes=["stock"],
        purpose="earnings",
        starts_at=datetime.combine(start, time.min, zone),
        ends_at=datetime.combine(end + timedelta(days=1), time.min, zone),
    )
