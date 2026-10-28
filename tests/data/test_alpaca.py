import json
from datetime import UTC, date, datetime

import httpx
import pytest
from pydantic import SecretStr

from services.market_data.csv_data import load_csv
from services.market_data.providers.alpaca import AlpacaDaily, AlpacaError, save_snapshot
from services.market_data.sessions import Schedule, audit_sessions

NOW = datetime(2026, 10, 28, tzinfo=UTC)
CALENDAR = [
    {"date": "2024-11-27", "open": "09:30", "close": "16:00"},
    {"date": "2024-11-29", "open": "09:30", "close": "13:00"},
    {"date": "2024-12-02", "open": "09:30", "close": "16:00"},
]
BARS = [
    {"t": day + "T05:00:00Z", "o": 100, "h": 102, "l": 99, "c": 101, "v": 1000}
    for day in ("2024-11-27", "2024-11-29", "2024-12-02")
]


def fetch(handler, **changes):
    adapter = AlpacaDaily(
        SecretStr("fixture-key"),
        SecretStr("fixture-secret"),
        transport=httpx.MockTransport(handler),
    )
    return adapter.fetch(
        **(
            {
                "symbol": "EXAMPLE",
                "asset_class": "stock",
                "start": date(2024, 11, 27),
                "end": date(2024, 12, 2),
                "clock": lambda: NOW,
            }
            | changes
        )
    )


def test_pagination_session_close_mapping_and_snapshot(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["APCA-API-KEY-ID"] == "fixture-key"
        assert "fixture-key" not in str(request.url)
        assert "fixture-secret" not in str(request.url)
        if request.url.host == "paper-api.alpaca.markets":
            assert request.url.path == "/v2/calendar"
            return httpx.Response(200, json=CALENDAR)
        assert request.url.host == "data.alpaca.markets"
        assert request.url.params["adjustment"] == "split" and request.url.params["feed"] == "iex"
        if request.url.params.get("page_token") == "next":
            return httpx.Response(
                200, json={"symbol": "EXAMPLE", "bars": BARS[1:], "next_page_token": None}
            )
        return httpx.Response(
            200, json={"symbol": "EXAMPLE", "bars": BARS[:1], "next_page_token": "next"}
        )

    snapshot = fetch(handler)
    assert len(requests) == 3
    output = tmp_path / "snapshot"
    save_snapshot(output, snapshot)
    data = load_csv(output / "bars.csv", output / "metadata.json")
    assert [stamp.hour for stamp in data.bars.index] == [21, 18, 21]
    assert data.spec.volume_basis == "split_adjusted"
    assert audit_sessions(data, Schedule.model_validate(snapshot["schedule"]), NOW)["consistent"]
    assert not json.loads((output / "manifest.json").read_text())["consolidated_market_coverage"]
    with pytest.raises(FileExistsError):
        save_snapshot(output, snapshot)


@pytest.mark.parametrize(
    "case",
    [
        "redirect",
        "rate",
        "wrong_symbol",
        "repeat_page",
        "duplicate",
        "bad_bounds",
        "naive",
        "wrong_label",
        "bad_calendar",
    ],
)
def test_bad_upstream_fails_without_redirect_or_retry(case):
    calls = []

    def handler(request):
        calls.append(request)
        if case == "redirect":
            return httpx.Response(302, headers={"Location": "https://attacker.invalid/steal"})
        if case == "rate":
            return httpx.Response(429)
        if request.url.host == "paper-api.alpaca.markets":
            return httpx.Response(200, json={} if case == "bad_calendar" else CALENDAR)
        bars = [dict(bar) for bar in BARS]
        if case == "duplicate":
            bars.append(bars[-1])
        if case == "bad_bounds":
            bars[0]["c"] = -1
        if case == "naive":
            bars[0]["t"] = "2024-11-27T00:00:00"
        if case == "wrong_label":
            bars[0]["t"] = "2024-11-27T21:00:00Z"
        return httpx.Response(
            200,
            json={
                "symbol": "OTHER" if case == "wrong_symbol" else "EXAMPLE",
                "bars": bars,
                "next_page_token": "same" if case == "repeat_page" else None,
            },
        )

    with pytest.raises(AlpacaError):
        fetch(handler)
    if case in ("redirect", "rate"):
        assert len(calls) == 1


@pytest.mark.parametrize(
    "changes", [{"symbol": "../orders"}, {"asset_class": "gold"}, {"end": date(2027, 1, 1)}]
)
def test_invalid_request_never_calls_provider(changes):
    def handler(request):
        pytest.fail("Invalid input must not cause HTTP")

    with pytest.raises(ValueError):
        fetch(handler, **changes)
