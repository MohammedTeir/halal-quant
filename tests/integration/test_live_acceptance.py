import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from services.accounts.access import locked, password_hash
from services.notifications.models import User
from services.operations.live_accounts import AcceptanceFailure, run_checks


@pytest.fixture
def api_overrides():
    return {"session_cookie_secure": True}


@pytest.fixture
def owner_sessions(client):
    sessions = sessionmaker(client.app.state.engine, expire_on_commit=False)
    with locked(sessions) as db:
        db.add(
            User(
                id="real-owner",
                email="owner@example.test",
                password=password_hash("Owner-password-not-used-by-runner"),
                role="admin",
                enabled=True,
            )
        )
    return sessions


def test_live_account_runner_exercises_real_api_and_cleans_only_its_fixtures(
    client, owner_sessions
):
    result = run_checks(
        owner_sessions,
        "https://testserver",
        lambda: TestClient(client.app, base_url="https://testserver"),
    )
    assert result["status"] == "PASSED" and all(result["checks"].values())
    assert result["temporary_accounts_removed"]
    with owner_sessions() as db:
        assert [u.id for u in db.scalars(select(User))] == ["real-owner"]
        assert db.get(User, "real-owner").enabled


def test_live_runner_cleans_fixtures_when_gateway_rejects_requests(client, owner_sessions):
    import httpx

    class BadGateway:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, *args, **kwargs):
            return httpx.Response(503)

    with pytest.raises(AcceptanceFailure):
        run_checks(owner_sessions, "https://testserver", BadGateway)
    with owner_sessions() as db:
        assert [u.id for u in db.scalars(select(User))] == ["real-owner"]
