"""Fixed-host, GET-only IEX quote/calendar reader for internal forward simulation."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from apps.api.db import utcnow
from packages.schemas.controls import Contract
from services.controls.broker import DATA, ROOT, AlpacaControls, BrokerError, symbol
from services.market_data.event_store import digest
from services.paper.schemas import QuoteRequest

NY = ZoneInfo("America/New_York")


class MarketSession(Contract):
    date: date
    opens: AwareDatetime
    closes: AwareDatetime

    @model_validator(mode="after")
    def ordered(self):
        if (
            self.opens >= self.closes
            or self.opens.astimezone(NY).date() != self.date
            or self.closes.astimezone(NY).date() != self.date
        ):
            raise ValueError("Invalid regular session")
        return self


class MarketBundle(Contract):
    observed_at: AwareDatetime
    received_at: AwareDatetime
    market_open: StrictBool
    sessions: tuple[MarketSession, ...] = Field(min_length=1, max_length=40)
    missing_symbols: tuple[str, ...] = Field(default=(), max_length=10)
    quotes: dict[str, QuoteRequest] = Field(default_factory=dict, max_length=10)
    receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def coherent(self):
        if abs((self.received_at - self.observed_at).total_seconds()) > 15:
            raise ValueError("Provider clock is stale or ahead")
        if len({s.date for s in self.sessions}) != len(self.sessions):
            raise ValueError("Duplicate calendar session")
        if len(set(self.missing_symbols)) != len(self.missing_symbols) or set(
            self.missing_symbols
        ) & set(self.quotes):
            raise ValueError("Quote availability sets overlap")
        opened = [s for s in self.sessions if s.opens <= self.observed_at < s.closes]
        if bool(opened) != self.market_open:
            raise ValueError("Provider clock/calendar disagree")
        for ticker, q in self.quotes.items():
            if (
                ticker != q.symbol
                or q.source != "alpaca_iex"
                or q.receipt_sha256 != self.receipt_sha256
            ):
                raise ValueError("Quote receipt/scope mismatch")
            if not self.received_at - timedelta(seconds=15) <= q.observed_at <= self.received_at:
                raise ValueError("Provider quote unavailable or stale")
            if (
                not opened
                or not opened[0].opens <= q.observed_at < opened[0].closes
                or q.session_open != opened[0].opens
                or q.session_close != opened[0].closes
                or q.settlement_at is None
                or q.settlement_at <= opened[0].closes
            ):
                raise ValueError("Quote calendar binding missing")
        return self


class AlpacaPaperData(AlpacaControls):
    """Only inherited GET transport is used. No submit/cancel broker methods exist."""

    def snapshot(self, tickers, settlement_days=1):
        if not 1 <= len(tickers) <= 10:
            raise BrokerError("PAPER_UNIVERSE_MUST_HAVE_1_TO_10_SYMBOLS")
        tickers = [symbol(s) for s in sorted(tickers)]
        try:
            with self.client() as client:
                clock = self.get(client, ROOT + "/v2/clock")
                observed = datetime.fromisoformat(clock["timestamp"])
                if observed.tzinfo is None or type(clock["is_open"]) is not bool:
                    raise ValueError
                today = observed.astimezone(NY).date()
                calendar = self.get(
                    client,
                    ROOT + "/v2/calendar",
                    {
                        "start": (today - timedelta(days=2)).isoformat(),
                        "end": (today + timedelta(days=14)).isoformat(),
                    },
                )
                sessions = tuple(
                    MarketSession(
                        date=date.fromisoformat(row["date"]),
                        opens=datetime.fromisoformat(row["date"] + "T" + row["open"])
                        .replace(tzinfo=NY)
                        .astimezone(UTC),
                        closes=datetime.fromisoformat(row["date"] + "T" + row["close"])
                        .replace(tzinfo=NY)
                        .astimezone(UTC),
                    )
                    for row in calendar
                )
                raw = (
                    self.get(
                        client,
                        DATA + "/v2/stocks/quotes/latest",
                        {"symbols": ",".join(tickers), "feed": "iex"},
                    )
                    if clock["is_open"]
                    else {"quotes": {}}
                )
            now = utcnow()
            receipt = digest({"clock": clock, "calendar": calendar, "quotes": raw})
            current = next((s for s in sessions if s.opens <= observed < s.closes), None)
            next_days = sorted((s for s in sessions if s.date > today), key=lambda s: s.date)
            normalized = {}
            missing = set()
            if clock["is_open"]:
                if (
                    not current
                    or len(next_days) < settlement_days
                    or set(raw["quotes"]) - set(tickers)
                ):
                    raise ValueError
                for ticker in tickers:
                    try:
                        q = raw["quotes"][ticker]
                        # Conservatively interpret displayed sizes as shares, never inflate lots.
                        sizes = [Decimal(str(q[k])) for k in ("bs", "as")]
                        if any(
                            not n.is_finite() or n != n.to_integral_value() or not 1 <= n <= 1000000
                            for n in sizes
                        ):
                            raise ValueError
                        normalized[ticker] = QuoteRequest(
                            command_id="provider:" + receipt[:24] + ":" + ticker,
                            symbol=ticker,
                            source="alpaca_iex",
                            observed_at=q["t"],
                            bid=q["bp"],
                            ask=q["ap"],
                            bid_size=int(sizes[0]),
                            ask_size=int(sizes[1]),
                            receipt_sha256=receipt,
                            session_open=current.opens,
                            session_close=current.closes,
                            settlement_at=next_days[settlement_days - 1].opens,
                        )
                        if (
                            not now - timedelta(seconds=15) <= normalized[ticker].observed_at <= now
                            or not current.opens <= normalized[ticker].observed_at < current.closes
                        ):
                            raise ValueError("No fresh regular-session quote")
                    except (ValueError, KeyError, TypeError, ArithmeticError):
                        normalized.pop(ticker, None)
                        missing.add(ticker)
            return MarketBundle(
                observed_at=observed,
                received_at=now,
                market_open=clock["is_open"],
                sessions=sessions,
                quotes=normalized,
                missing_symbols=tuple(sorted(missing)),
                receipt_sha256=receipt,
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise BrokerError("PAPER_MARKET_SNAPSHOT_INVALID") from None
