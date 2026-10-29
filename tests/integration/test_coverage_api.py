from datetime import UTC, datetime, timedelta

from alembic import command
from alembic.config import Config

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)
READ = {"Authorization": "Bearer dashboard-test"}
WRITE = {"X-Data-Key": "data-test"}


def params(**changes):
    return {
        "provider": "fixture",
        "symbol": "AAPL",
        "asset_class": "stock",
        "purpose": "company_news",
        "window_start": (NOW - timedelta(hours=2)).isoformat(),
        "window_end": NOW.isoformat(),
    } | changes


def batch():
    return {
        "provider": "fixture",
        "kind": "news",
        "batch_id": "coverage-1",
        "coverage": {
            "symbols": ["AAPL"],
            "asset_classes": ["stock"],
            "purpose": "company_news",
            "starts_at": (NOW - timedelta(days=1)).isoformat(),
            "ends_at": (NOW + timedelta(days=1)).isoformat(),
        },
        "records": [],
    }


def test_coverage_route_role_scope_and_replay(client, monkeypatch):
    monkeypatch.setattr("apps.api.main.utcnow", lambda: NOW)
    assert client.get("/api/v1/data/coverage", params=params()).status_code == 401
    assert client.post("/api/v1/data/import", headers=WRITE, json=batch()).status_code == 200
    first = client.get("/api/v1/data/coverage", headers=READ, params=params()).json()
    assert first["required_feed_available"] and not first["authorized_for_entry"]
    wrong = client.get("/api/v1/data/coverage", headers=READ, params=params(symbol="OTHER")).json()
    assert wrong["state"] == "MISSING"
    replay = client.post("/api/v1/data/import", headers=WRITE, json=batch()).json()
    assert replay["duplicate"]
    monkeypatch.setattr("apps.api.main.utcnow", lambda: NOW + timedelta(hours=1))
    stale = client.get("/api/v1/data/coverage", headers=READ, params=params()).json()
    assert stale["state"] == "STALE" and not stale["required_feed_available"]


def test_coverage_invalid_window_and_future_asof_rejected(client, monkeypatch):
    monkeypatch.setattr("apps.api.main.utcnow", lambda: NOW)
    assert (
        client.get(
            "/api/v1/data/coverage", headers=READ, params=params(window_start=NOW.isoformat())
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/data/coverage",
            headers=READ,
            params=params(as_of=(NOW + timedelta(days=1)).isoformat()),
        ).status_code
        == 422
    )
    value = batch()
    value["kind"] = "calendar"
    assert client.post("/api/v1/data/import", headers=WRITE, json=value).status_code == 422
    assert (
        client.get("/api/v1/data/coverage", headers=READ, params=params()).json()["state"]
        == "MISSING"
    )


def test_coverage_migration_required_preserves_older_facts(client, monkeypatch):
    monkeypatch.setattr("apps.api.main.utcnow", lambda: NOW)
    assert client.post("/api/v1/data/import", headers=WRITE, json=batch()).status_code == 200
    config = Config("alembic.ini")
    command.downgrade(config, "0004_gemini_jobs")
    assert client.get("/health/ready").status_code == 503
    assert client.get("/api/v1/data/coverage", headers=READ, params=params()).status_code == 503
    command.upgrade(config, "head")
    assert client.get("/health/ready").status_code == 200
    # Lost coverage cannot be invented by replaying the old successful batch ID.
    assert client.post("/api/v1/data/import", headers=WRITE, json=batch()).json()["duplicate"]
    assert (
        client.get("/api/v1/data/coverage", headers=READ, params=params()).json()["state"]
        == "MISSING"
    )
