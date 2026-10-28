import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.main import create_app
from packages.config.settings import Settings


def test_live_execution_cannot_be_enabled():
    with pytest.raises(ValidationError):
        Settings(live_trading_enabled=True, _env_file=None)


def test_credentials_must_differ():
    with pytest.raises(ValidationError):
        Settings(dashboard_api_key="same", tradingview_webhook_key="same", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(dashboard_api_key="same", data_ingestion_key="same", _env_file=None)


def test_missing_credentials_deny_access_and_missing_migrations_not_ready(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'empty.db'}",
            dashboard_api_key="",
            tradingview_webhook_key="",
            _env_file=None,
        )
    )
    with TestClient(app) as client:
        assert client.get("/health/live").json()["live_execution"] is False
        assert client.get("/health/ready").status_code == 503
        assert (
            client.get("/api/v1/signals", headers={"Authorization": "Bearer "}).status_code == 401
        )
        assert client.post("/api/v1/webhooks/tradingview", json={}).status_code == 401
        assert client.post("/api/v1/data/import", json={}).status_code == 401
        assert client.get("/api/v1/news").status_code == 401
    app.state.engine.dispose()
