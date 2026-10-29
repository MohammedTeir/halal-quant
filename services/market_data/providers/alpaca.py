"""Read-only Alpaca IEX daily equity adapter; never connects to an order endpoint.

Daily timestamps are session labels at midnight in New York, not bar close times.
The explicit market calendar determines closes, including DST and shortened days.
"""

import csv
import hashlib
import io
import json
import math
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from pydantic import SecretStr

from services.market_data.csv_data import DataSpec
from services.market_data.sessions import Schedule, Session

NEW_YORK = ZoneInfo("America/New_York")
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class AlpacaError(RuntimeError):
    pass


class AlpacaDaily:
    def __init__(self, key: SecretStr, secret: SecretStr, *, transport=None):
        if not key.get_secret_value() or not secret.get_secret_value():
            raise AlpacaError("ALPACA_NOT_CONFIGURED")
        self._key, self._secret, self._transport = key, secret, transport

    def _get(self, client, url, params):
        try:
            with client.stream("GET", url, params=params) as response:
                if response.status_code != 200:
                    raise AlpacaError("ALPACA_REQUEST_REJECTED")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise AlpacaError("ALPACA_RESPONSE_TOO_LARGE")
            return json.loads(raw)
        except (httpx.HTTPError, ValueError):
            raise AlpacaError("ALPACA_RESPONSE_UNAVAILABLE") from None

    def fetch(
        self,
        symbol: str,
        asset_class: str,
        start: date,
        end: date,
        *,
        clock=None,
        adjustment="split",
    ):
        # This adapter intentionally supports whole-session equity candles only.
        if (
            not symbol.isascii()
            or not symbol.replace(".", "").replace("-", "").isalnum()
            or len(symbol) > 32
            or asset_class not in ("stock", "etf")
            or not isinstance(start, date)
            or not isinstance(end, date)
            or start > end
            or adjustment not in ("split", "raw")
        ):
            raise ValueError("Valid equity symbol, asset class and date window required")
        received = (clock or (lambda: datetime.now(UTC)))()
        if received.tzinfo is None or end >= received.astimezone(NEW_YORK).date():
            raise ValueError("Only completed prior-date sessions may be acquired")
        headers = {
            "APCA-API-KEY-ID": self._key.get_secret_value(),
            "APCA-API-SECRET-KEY": self._secret.get_secret_value(),
        }
        start_at = datetime.combine(start, time.min, NEW_YORK).astimezone(UTC)
        # Query through end-of-day without treating a day's label as its close.
        end_at = datetime.combine(end, time.max, NEW_YORK).astimezone(UTC)
        pages, bars, tokens = [], [], set()
        params = {
            "start": start_at.isoformat(),
            "end": end_at.isoformat(),
            "timeframe": "1Day",
            "adjustment": adjustment,
            "feed": "iex",
            "limit": 10000,
        }
        with httpx.Client(
            headers=headers,
            timeout=20,
            verify=True,
            trust_env=True,
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            calendar = self._get(
                client,
                "https://paper-api.alpaca.markets/v2/calendar",
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                },
            )
            for _ in range(100):
                page = self._get(
                    client, f"https://data.alpaca.markets/v2/stocks/{symbol}/bars", params
                )
                if (
                    not isinstance(page, dict)
                    or page.get("symbol") != symbol
                    or not isinstance(page.get("bars"), list)
                ):
                    raise AlpacaError("ALPACA_INVALID_BARS")
                pages.append(page)
                bars.extend(page["bars"])
                token = page.get("next_page_token")
                if not token:
                    break
                if not isinstance(token, str) or len(token) > 4096 or token in tokens:
                    raise AlpacaError("ALPACA_INVALID_PAGINATION")
                tokens.add(token)
                params["page_token"] = token
            else:
                raise AlpacaError("ALPACA_PAGINATION_LIMIT")
        completed = (clock or (lambda: datetime.now(UTC)))()
        if completed.tzinfo is None or completed < received:
            raise ValueError("Acquisition clock moved backwards")
        received = completed
        try:
            if not isinstance(calendar, list):
                raise TypeError("Expected calendar")
            sessions = []
            closes = {}
            for row in calendar:
                day = date.fromisoformat(row["date"])
                if not start <= day <= end or day in closes:
                    raise ValueError("Invalid calendar day")
                opening = datetime.combine(day, time.fromisoformat(row["open"]), NEW_YORK)
                closing = datetime.combine(day, time.fromisoformat(row["close"]), NEW_YORK)
                sessions.append(Session(opens_at=opening, closes_at=closing))
                closes[day] = closing.astimezone(UTC)
            output = io.StringIO()
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(["timestamp", "Open", "High", "Low", "Close", "Volume"])
            previous = None
            for bar in bars:
                label = datetime.fromisoformat(bar["t"])
                if label.tzinfo is None:
                    raise ValueError("Naive provider timestamp")
                local_label = label.astimezone(NEW_YORK)
                if local_label.time() != time.min:
                    raise ValueError("Daily timestamp is not a midnight session label")
                close = closes[local_label.date()]
                if close > received or (previous is not None and close <= previous):
                    raise ValueError("Incomplete, duplicate or unordered candle")
                previous = close
                values = [bar[key] for key in ("o", "h", "l", "c", "v")]
                if any(type(value) not in (int, float) for value in values):
                    raise ValueError("Non-numeric OHLCV")
                o, h, low, c, v = values
                if (
                    not all(math.isfinite(value) for value in values)
                    or min(o, h, low, c) <= 0
                    or v < 0
                    or low > min(o, c)
                    or h < max(o, c)
                ):
                    raise ValueError("Invalid OHLCV bounds")
                writer.writerow([close.isoformat(), *values])
            spec = DataSpec(
                source="alpaca_iex",
                symbol=symbol,
                asset_class=asset_class,
                timeframe_seconds=86400,
                price_basis="split_adjusted" if adjustment == "split" else "unadjusted",
                volume_basis="split_adjusted" if adjustment == "split" else "as_reported",
                adjustment_rounding_quantum=Decimal("0.01") if adjustment == "split" else None,
                retrieved_at=received,
            )
            schedule = Schedule(
                source="alpaca_calendar",
                venue="US_EQUITIES",
                symbol=symbol,
                retrieved_at=received,
                coverage_start=start_at,
                coverage_end=end_at,
                sessions=sessions,
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            raise AlpacaError("ALPACA_INVALID_OBSERVATIONS") from None
        return {
            "csv": output.getvalue(),
            "metadata": spec.model_dump(mode="json"),
            "schedule": schedule.model_dump(mode="json"),
            "raw": {"calendar": calendar, "bar_pages": pages},
            "feed": "iex",
            "consolidated_market_coverage": False,
            "provider_independently_verified": False,
            "corporate_actions_independently_verified": False,
        }


def save_snapshot(path: Path, snapshot: dict):
    # Refuse overwrites and keep the raw provider response for provenance audits.
    path.mkdir(parents=True, exist_ok=False)
    files = {"bars.csv": snapshot["csv"].encode()}
    for name in ("metadata", "schedule", "raw"):
        files[name + ".json"] = (
            json.dumps(snapshot[name], sort_keys=True, indent=2, allow_nan=False) + "\n"
        ).encode()
    for name, content in files.items():
        with (path / name).open("xb") as output:
            output.write(content)
    manifest = {
        "feed": "iex",
        "consolidated_market_coverage": False,
        "authorized_for_entry": False,
        "sha256": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }
    with (path / "manifest.json").open("x") as output:
        json.dump(manifest, output, indent=2, sort_keys=True)
        output.write("\n")
