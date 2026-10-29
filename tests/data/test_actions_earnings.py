from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from packages.schemas.data_events import EconomicEvent
from services.decision_engine.policies import DecisionPolicy, calendar_restrictions
from services.macro_intelligence.earnings import FinnhubEarnings
from services.market_data.providers.actions import AlpacaActions, normalize_actions
from services.market_data.providers.alpaca import AlpacaError
from services.news_intelligence.providers.finnhub import FinnhubError

NOW = datetime(2026, 10, 29, tzinfo=UTC)
START, END = date(2020, 8, 1), date(2020, 9, 1)


def action_page():
    return {
        "corporate_actions": {
            "forward_splits": [
                {
                    "id": "split-1",
                    "symbol": "AAPL",
                    "ex_date": "2020-08-31",
                    "new_rate": 4,
                    "old_rate": 1,
                }
            ]
        },
        "next_page_token": None,
    }


def test_action_fixed_endpoint_and_ratio():
    def handler(request):
        assert request.url.host == "data.alpaca.markets"
        assert request.url.path == "/v1/corporate-actions"
        assert request.headers["APCA-API-SECRET-KEY"] == "fixture-secret"
        assert "fixture-secret" not in str(request.url)
        return httpx.Response(200, json=action_page())

    _pages, records, now = AlpacaActions(
        SecretStr("fixture-key"),
        SecretStr("fixture-secret"),
        transport=httpx.MockTransport(handler),
    ).acquire("AAPL", START, END, clock=lambda: NOW)
    assert records[0].split_ratio == Decimal(4)
    assert records[0].effective_at.isoformat() == "2020-08-31T04:00:00+00:00"
    assert records[0].publication_basis == "observed_at" and now == NOW


@pytest.mark.parametrize(
    "case", ["zero_ratio", "negative_rates", "foreign", "wrong_scope", "unsupported", "duplicate"]
)
def test_bad_actions_rejected(case):
    page = action_page()
    item = page["corporate_actions"]["forward_splits"][0]
    if case == "zero_ratio":
        item["old_rate"] = 0
    if case == "negative_rates":
        item["new_rate"], item["old_rate"] = -4, -1
    if case == "foreign":
        item["foreign"] = True
    if case == "wrong_scope":
        item["symbol"] = "OTHER"
    if case == "unsupported":
        page["corporate_actions"]["mergers"] = [{"id": "unsupported"}]
    if case == "duplicate":
        page["corporate_actions"]["forward_splits"].append(item)
    with pytest.raises(AlpacaError):
        normalize_actions([page], "AAPL", START, END, NOW)


def earnings_row(**changes):
    return {
        "symbol": "AAPL",
        "date": "2026-11-02",
        "hour": "amc",
        "quarter": 4,
        "year": 2026,
    } | changes


def earnings(rows):
    def handler(request):
        assert request.url.path == "/api/v1/calendar/earnings"
        assert request.headers["X-Finnhub-Token"] == "fixture-token"
        assert "fixture-token" not in str(request.url)
        return httpx.Response(200, json={"earningsCalendar": rows})

    return FinnhubEarnings(
        SecretStr("fixture-token"), transport=httpx.MockTransport(handler)
    ).fetch("AAPL", date(2026, 10, 1), date(2026, 11, 30), clock=lambda: NOW)


def test_earnings_date_only_restrictions_cover_whole_day_and_corrections_keep_identity():
    _, rows, _ = earnings([earnings_row()])
    event = rows[0]
    assert event.publication_basis == "observed_at" and event.scheduled_precision == "date"
    _, corrected, _ = earnings([earnings_row(date="2026-11-03")])
    assert corrected[0].item_id == event.item_id
    fact = event.model_dump(mode="json") | {"source_id": "a" * 64}
    for stamp in (
        "2026-11-02T00:30:00-05:00",
        "2026-11-02T23:59:00-05:00",
        "2026-11-03T23:59:00-05:00",
    ):
        assert calendar_restrictions(
            [fact], "AAPL", "stock", datetime.fromisoformat(stamp), DecisionPolicy()
        )
    assert not calendar_restrictions(
        [fact],
        "AAPL",
        "stock",
        datetime.fromisoformat("2026-11-04T00:01:00-05:00"),
        DecisionPolicy(),
    )
    with pytest.raises(ValueError):
        EconomicEvent.model_validate(event.model_dump() | {"scheduled_timezone": None})


@pytest.mark.parametrize(
    "rows",
    [
        [earnings_row(symbol="OTHER")],
        [earnings_row(quarter=0)],
        [earnings_row(), earnings_row()],
        [earnings_row(date="2027-01-01")],
    ],
)
def test_bad_earnings_fail_whole_poll(rows):
    with pytest.raises(FinnhubError):
        earnings(rows)
