from datetime import UTC, datetime

import httpx
import pytest

from packages.config.settings import Settings
from services.controls.broker import BrokerError
from services.paper import provider


def reader(monkeypatch, *, opened=True, clock_age=0, bad=None):
    now = datetime(2026, 11, 27, 17, 0, tzinfo=UTC)
    monkeypatch.setattr(provider, "utcnow", lambda: now)
    calls = []

    def handle(request):
        calls.append((request.method, request.url.host, request.url.path))
        if bad == "rate":
            return httpx.Response(429, json={"message": "do not log raw provider details"})
        if request.url.path == "/v2/clock":
            from datetime import timedelta

            return httpx.Response(
                200,
                json={
                    "timestamp": (now - timedelta(seconds=clock_age)).isoformat(),
                    "is_open": opened,
                },
            )
        if request.url.path == "/v2/calendar":
            return httpx.Response(
                200,
                json=[
                    {"date": d, "open": "09:30", "close": "13:00" if d == "2026-11-27" else "16:00"}
                    for d in ["2026-11-27", "2026-11-30", "2026-12-01", "2026-12-02"]
                ],
            )
        if request.url.path == "/v2/stocks/quotes/latest":
            quote = {"bp": 99, "ap": 100, "bs": 7, "as": 4, "t": now.isoformat()}
            if bad == "crossed":
                quote["bp"] = 101
            if bad == "missing":
                return httpx.Response(200, json={"quotes": {}})
            return httpx.Response(200, json={"quotes": {"AAPL": quote}})
        raise AssertionError("Unexpected endpoint")

    settings = Settings(
        alpaca_api_key="fictional-key", alpaca_secret_key="fictional-secret", _env_file=None
    )
    return provider.AlpacaPaperData(settings, transport=httpx.MockTransport(handle)), calls


def test_get_only_reader_binds_early_close_dst_and_holiday_settlement(monkeypatch):
    source, calls = reader(monkeypatch)
    snapshot = source.snapshot(["AAPL"])
    q = snapshot.quotes["AAPL"]
    assert q.session_open.isoformat() == "2026-11-27T14:30:00+00:00"
    assert q.session_close.isoformat() == "2026-11-27T18:00:00+00:00"
    assert q.settlement_at.isoformat() == "2026-11-30T14:30:00+00:00"
    assert q.ask_size == 4 and q.bid_size == 7
    assert all(method == "GET" for method, _, _ in calls)
    assert {host for _, host, _ in calls} == {"paper-api.alpaca.markets", "data.alpaca.markets"}


def test_rate_limit_is_sanitized(monkeypatch):
    source, _ = reader(monkeypatch, bad="rate")
    with pytest.raises(BrokerError) as result:
        source.snapshot(["AAPL"])
    assert "fictional-secret" not in str(result.value)
    assert "raw provider" not in str(result.value)


@pytest.mark.parametrize("bad", ["crossed", "missing"])
def test_bad_symbol_data_is_reported_missing_and_never_becomes_a_quote(monkeypatch, bad):
    source, _ = reader(monkeypatch, bad=bad)
    result = source.snapshot(["AAPL"])
    assert not result.quotes and result.missing_symbols == ("AAPL",)


def test_stale_provider_clock_is_rejected(monkeypatch):
    source, _ = reader(monkeypatch, clock_age=60)
    with pytest.raises(BrokerError, match="SNAPSHOT_INVALID"):
        source.snapshot(["AAPL"])


def test_closed_market_does_not_fetch_quotes(monkeypatch):
    source, calls = reader(monkeypatch, opened=False)
    # Clock/calendar disagreement during an actual open session is rejected.
    with pytest.raises(BrokerError):
        source.snapshot(["AAPL"])
    assert not any(path.startswith("/v2/stocks/") for _, _, path in calls)
