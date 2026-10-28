import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.config.settings import Settings, get_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")
    command.check(config)
    app = create_app(
        Settings(
            database_url=url,
            dashboard_api_key="dashboard-test",
            tradingview_webhook_key="webhook-test",
            data_ingestion_key="data-test",
            _env_file=None,
        )
    )
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    get_settings.cache_clear()
