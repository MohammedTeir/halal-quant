from datetime import timedelta

import pytest

from apps.api.db import BrokerCapture, utcnow
from tests.controls.operations_fixtures import broker_facts, signal

READ = {"Authorization": "Bearer dashboard-test"}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/dashboard/overview",
        "/api/v1/dashboard/research",
        "/api/v1/portfolio",
        "/api/v1/notifications/preview",
    ],
)
def test_dashboard_data_is_private_and_not_cached(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert client.get(path, headers=READ).status_code == 200


def test_shell_has_strict_csp_and_no_embedded_credentials(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert 'lang="en" dir="ltr"' in response.text
    assert "dashboard-test" not in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "'unsafe-inline'" not in response.headers["content-security-policy"]
    js = client.get("/dashboard/assets/app.js")
    assert js.status_code == 200
    assert "innerHTML" not in js.text
    assert "halal-quant.language" in js.text


def test_signal_to_notification_preview_replays_without_sending(client):
    body = signal()
    headers = {"X-Webhook-Key": "webhook-test"}
    assert (
        client.post("/api/v1/webhooks/tradingview", headers=headers, json=body).status_code == 200
    )
    assert (
        client.post("/api/v1/webhooks/tradingview", headers=headers, json=body).json()["duplicate"]
        is True
    )
    preview = client.get("/api/v1/notifications/preview", headers=READ).json()
    assert preview["delivery_enabled"] is False
    assert len(preview["items"]) == 1
    assert preview["items"][0]["delivery_status"] == "PREVIEW_ONLY"
    assert "AAPL" in preview["items"][0]["text"]
    assert preview["items"][0]["authorized"] is False
    assert client.get("/api/v1/dashboard/overview", headers=READ).json()["counts"]["signals"] == 1


def test_portfolio_never_falls_back_after_newer_capture_failure(client):
    now = utcnow()
    facts = broker_facts() | {
        "account_number": "PRIVATE-IDENTITY",
        "settled_cash_verified": False,
        "settled_cash": "99999",
        "positions": [
            {
                "symbol": "AAPL",
                "quantity": "5",
                "available_quantity": "3",
                "market_value": "500",
                "private_field": "HIDDEN",
            }
        ],
    }
    with client.app.state.engine.begin() as connection:
        connection.execute(
            BrokerCapture.__table__.insert(),
            {
                "id": "dashboard-good",
                "request_sha256": "a" * 64,
                "kind": "account",
                "scope": "private-id",
                "status": "SUCCEEDED",
                "created_at": now,
                "completed_at": utcnow(),
                "payload": facts,
            },
        )
    response = client.get("/api/v1/portfolio", headers=READ)
    assert response.json()["settled_cash"] is None
    assert response.json()["positions"][0]["sellable_quantity"] == "3"
    assert "HIDDEN" not in response.text
    assert "PRIVATE-IDENTITY" not in response.text and "private-id" not in response.text
    with client.app.state.engine.begin() as connection:
        connection.execute(
            BrokerCapture.__table__.insert(),
            {
                "id": "dashboard-failed",
                "request_sha256": "b" * 64,
                "kind": "account",
                "scope": None,
                "status": "FAILED",
                "created_at": utcnow(),
            },
        )
    assert client.get("/api/v1/portfolio", headers=READ).json()["status"] == "UNAVAILABLE"


def test_old_portfolio_observation_is_labeled_stale(client):
    old = utcnow() - timedelta(hours=1)
    facts = broker_facts() | {"observed_at": old.isoformat()}
    with client.app.state.engine.begin() as connection:
        connection.execute(
            BrokerCapture.__table__.insert(),
            {
                "id": "dashboard-old",
                "request_sha256": "a" * 64,
                "kind": "account",
                "scope": "private-id",
                "status": "SUCCEEDED",
                "created_at": old,
                "completed_at": old,
                "payload": facts,
            },
        )
    assert client.get("/api/v1/portfolio", headers=READ).json()["status"] == "STALE_OBSERVATION"


def test_notification_preview_defaults_to_english_and_supports_arabic(client):
    client.post(
        "/api/v1/webhooks/tradingview", headers={"X-Webhook-Key": "webhook-test"}, json=signal()
    )
    english = client.get("/api/v1/notifications/preview", headers=READ).json()["items"][0]
    arabic = client.get("/api/v1/notifications/preview?language=ar", headers=READ).json()["items"][
        0
    ]
    assert english["language"] == "en"
    assert "Research signal" in english["text"]
    assert arabic["language"] == "ar"
    assert "إشارة بحثية" in arabic["text"]
    assert english["texts"] == arabic["texts"]
    assert client.get("/api/v1/notifications/preview?language=fr", headers=READ).status_code == 422
