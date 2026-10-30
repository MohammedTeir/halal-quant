"""Exercise the SQL Editor bootstrap on CI PostgreSQL; no external services."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from services.accounts.access import digest


@pytest.fixture
def api_overrides():
    return {"session_cookie_secure": False}


def test_sql_editor_bootstrap_creates_one_time_admin_without_public_registration(client):
    engine = client.app.state.engine
    if engine.dialect.name != "postgresql":
        pytest.skip("SQL Editor bootstrap requires PostgreSQL; exercised by hosted CI")
    script = (Path(__file__).resolve().parents[2] / "infra/sql/bootstrap_admin.sql").read_text()
    function = script.split("-- Edit only the email below.")[0]
    call = text("SELECT pg_temp.hq_bootstrap_admin(:email, :origin)")
    origin = "https://halal-quant.vercel.app"
    with engine.connect() as connection:
        connection.exec_driver_sql(function)
        for email, site in [("invalid", origin), ("admin@example.test", "http://bad.example.test")]:
            with pytest.raises(DBAPIError), connection.begin_nested():
                connection.scalar(call, {"email": email, "origin": site})
        link = connection.scalar(call, {"email": "ADMIN@example.test", "origin": origin})
        token = link.split("#recover=")[1]
        assert len(token) == 64
        stored = connection.execute(text("SELECT email, password, role FROM users")).one()
        assert tuple(stored) == ("admin@example.test", "", "admin")
        assert connection.scalar(text("SELECT id FROM access_tokens")) == digest(token)
        connection.commit()
        # Existing accounts cannot be overwritten even with a valid operator email.
        with pytest.raises(DBAPIError):
            connection.scalar(call, {"email": "another@example.test", "origin": origin})
        connection.rollback()
        assert connection.scalar(text("SELECT count(*) FROM users")) == 1
        connection.commit()
        body = {"token": token, "password": "SQL-bootstrap-fixture-password"}
        assert client.post("/api/v1/auth/recover", json=body).status_code == 200
        assert client.post("/api/v1/auth/recover", json=body).status_code == 400
        login = client.post(
            "/api/v1/auth/login", json={"email": "admin@example.test", "password": body["password"]}
        )
        assert login.status_code == 200
        assert client.get("/api/v1/admin/users").status_code == 200
