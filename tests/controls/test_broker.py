from datetime import UTC, datetime

import httpx
import pytest

from packages.config.settings import Settings
from services.controls.broker import AlpacaControls, BrokerError


def adapter(handler):
    return AlpacaControls(
        Settings(alpaca_api_key="fixture-key", alpaca_secret_key="fixture-secret", _env_file=None),
        transport=httpx.MockTransport(handler),
    )


def account():
    return {
        "id": "acct-fixture",
        "account_number": "PRIVATE_NOT_TO_STORE",
        "status": "ACTIVE",
        "account_blocked": False,
        "trading_blocked": False,
        "equity": "10000",
        "cash": "10000",
        "buying_power": "40000",
        "multiplier": "1",
    }


def position():
    return {
        "symbol": "AAPL",
        "asset_id": "asset-a",
        "side": "long",
        "asset_class": "us_equity",
        "qty": "10",
        "qty_available": "8",
        "market_value": "1000",
    }


def responses(request, positions=None, orders=None):
    assert request.method == "GET" and request.url.host == "paper-api.alpaca.markets"
    values = {
        "/v2/account": account(),
        "/v2/account/configurations": {"no_shorting": True},
        "/v2/positions": positions or [],
        "/v2/orders": orders or [],
        "/v2/account/activities": [],
    }
    return httpx.Response(200, json=values[request.url.path])


def test_fixed_read_only_capture_never_infers_cash_contract_or_stores_account_number():
    calls = []

    def handle(request):
        calls.append(request)
        return responses(request, [position()])

    facts = adapter(handle).account()
    assert len(calls) == 6 and facts["positions_complete"]
    assert not facts["cash_account_verified"] and not facts["settled_cash_verified"]
    assert facts["settled_cash"] is None and not facts["lending_disabled_verified"]
    assert "PRIVATE_NOT_TO_STORE" not in str(facts)
    assert facts["positions"][0]["available_quantity"] == "8"
    assert len(facts["raw_response_sha256"]) == 64


def test_negative_cash_does_not_discard_owned_long_exit_observations():
    def handle(request):
        if request.url.path == "/v2/account":
            return httpx.Response(200, json=account() | {"cash": "-1"})
        return responses(request, [position()])

    facts = adapter(handle).account()
    assert facts["reported_cash"] == "-1" and facts["positions"][0]["quantity"] == "10"


def test_changed_position_quantity_is_incomplete_not_silently_atomic():
    calls = []

    def handle(request):
        if request.url.path == "/v2/positions":
            calls.append(1)
            row = position()
            row["qty"] = "11" if len(calls) == 2 else "10"
            return httpx.Response(200, json=[row])
        return responses(request)

    assert not adapter(handle).account()["positions_complete"]


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_rejections_never_follow_redirect_or_expose_bodies(status):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status, text="SECRET_RESPONSE_DETAIL", headers={"Location": "https://other.invalid"}
        )

    with pytest.raises(BrokerError) as error:
        adapter(handle).account()
    assert str(error.value) == "BROKER_READ_REJECTED" and len(calls) == 1


def test_quote_is_iex_bound_and_never_accepts_caller_url_or_future_quote():
    def handle(request):
        assert request.method == "GET" and request.url.host == "data.alpaca.markets"
        assert request.url.params["feed"] == "iex"
        return httpx.Response(
            200,
            json={
                "symbol": "AAPL",
                "quote": {"bp": 99, "ap": 100, "t": datetime.now(UTC).isoformat()},
            },
        )

    client = adapter(handle)
    quote = client.quote("AAPL")
    assert (
        quote["bid"] == "99"
        and quote["ask"] == "100"
        and quote["venue"] == "IEX_ONLY_NOT_CONSOLIDATED"
    )
    with pytest.raises(BrokerError):
        client.quote("../v2/orders")


def test_full_orders_or_activity_page_is_incomplete():
    def handle(request):
        if request.url.path == "/v2/account/activities":
            return httpx.Response(200, json=[{"id": str(i)} for i in range(100)])
        return responses(request)

    assert not adapter(handle).account()["activity_complete"]


def test_short_position_does_not_become_owned_long_evidence():
    row = position() | {"side": "short", "qty": "-10", "qty_available": "-10"}
    facts = adapter(lambda request: responses(request, [row])).account()
    assert facts["positions"] == [] and facts["unsupported_positions_present"]


def test_local_capture_cli_does_not_dump_private_database_error_details(
    tmp_path, monkeypatch, capsys
):
    import sys

    from sqlalchemy.exc import SQLAlchemyError

    from services.controls import acquire_broker

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "acquire",
            "--kind",
            "account",
            "--refresh-id",
            "safe-failure",
            "--report-output",
            str(tmp_path / "report.json"),
        ],
    )
    monkeypatch.setattr(acquire_broker, "get_settings", lambda: Settings(_env_file=None))

    def fail(url):
        raise SQLAlchemyError("PRIVATE_BALANCE_AND_DATABASE_DETAILS")

    monkeypatch.setattr(acquire_broker, "session_factory", fail)
    with pytest.raises(SystemExit) as error:
        acquire_broker.main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "PRIVATE_BALANCE_AND_DATABASE_DETAILS" not in output.err + output.out
    assert not (tmp_path / "report.json").exists()
