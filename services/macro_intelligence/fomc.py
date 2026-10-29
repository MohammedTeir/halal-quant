"""Official FOMC meeting calendar; observed publication, conservative date-only timing."""

import calendar
import re
from datetime import UTC, date, datetime, time
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import httpx

from packages.schemas.data_events import EconomicEvent, FeedCoverage
from services.market_data.event_store import digest

URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
MAX_BYTES = 2 * 1024 * 1024


class FomcError(RuntimeError):
    pass


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.heading = False
        self.heading_text = []
        self.year = None
        self.month = None
        self.capture = None
        self.depth = 0
        self.parts = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "h4":
            self.heading = True
            self.heading_text = []
        if tag == "div":
            if self.capture:
                self.depth += 1
            else:
                classes = values.get("class", "").split()
                if "fomc-meeting__month" in classes:
                    self.capture = "month"
                elif "fomc-meeting__date" in classes:
                    self.capture = "date"
                if self.capture:
                    self.parts = []
                    self.depth = 1

    def handle_data(self, data):
        if self.heading:
            self.heading_text.append(data)
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "h4" and self.heading:
            match = re.fullmatch(r"\s*(\d{4}) FOMC Meetings\s*", "".join(self.heading_text))
            self.year = int(match[1]) if match else None
            self.heading = False
            self.month = None
        if tag == "div" and self.capture:
            self.depth -= 1
            if not self.depth:
                text = " ".join("".join(self.parts).split())
                if self.capture == "month":
                    self.month = text
                else:
                    self.rows.append((self.year, self.month, text))
                self.capture = None


def parse_calendar(raw, year, observed_at):
    if len(raw) > MAX_BYTES or observed_at.tzinfo is None or not 2000 <= year <= 2100:
        raise FomcError("FOMC_INVALID_CALENDAR")
    try:
        parser = CalendarParser()
        parser.feed(raw.decode("utf-8"))
        months = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
        months.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
        events = []
        seen = set()
        for y, month, days in parser.rows:
            if y != year:
                continue
            match = re.fullmatch(r"(\d{1,2})(?:-(\d{1,2}))?\*?(?: \([^)]*\))?", days)
            if not match or month is None:
                raise ValueError("Unsupported meeting date")
            # Cross-month meetings are named Jan/Feb or Apr/May; use the final date.
            month_number = months[month.split("/")[-1].lower()]
            day = date(year, month_number, int(match[2] or match[1]))
            if day in seen:
                raise ValueError("Duplicate meeting date")
            seen.add(day)
            events.append(
                EconomicEvent(
                    provider="federal_reserve",
                    item_id=digest(["FOMC", day.isoformat()]),
                    published_at=observed_at,
                    publication_basis="observed_at",
                    title=f"FOMC calendar event ending {day.isoformat()}",
                    event_type="fed",
                    severity="high",
                    scheduled_at=datetime.combine(day, time.min, ZoneInfo("America/New_York")),
                    scheduled_precision="date",
                    scheduled_timezone="America/New_York",
                    asset_classes=["stock", "etf", "gold"],
                )
            )
        if not 1 <= len(events) <= 32:
            raise ValueError("Missing or excessive meeting rows")
        return sorted(events, key=lambda event: event.scheduled_at)
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise FomcError("FOMC_INVALID_CALENDAR") from None


def fetch_calendar(year, *, transport=None):
    if not 2000 <= year <= 2100:
        raise ValueError("Calendar year must be 2000..2100")
    try:
        with (
            httpx.Client(
                timeout=25, verify=True, trust_env=True, follow_redirects=False, transport=transport
            ) as client,
            client.stream("GET", URL) as response,
        ):
            if response.status_code != 200:
                raise FomcError("FOMC_REQUEST_REJECTED")
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_BYTES:
                    raise FomcError("FOMC_RESPONSE_TOO_LARGE")
        observed = datetime.now(UTC)
        return bytes(raw), parse_calendar(bytes(raw), year, observed), observed
    except httpx.HTTPError:
        raise FomcError("FOMC_UNAVAILABLE") from None


def coverage_window(year):
    return FeedCoverage(
        symbols=[],
        asset_classes=["stock", "etf", "gold"],
        purpose="macro_releases",
        starts_at=datetime(year, 1, 1, tzinfo=ZoneInfo("America/New_York")),
        ends_at=datetime(year + 1, 1, 1, tzinfo=ZoneInfo("America/New_York")),
    )
