from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.db import Base, DataImport, EconomicRecord, NewsRecord
from services.macro_intelligence.bls import BlsError, fetch_calendar, parse_calendar
from services.market_data.acquire_news import persist_poll
from services.market_data.event_store import latest_events
from services.news_intelligence.providers.finnhub import FinnhubError, FinnhubNews

NOW = datetime(2026, 10, 28, tzinfo=UTC)
ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:cpi-release
DTSTAMP:20261001T120000Z
DTSTART;TZID=US-Eastern:20261110T083000
SUMMARY:Consumer Price Index
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
"""


def news(**changes):
    return {
        "id": 123,
        "datetime": int((NOW - timedelta(hours=1)).timestamp()),
        "source": "Fixture publisher",
        "url": "https://example.org/news",
        "headline": "Company reports growth",
        "summary": "Revenue increased in the quarter",
    } | changes


def fetch_news(handler):
    return FinnhubNews(SecretStr("fixture-token"), transport=httpx.MockTransport(handler)).fetch(
        "EXAMPLE", "stock", date(2026, 10, 27), date(2026, 10, 28), now=NOW
    )


def test_news_fixed_endpoint_header_and_no_privileged_fields():
    def handler(request):
        assert str(request.url).startswith("https://finnhub.io/api/v1/company-news?")
        assert request.headers["X-Finnhub-Token"] == "fixture-token"
        assert "fixture-token" not in str(request.url)
        assert request.url.params["symbol"] == "EXAMPLE"
        return httpx.Response(200, json=[news() | {"authorized": True}])

    event = fetch_news(handler)[0]
    assert event.provider == "finnhub" and event.symbols == ["EXAMPLE"]
    assert "authorized" not in event.model_dump()


@pytest.mark.parametrize(
    "body",
    [
        {"error": "quota"},
        [news(datetime=True)],
        [news(url="http://example.org")],
        [news(), news()],
        [news(datetime=int((NOW + timedelta(days=1)).timestamp()))],
    ],
)
def test_bad_news_fails_whole_poll(body):
    with pytest.raises(FinnhubError):
        fetch_news(lambda request: httpx.Response(200, json=body))


def test_news_no_redirect_or_transient_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://attacker.invalid"})

    with pytest.raises(FinnhubError):
        fetch_news(handler)
    assert len(calls) == 1


def test_bls_timezone_and_cancellation():
    event = parse_calendar(ICS, received_at=NOW)[0]
    assert event.scheduled_at.isoformat() == "2026-11-10T13:30:00+00:00"
    assert event.event_type == "cpi" and event.severity == "high"
    assert event.asset_classes == ["stock", "etf", "gold"]
    cancelled = parse_calendar(ICS.replace(b"CONFIRMED", b"CANCELLED"), received_at=NOW)[0]
    assert cancelled.cancelled
    raw, events = fetch_calendar(
        received_at=NOW,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=ICS)),
    )
    assert raw == ICS and events == [event]


@pytest.mark.parametrize(
    "raw",
    [
        ICS.replace(b"TZID=US-Eastern", b"TZID=Unknown/Zone"),
        ICS.replace(b"20261110T083000", b"20261101T013000"),
        ICS.replace(b"20261110T083000", b"20260308T023000"),
        ICS.replace(b";TZID=US-Eastern", b""),
        ICS.replace(b"DTSTAMP:20261001T120000Z", b"DTSTAMP:20271001T120000Z"),
        ICS.replace(b"STATUS:CONFIRMED", b"RRULE:FREQ=MONTHLY"),
        ICS.replace(b"STATUS:CONFIRMED", b"RECURRENCE-ID:20261110T133000Z"),
        ICS.replace(b"END:VEVENT", b""),
        ICS.replace(b"STATUS:CONFIRMED", b"SUMMARY:duplicate"),
        b"BEGIN:VCALENDAR\nEND:VCALENDAR\n",
    ],
)
def test_unsupported_or_ambiguous_calendar_fails(raw):
    with pytest.raises(BlsError):
        parse_calendar(raw, received_at=NOW)


def test_local_revisions_and_atomic_batches_preserve_receipt_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'providers.db'}")
    Base.metadata.create_all(engine)
    try:
        events = fetch_news(lambda request: httpx.Response(200, json=[news()]))
        persist_poll(engine, events, NOW, "first")
        persist_poll(engine, events, NOW + timedelta(minutes=1), "unchanged")
        changed = [events[0].model_copy(update={"headline": "Corrected company growth report"})]
        persist_poll(engine, changed, NOW + timedelta(minutes=2), "correction")
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(NewsRecord)) == 2
            assert latest_events(session, "news", NOW)[0].revision == 1
            assert latest_events(session, "news", NOW + timedelta(minutes=2))[0].revision == 2
        calendar = parse_calendar(ICS, received_at=NOW)
        persist_poll(engine, calendar, NOW, "calendar", provider="bls", kind="calendar")
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(EconomicRecord)) == 1
            before = session.scalar(select(func.count()).select_from(DataImport))
        bad = [events[0].model_copy(update={"item_id": f"new-{i}"}) for i in range(100)] + [
            changed[0].model_copy(
                update={"item_id": "future", "published_at": NOW + timedelta(days=1)}
            )
        ]
        # A failure in any chunk must roll back the entire poll and its health records.
        with pytest.raises(ValueError):
            persist_poll(engine, bad, NOW, "bad")
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(DataImport)) == before
    finally:
        engine.dispose()
