"""Read-only Alpaca corporate-action ledger for split/cash-dividend audits.

Ex-dates are represented at midnight America/New_York. Source publication time
is unavailable: these events explicitly retain their first observation timestamp.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx

from packages.schemas.data_events import CorporateAction
from services.market_data.providers.alpaca import AlpacaDaily, AlpacaError

SUPPORTED = {"forward_splits", "reverse_splits", "cash_dividends"}


def normalize_actions(pages, symbol, start, end, observed_at):
    records, seen = [], set()
    try:
        for page in pages:
            groups = page["corporate_actions"]
            if not isinstance(groups, dict) or any(
                key not in SUPPORTED and rows for key, rows in groups.items()
            ):
                raise ValueError("Unsupported action type in audit ledger")
            for kind, rows in groups.items():
                for row in rows:
                    day = date.fromisoformat(row["ex_date"])
                    if row["symbol"] != symbol or not start <= day <= end or row["id"] in seen:
                        raise ValueError("Wrong scope or duplicate corporate action")
                    seen.add(row["id"])
                    if row.get("foreign", False):
                        raise ValueError(
                            "Foreign action currency/structure requires separate verification"
                        )
                    if kind != "cash_dividends":
                        new_rate, old_rate = (
                            Decimal(str(row["new_rate"])),
                            Decimal(str(row["old_rate"])),
                        )
                        if (
                            not new_rate.is_finite()
                            or not old_rate.is_finite()
                            or min(new_rate, old_rate) <= 0
                        ):
                            raise ValueError("Share counts must be finite and positive")
                    values = (
                        {"cash_amount": Decimal(str(row["rate"]))}
                        if kind == "cash_dividends"
                        else {
                            "split_ratio": Decimal(str(row["new_rate"]))
                            / Decimal(str(row["old_rate"]))
                        }
                    )
                    if kind == "forward_splits" and values["split_ratio"] <= 1:
                        raise ValueError("Invalid forward split")
                    if kind == "reverse_splits" and values["split_ratio"] >= 1:
                        raise ValueError("Invalid reverse split")
                    records.append(
                        CorporateAction(
                            provider="alpaca_iex",
                            item_id=row["id"],
                            published_at=observed_at,
                            publication_basis="observed_at",
                            symbol=symbol,
                            action_type="cash_dividend" if kind == "cash_dividends" else "split",
                            effective_at=datetime.combine(
                                day, time.min, ZoneInfo("America/New_York")
                            ),
                            **values,
                        )
                    )
    except (KeyError, ValueError, TypeError, ArithmeticError):
        raise AlpacaError("ALPACA_INVALID_ACTIONS") from None
    return records


class AlpacaActions(AlpacaDaily):
    def acquire(self, symbol: str, start: date, end: date, *, clock=None):
        if (
            not symbol.isascii()
            or not symbol.replace(".", "").replace("-", "").isalnum()
            or len(symbol) > 32
            or start > end
        ):
            raise ValueError("Valid symbol and action window required")
        params = {
            "symbols": symbol,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": 1000,
            "types": "forward_split,reverse_split,cash_dividend",
        }
        pages, tokens = [], set()
        with httpx.Client(
            timeout=20,
            verify=True,
            trust_env=True,
            follow_redirects=False,
            transport=self._transport,
            headers={
                "APCA-API-KEY-ID": self._key.get_secret_value(),
                "APCA-API-SECRET-KEY": self._secret.get_secret_value(),
            },
        ) as client:
            for _ in range(100):
                page = self._get(client, "https://data.alpaca.markets/v1/corporate-actions", params)
                if not isinstance(page, dict):
                    raise AlpacaError("ALPACA_INVALID_ACTIONS")
                pages.append(page)
                token = page.get("next_page_token")
                if not token:
                    break
                if not isinstance(token, str) or len(token) > 4096 or token in tokens:
                    raise AlpacaError("ALPACA_INVALID_PAGINATION")
                tokens.add(token)
                params["page_token"] = token
            else:
                raise AlpacaError("ALPACA_PAGINATION_LIMIT")
        received = (clock or (lambda: datetime.now(UTC)))()
        if received.tzinfo is None:
            raise ValueError("Aware acquisition time required")
        return pages, normalize_actions(pages, symbol, start, end, received), received
