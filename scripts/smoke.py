"""Development-only smoke: writes a synthetic signal/audit to the configured API."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx


def smoke():
    with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=10) as client:
        assert client.get("/health/ready").json() == {"status": "ready"}
        assert client.get("/api/v1/signals").status_code == 401
        event = f"smoke:{uuid4()}"
        payload = {
            "schema_version": "1.0",
            "event_id": event,
            "strategy": "adaptive_pullback",
            "strategy_version": "1.0.0",
            "asset_class": "stock",
            "symbol": "EXAMPLE",
            "timeframe": "240",
            "action": "ENTRY_CANDIDATE",
            "bar_time": datetime.now(UTC).isoformat(),
            "price": "100.25",
        }
        headers = {"X-Webhook-Key": os.environ["TRADINGVIEW_WEBHOOK_KEY"]}
        first = client.post("/api/v1/webhooks/tradingview", json=payload, headers=headers)
        assert first.status_code == 200, first.status_code
        assert first.json()["authorized"] is False
        assert first.json()["duplicate"] is False
        assert (
            client.post("/api/v1/webhooks/tradingview", json=payload, headers=headers).json()[
                "duplicate"
            ]
            is True
        )
        dashboard = {"Authorization": f"Bearer {os.environ['DASHBOARD_API_KEY']}"}
        signals = client.get("/api/v1/signals", headers=dashboard).json()["items"]
        assert any(item["event_id"] == event for item in signals)
        audit = client.get("/api/v1/audit", headers=dashboard).json()["items"]
        assert sum(item["subject"] == event for item in audit) == 1
        print(
            "PASS: ready, auth, ingestion, replay, stored signal and single audit; no order authorization"
        )
        return event


if __name__ == "__main__":
    smoke()
