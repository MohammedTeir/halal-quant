from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import sessionmaker

from services.accounts.access import password_hash
from services.notifications.models import User


@pytest.fixture
def api_overrides():
    return {"paper_trading_enabled": True, "session_cookie_secure": False}


def sign_in(client, role="operator"):
    with sessionmaker(client.app.state.engine).begin() as db:
        db.add(
            User(
                id="paper-user",
                email="paper@example.test",
                password=password_hash("Paper-Test-Password-123"),
                role=role,
                enabled=True,
            )
        )
    result = client.post(
        "/api/v1/auth/login",
        json={"email": "paper@example.test", "password": "Paper-Test-Password-123"},
    )
    assert result.status_code == 200
    return {"X-CSRF-Token": result.json()["csrf"]}


def account_body():
    return {"account_id": "api-paper", "universe": {"SYNTH": "technology"}}


@pytest.mark.parametrize("role", ["admin", "viewer", "analyst", "reviewer", "broker_reader"])
def test_other_roles_cannot_create_paper_accounts(client, role):
    headers = sign_in(client, role)
    assert (
        client.post("/api/v1/paper/accounts", json=account_body(), headers=headers).status_code
        == 403
    )
    assert client.get("/api/v1/paper/accounts").status_code == 200


def test_anonymous_service_key_and_missing_csrf_cannot_trade(client):
    assert client.post("/api/v1/paper/accounts", json=account_body()).status_code == 401
    assert (
        client.post(
            "/api/v1/paper/accounts",
            json=account_body(),
            headers={"Authorization": "Bearer dashboard-test"},
        ).status_code
        == 401
    )
    sign_in(client)
    assert client.post("/api/v1/paper/accounts", json=account_body()).status_code == 403


def test_operator_api_lifecycle_and_account_isolation_without_network(client):
    headers = sign_in(client)
    client.app.state.controls_broker_factory = lambda: (_ for _ in ()).throw(
        AssertionError("Paper simulator must never use external broker")
    )
    response = client.post("/api/v1/paper/accounts", json=account_body(), headers=headers)
    assert response.status_code == 200 and response.json()["authorized"] is False
    assert client.post("/api/v1/paper/accounts", json=account_body(), headers=headers).json()[
        "duplicate"
    ]
    base = "/api/v1/paper/accounts/api-paper"
    quote = {
        "command_id": "q1",
        "symbol": "SYNTH",
        "observed_at": datetime.now(UTC).isoformat(),
        "bid": "99",
        "ask": "100",
        "bid_size": 100,
        "ask_size": 100,
    }
    assert client.post(base + "/quotes", json=quote, headers=headers).status_code == 200
    order = client.post(
        base + "/orders",
        json={
            "command_id": "buy",
            "symbol": "SYNTH",
            "side": "BUY",
            "quantity": 10,
            "stop_price": "95",
        },
        headers=headers,
    )
    assert order.json()["status"] == "ACCEPTED", order.text
    quote.update(command_id="q2", observed_at=datetime.now(UTC).isoformat())
    q = client.post(base + "/quotes", json=quote, headers=headers).json()["quote_id"]
    filled = client.post(
        base + "/fills",
        json={"command_id": "filled", "order_id": order.json()["order_id"], "quote_id": q},
        headers=headers,
    )
    assert filled.json()["status"] == "FILLED", filled.text
    snap = client.get(base).json()
    assert snap["reconciliation"]["status"] == "MATCH"
    assert snap["state"]["positions"]["SYNTH"]["quantity"] == 10
    assert snap["forward_acceptance"] == "NOT_ESTABLISHED"
    assert len(client.get(base + "/journal?limit=2").json()["items"]) == 2
    assert client.get("/api/v1/paper/accounts/unknown").status_code == 404


@pytest.mark.parametrize("patch", [{"mode": "live"}, {"mode": "paper"}, {"margin": True}])
def test_only_strict_synthetic_account_contract_is_accepted(client, patch):
    headers = sign_in(client)
    assert (
        client.post(
            "/api/v1/paper/accounts", json=account_body() | patch, headers=headers
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"side": "SHORT"},
        {"quantity": 0},
        {"quantity": 1.5},
        {"quantity": True},
        {"margin_requested": True},
        {"borrow_requested": True},
        {"stop_price": "NaN"},
        {"asset_class": "gold"},
    ],
)
def test_forbidden_or_invalid_orders_rejected(client, patch):
    headers = sign_in(client)
    client.post("/api/v1/paper/accounts", json=account_body(), headers=headers)
    request = {
        "command_id": "bad",
        "symbol": "SYNTH",
        "side": "BUY",
        "quantity": 10,
        "stop_price": "95",
    } | patch
    assert (
        client.post(
            "/api/v1/paper/accounts/api-paper/orders", json=request, headers=headers
        ).status_code
        == 422
    )
