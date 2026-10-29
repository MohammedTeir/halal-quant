"""Bounded BLS iCalendar acquisition with explicit timezone and revision semantics.

Only standalone events with explicit scheduled times are supported. Recurrence and
unknown timezones fail the whole poll instead of silently dropping restrictions.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from packages.schemas.data_events import EconomicEvent
from services.market_data.event_store import digest

URL = "https://www.bls.gov/schedule/news_release/bls.ics"
MAX_BYTES = 2 * 1024 * 1024


class BlsError(RuntimeError):
    pass


def _stamp(name, value):
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    parts = name.split(";")
    zones = [part[5:] for part in parts[1:] if part.startswith("TZID=")]
    if len(zones) != 1:
        raise ValueError("Calendar timestamps need UTC or an explicit timezone")
    zone = zones[0].strip('"')
    zone = {"US-Eastern": "America/New_York", "Eastern Standard Time": "America/New_York"}.get(
        zone, zone
    )
    naive = datetime.strptime(value, "%Y%m%dT%H%M%S")
    local = naive.replace(tzinfo=ZoneInfo(zone))
    if (
        local.utcoffset() != local.replace(fold=1).utcoffset()
        or local.astimezone(UTC).astimezone(local.tzinfo).replace(tzinfo=None) != naive
    ):
        raise ValueError("Ambiguous or nonexistent calendar time")
    return local.astimezone(UTC)


def _text(value):
    # RFC 5545 escapes, without interpreting source text as code/HTML.
    return (
        value.replace("\\n", " ")
        .replace("\\N", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def parse_calendar(raw: bytes, *, received_at: datetime):
    if len(raw) > MAX_BYTES or received_at.tzinfo is None:
        raise BlsError("BLS_INVALID_CALENDAR")
    try:
        text = raw.decode("utf-8-sig").replace("\r\n", "\n")
        unfolded = []
        for line in text.splitlines():
            if line.startswith((" ", "\t")):
                if not unfolded:
                    raise ValueError("Invalid folding")
                unfolded[-1] += line[1:]
            else:
                unfolded.append(line)
        if not unfolded or unfolded[0] != "BEGIN:VCALENDAR" or unfolded[-1] != "END:VCALENDAR":
            raise ValueError("Expected a complete calendar")
        events, active, seen = [], None, set()
        for line in unfolded:
            if line == "BEGIN:VEVENT":
                if active is not None:
                    raise ValueError("Nested event")
                active = {}
            elif line == "END:VEVENT":
                if active is None:
                    raise ValueError("Missing event")
                uid = active["UID"][1]
                if uid in seen:
                    raise ValueError("Duplicate UID or recurrence override")
                seen.add(uid)
                title = _text(active["SUMMARY"][1])
                lower = title.lower()
                event_type = (
                    "cpi"
                    if "consumer price index" in lower
                    else "employment"
                    if any(
                        term in lower
                        for term in ("employment situation", "job openings", "employment cost")
                    )
                    else "other"
                )
                source_stamp = active.get("LAST-MODIFIED") or active.get("DTSTAMP")
                published = _stamp(*source_stamp) if source_stamp else received_at
                if published > received_at:
                    raise ValueError("Future source stamp")
                events.append(
                    EconomicEvent(
                        provider="bls",
                        item_id=digest(uid),
                        published_at=published,
                        publication_basis="provider_timestamp" if source_stamp else "observed_at",
                        title=title,
                        event_type=event_type,
                        scheduled_at=_stamp(*active["DTSTART"]),
                        severity="high" if event_type in ("cpi", "employment") else "medium",
                        asset_classes=["stock", "etf", "gold"],
                        cancelled=active.get("STATUS", (None, ""))[1] == "CANCELLED",
                    )
                )
                active = None
            elif active is not None:
                name, value = line.split(":", 1)
                base = name.split(";", 1)[0]
                if base in ("RRULE", "RDATE", "EXDATE", "RECURRENCE-ID") or base.startswith(
                    "BEGIN"
                ):
                    raise ValueError("Unsupported recurrence or nested event")
                if base in active:
                    raise ValueError("Duplicate event property")
                active[base] = (name, value)
        if active is not None or not events or len(events) > 10000:
            raise ValueError("Incomplete or empty release schedule")
        return events
    except (ValueError, KeyError, UnicodeError, ZoneInfoNotFoundError):
        raise BlsError("BLS_INVALID_CALENDAR") from None


def fetch_calendar(*, received_at: datetime | None = None, transport=None):
    try:
        with (
            httpx.Client(
                timeout=20, verify=True, trust_env=True, follow_redirects=False, transport=transport
            ) as client,
            client.stream("GET", URL) as response,
        ):
            if response.status_code != 200:
                raise BlsError("BLS_REQUEST_REJECTED")
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_BYTES:
                    raise BlsError("BLS_RESPONSE_TOO_LARGE")
    except httpx.HTTPError:
        raise BlsError("BLS_UNAVAILABLE") from None
    return bytes(raw), parse_calendar(bytes(raw), received_at=received_at or datetime.now(UTC))
