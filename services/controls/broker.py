"""Fixed-host read-only Alpaca paper capture; never submits/cancels orders.

Alpaca cash/buying power is not attested settled cash or a cash-account contract.
Those authority flags deliberately remain false for this adapter.
"""

import json
from datetime import UTC, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx

from services.market_data.event_store import digest

ROOT = "https://paper-api.alpaca.markets"
DATA = "https://data.alpaca.markets"


class BrokerError(RuntimeError):
    pass


def amount(value, *, positive=False, signed=False):
    try:
        number = Decimal(str(value))
        if (
            not number.is_finite()
            or (not signed and number < 0)
            or (positive and number <= 0)
            or abs(number.adjusted()) > 24
        ):
            raise ValueError
        return str(number)
    except (ValueError, ArithmeticError):
        raise BrokerError("BROKER_INVALID_AMOUNT") from None


def symbol(value):
    if (
        not isinstance(value, str)
        or len(value) > 32
        or not value.isascii()
        or not value.replace(".", "").replace("-", "").isalnum()
    ):
        raise BrokerError("BROKER_UNSUPPORTED_SYMBOL")
    return value


class AlpacaControls:
    def __init__(self, settings, *, transport=None):
        if (
            not settings.alpaca_api_key.get_secret_value()
            or not settings.alpaca_secret_key.get_secret_value()
        ):
            raise BrokerError("BROKER_NOT_CONFIGURED")
        self.settings, self.transport = settings, transport

    def client(self):
        return httpx.Client(
            timeout=15,
            verify=True,
            trust_env=True,
            follow_redirects=False,
            transport=self.transport,
            headers={
                "APCA-API-KEY-ID": self.settings.alpaca_api_key.get_secret_value(),
                "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key.get_secret_value(),
            },
        )

    def get(self, client, url, params=None):
        try:
            with client.stream("GET", url, params=params) as r:
                if r.status_code != 200:
                    raise BrokerError("BROKER_READ_REJECTED")
                raw = bytearray()
                for chunk in r.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 4 * 1024 * 1024:
                        raise BrokerError("BROKER_RESPONSE_TOO_LARGE")
            return json.loads(raw)
        except (httpx.HTTPError, ValueError, RecursionError):
            raise BrokerError("BROKER_READ_UNAVAILABLE") from None

    def account(self):
        try:
            with self.client() as client:
                account = self.get(client, ROOT + "/v2/account")
                positions = self.get(client, ROOT + "/v2/positions")
                orders = self.get(
                    client,
                    ROOT + "/v2/orders",
                    {"status": "open", "limit": 500, "nested": "true", "direction": "asc"},
                )
                configuration = self.get(client, ROOT + "/v2/account/configurations")
                # All activity types: a changed set invalidates reviewed loss reconciliation.
                activity_day = datetime.now(ZoneInfo("America/New_York")).date()
                activity_start = datetime.combine(
                    activity_day, time.min, ZoneInfo("America/New_York")
                ).astimezone(UTC)
                activities = self.get(
                    client,
                    ROOT + "/v2/account/activities",
                    {"page_size": 100, "direction": "desc", "after": activity_start.isoformat()},
                )
                activity_observed_at = datetime.now(UTC)
                confirm = self.get(client, ROOT + "/v2/positions")
            if (
                not isinstance(account, dict)
                or not isinstance(configuration, dict)
                or not all(isinstance(x, list) for x in (positions, orders, activities, confirm))
            ):
                raise BrokerError("BROKER_INVALID_RESPONSE")
            if len(positions) > 500 or len(orders) > 500 or len(activities) > 100:
                raise BrokerError("BROKER_CAPTURE_LIMIT")

            def identity(rows):
                return sorted(
                    (x["symbol"], x["asset_id"], x["qty"], x["qty_available"], x["side"])
                    for x in rows
                )

            coherent = identity(positions) == identity(confirm)
            normal = []
            unsupported = False
            for p in confirm:
                if p["side"] != "long" or p["asset_class"] != "us_equity":
                    unsupported = True
                    continue
                qty = amount(p["qty"])
                available = amount(p["qty_available"])
                if Decimal(available) > Decimal(qty):
                    raise BrokerError("BROKER_INVALID_POSITION")
                normal.append(
                    {
                        "symbol": symbol(p["symbol"]),
                        "asset_id": str(p["asset_id"]),
                        "quantity": qty,
                        "available_quantity": available,
                        "market_value": amount(p["market_value"]),
                    }
                )
            if len({p["symbol"] for p in normal}) != len(normal):
                raise BrokerError("BROKER_DUPLICATE_POSITION")

            # Keep only order fields needed for capacity/protective-stop reconciliation.
            def order(o):
                if o["side"] not in ("buy", "sell"):
                    raise BrokerError("BROKER_UNSUPPORTED_ORDER")
                quantity = Decimal(amount(o["qty"])) - Decimal(amount(o.get("filled_qty", "0")))
                if quantity < 0:
                    raise BrokerError("BROKER_INVALID_ORDER")
                return {
                    "id": str(o["id"]),
                    "symbol": symbol(o["symbol"]),
                    "asset_class": o.get("asset_class", "unknown"),
                    "side": o["side"].upper(),
                    "quantity": str(quantity),
                    "type": o["type"],
                    "status": o["status"],
                    "limit_price": amount(o["limit_price"], positive=True)
                    if o.get("limit_price")
                    else None,
                    "stop_price": amount(o["stop_price"], positive=True)
                    if o.get("stop_price")
                    else None,
                    "legs": [order(x) for x in o.get("legs") or []],
                }

            normal_orders = [order(o) for o in orders]
            if len({o["id"] for o in normal_orders}) != len(normal_orders):
                raise BrokerError("BROKER_DUPLICATE_ORDER")
            activity_ids = [str(a["id"]) for a in activities]
            if len(set(activity_ids)) != len(activity_ids):
                raise BrokerError("BROKER_DUPLICATE_ACTIVITY")
            return {
                "provider": "alpaca_paper",
                "account_id": str(account["id"]),
                "observed_at": datetime.now(UTC).isoformat(),
                "equity": amount(account["equity"], signed=True),
                "reported_cash": amount(account["cash"], signed=True),
                "broker_connected": account["status"] == "ACTIVE"
                and not bool(account.get("account_blocked", True))
                and not bool(account.get("trading_blocked", True)),
                "positions": normal,
                "orders": normal_orders,
                "positions_complete": coherent,
                "unsupported_positions_present": unsupported,
                "orders_complete": len(orders) < 500,
                "activity_complete": len(activities) < 100,
                "activity_trading_day": activity_day.isoformat(),
                "activity_coverage_start": activity_start.isoformat(),
                "activity_observed_at": activity_observed_at.isoformat(),
                "activity_sha256": digest(sorted(activities, key=lambda x: str(x["id"]))),
                "cash_account_verified": False,
                "settled_cash_verified": False,
                "settled_cash": None,
                "lending_disabled_verified": False,
                "borrowing_disabled_verified": False,
                "raw_response_sha256": digest(
                    {
                        "account": account,
                        "positions": positions,
                        "orders": orders,
                        "configuration": configuration,
                        "activities": activities,
                        "confirm": confirm,
                    }
                ),
                "limitations": [
                    "Reported cash/buying power is not verified settled cash",
                    "No explicit cash-account/lending/custody contract attested",
                    "Repeated position fields matched, not an atomic broker snapshot",
                    "Activity window capped at100; a full page is incomplete",
                ],
            }
        except (KeyError, TypeError, RecursionError, ValueError):
            raise BrokerError("BROKER_INVALID_RESPONSE") from None

    def quote(self, ticker):
        ticker = symbol(ticker)
        try:
            with self.client() as client:
                raw = self.get(client, DATA + f"/v2/stocks/{ticker}/quotes/latest", {"feed": "iex"})
            if raw["symbol"] != ticker:
                raise BrokerError("BROKER_QUOTE_SCOPE_MISMATCH")
            q = raw["quote"]
            bid = amount(q["bp"], positive=True)
            ask = amount(q["ap"], positive=True)
            stamp = datetime.fromisoformat(q["t"])
            now = datetime.now(UTC)
            if stamp.tzinfo is None or stamp > now or Decimal(bid) > Decimal(ask):
                raise BrokerError("BROKER_INVALID_QUOTE")
            return {
                "provider": "alpaca_iex",
                "symbol": ticker,
                "bid": bid,
                "ask": ask,
                "observed_at": stamp.isoformat(),
                "received_at": now.isoformat(),
                "raw_response_sha256": digest(raw),
                "venue": "IEX_ONLY_NOT_CONSOLIDATED",
            }
        except (KeyError, TypeError, ValueError):
            raise BrokerError("BROKER_INVALID_QUOTE") from None
