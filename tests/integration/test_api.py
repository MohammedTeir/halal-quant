from datetime import UTC, datetime, timedelta

import pytest


def payload():
    return {
        "schema_version": "1.0",
        "event_id": "test:1",
        "strategy": "adaptive_pullback",
        "strategy_version": "1.0.0",
        "asset_class": "stock",
        "symbol": "NASDAQ:EXAMPLE",
        "timeframe": "240",
        "action": "ENTRY_CANDIDATE",
        "bar_time": datetime.now(UTC).isoformat(),
        "price": "100.25",
    }


WEBHOOK = {"X-Webhook-Key": "webhook-test"}
DASHBOARD = {"Authorization": "Bearer dashboard-test"}


def test_ingestion_audit_and_replay(client):
    assert client.get("/health/ready").status_code == 200
    body = payload()
    result = client.post("/api/v1/webhooks/tradingview", json=body, headers=WEBHOOK)
    assert result.status_code == 200
    assert result.json() == {"event_id": "test:1", "duplicate": False, "authorized": False}
    assert client.post("/api/v1/webhooks/tradingview", json=body, headers=WEBHOOK).json()[
        "duplicate"
    ]
    body["price"] = "101"
    assert (
        client.post("/api/v1/webhooks/tradingview", json=body, headers=WEBHOOK).status_code == 409
    )
    assert len(client.get("/api/v1/signals", headers=DASHBOARD).json()["items"]) == 1
    assert len(client.get("/api/v1/audit", headers=DASHBOARD).json()["items"]) == 1


def test_authentication_separation(client):
    assert client.get("/api/v1/signals").status_code == 401
    assert (
        client.get("/api/v1/signals", headers={"Authorization": "Bearer webhook-test"}).status_code
        == 401
    )
    assert (
        client.post("/api/v1/webhooks/tradingview", json=payload(), headers=DASHBOARD).status_code
        == 401
    )


@pytest.mark.parametrize(
    "change",
    [
        {"action": "SELL_SHORT"},
        {"price": "NaN"},
        {"price": "0"},
        {"asset_class": "gold"},
        {"authorized": True},
        {"bar_time": "2025-01-01T12:00:00"},
        {"bar_time": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
        {"bar_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
    ],
)
def test_invalid_or_unsafe_signals(client, change):
    assert (
        client.post(
            "/api/v1/webhooks/tradingview", json=payload() | change, headers=WEBHOOK
        ).status_code
        == 422
    )
