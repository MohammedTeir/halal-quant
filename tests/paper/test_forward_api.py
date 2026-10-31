from datetime import timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from apps.api.db import utcnow
from services.accounts.access import password_hash
from services.notifications.models import User
from services.paper.schemas import ForwardProtocol
from tests.paper.test_api import sign_in


@pytest.fixture
def api_overrides():
    return {
        "paper_trading_enabled": True,
        "paper_forward_enabled": True,
        "session_cookie_secure": False,
    }


def proposal():
    providers = {
        k: k + "-fixture" for k in ("news", "calendar", "fomc", "earnings", "corporate_actions")
    }
    return ForwardProtocol(
        run_id="api-forward-run",
        account_id="api-forward",
        feed_providers=providers,
        data_review={p: "a" * 64 for p in ["alpaca_iex", *providers.values()]},
        source_limitations="Fictional fixture sources; no real approval is represented",
        references=["https://example.invalid/source"],
    ).model_dump(mode="json")


def test_forward_http_requires_distinct_reviewer_and_cannot_finalize_early(client):
    headers = sign_in(client)
    account = {"account_id": "api-forward", "mode": "forward", "universe": {"AAPL": "technology"}}
    assert client.post("/api/v1/paper/accounts", json=account, headers=headers).status_code == 200
    proposed = client.post("/api/v1/paper/runs", json=proposal(), headers=headers)
    assert proposed.status_code == 200, proposed.text
    body = {
        "protocol_sha256": proposed.json()["protocol_sha256"],
        "approved": True,
        "expires_at": (utcnow() + timedelta(days=60)).isoformat(),
        "note": "Fictional fixture source review for isolated API acceptance only",
    }
    assert (
        client.post(
            "/api/v1/paper/runs/api-forward-run/review", json=body, headers=headers
        ).status_code
        == 403
    )
    with sessionmaker(client.app.state.engine).begin() as db:
        db.add(
            User(
                id="api-reviewer",
                email="reviewer@example.test",
                password=password_hash("Paper-Test-Password-123"),
                role="reviewer",
                enabled=True,
            )
        )
    result = client.post(
        "/api/v1/auth/login",
        json={"email": "reviewer@example.test", "password": "Paper-Test-Password-123"},
    )
    review_headers = {"X-CSRF-Token": result.json()["csrf"]}
    bad = client.post(
        "/api/v1/paper/runs/api-forward-run/review",
        json=body | {"protocol_sha256": "f" * 64},
        headers=review_headers,
    )
    assert bad.status_code == 409
    assert (
        client.post(
            "/api/v1/paper/runs/api-forward-run/review", json=body, headers=review_headers
        ).status_code
        == 200
    )
    repeated = client.post(
        "/api/v1/paper/runs/api-forward-run/review", json=body, headers=review_headers
    )
    assert repeated.json()["duplicate"]
    status = client.get("/api/v1/paper/runs/api-forward-run").json()
    assert status["status"] == "NOT_CONFIRMED"
    assert "INSUFFICIENT_COMPLETE_MARKET_SESSIONS" in status["blockers"]
    assert (
        client.post(
            "/api/v1/paper/runs/api-forward-run/finalize", json={}, headers=review_headers
        ).status_code
        == 403
    )
    result = client.post(
        "/api/v1/auth/login",
        json={"email": "paper@example.test", "password": "Paper-Test-Password-123"},
    )
    headers = {"X-CSRF-Token": result.json()["csrf"]}
    assert (
        client.post("/api/v1/paper/runs/api-forward-run/finalize", json={}, headers=headers).json()[
            "status"
        ]
        == "NOT_CONFIRMED"
    )
    raw_order = {
        "command_id": "forged",
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 1,
        "stop_price": "95",
    }
    assert (
        client.post(
            "/api/v1/paper/accounts/api-forward/orders", json=raw_order, headers=headers
        ).status_code
        == 422
    )


@pytest.mark.parametrize("role", ["admin", "analyst", "viewer", "broker_reader"])
def test_unprivileged_roles_cannot_propose_or_review(client, role):
    headers = sign_in(client, role)
    assert client.post("/api/v1/paper/runs", json=proposal(), headers=headers).status_code == 403
    assert client.get("/api/v1/paper/runs").status_code == 200
