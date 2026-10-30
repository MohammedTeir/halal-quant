"""All Telegram network calls are fakes. No mail transport is installed or invoked."""

import time

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from services.accounts.access import digest, issue, locked, password_hash
from services.notifications.delivery import enqueue
from services.notifications.linking import process_update
from services.notifications.models import AccessSession, Destination, OneTimeToken, Outbox, User

PASSWORD = "a-long-test-password"


@pytest.fixture
def api_overrides():
    return {"session_cookie_secure": False}


@pytest.fixture
def accounts(client):
    sessions = sessionmaker(client.app.state.engine, expire_on_commit=False)
    with locked(sessions) as db:
        db.add(
            User(
                id="admin",
                email="admin@example.test",
                password=password_hash(PASSWORD),
                role="admin",
                enabled=True,
            )
        )
        db.add(
            User(
                id="viewer",
                email="viewer@example.test",
                password=password_hash(PASSWORD),
                role="viewer",
                enabled=True,
            )
        )
    return sessions


def login(client, email="admin@example.test"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf"]}


def test_invitation_single_use_recovery_and_revocation(client, accounts):
    headers = login(client)
    assert client.get("/api/v1/dashboard/overview").status_code == 200
    assert (
        client.post("/api/v1/admin/invitations", json={"email": "new@example.test"}).status_code
        == 403
    )
    invitation = client.post(
        "/api/v1/admin/invitations",
        headers=headers,
        json={"email": "new@example.test", "role": "viewer"},
    )
    assert invitation.status_code == 200
    raw = invitation.json()["token"]
    with accounts() as db:
        token = db.get(OneTimeToken, digest(raw))
        assert token and token.expires > time.time()
        assert db.get(OneTimeToken, raw) is None
    body = {"token": raw, "password": PASSWORD}
    assert client.post("/api/v1/auth/recover", json=body).status_code == 200
    assert client.post("/api/v1/auth/recover", json=body).status_code == 400
    with accounts() as db:
        target = db.scalar(select(User).where(User.email == "new@example.test"))
    recovery = client.post(f"/api/v1/admin/users/{target.id}/recovery", headers=headers).json()[
        "token"
    ]
    login(client, "new@example.test")
    assert client.get("/api/v1/admin/users").status_code == 403
    assert (
        client.post(
            "/api/v1/auth/recover", json={"token": recovery, "password": PASSWORD}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/dashboard/overview").status_code == 401
    with accounts() as db:
        assert not db.scalars(select(AccessSession).where(AccessSession.user_id == target.id)).all()


def test_expired_tokens_disabled_users_and_last_admin(client, accounts):
    headers = login(client)
    assert (
        client.patch(
            "/api/v1/admin/users/admin", headers=headers, json={"role": "viewer", "enabled": True}
        ).status_code
        == 409
    )
    with locked(accounts) as db:
        raw = issue(db, db.get(User, "viewer"), "invite", -1)
    assert (
        client.post("/api/v1/auth/recover", json={"token": raw, "password": PASSWORD}).status_code
        == 400
    )
    recovery = client.post("/api/v1/admin/users/viewer/recovery", headers=headers).json()["token"]
    assert (
        client.patch(
            "/api/v1/admin/users/viewer", headers=headers, json={"role": "viewer", "enabled": False}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/recover", json={"token": recovery, "password": PASSWORD}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "viewer@example.test", "password": PASSWORD}
        ).status_code
        == 401
    )


def test_sessions_password_csrf_and_backend_permissions(client, accounts):
    headers = login(client, "viewer@example.test")
    assert (
        client.post("/api/v1/controls/kill-switch/engage", headers=headers, json={}).status_code
        == 403
    )
    assert client.post("/api/v1/decisions/evaluate", headers=headers, json={}).status_code in (
        403,
        404,
    )
    assert client.get("/api/v1/auth/me").headers["Cache-Control"] == "no-store"
    sessions = client.get("/api/v1/auth/sessions").json()["items"]
    assert len(sessions) == 1 and sessions[0]["current"]
    assert (
        client.post(
            "/api/v1/auth/password",
            json={"current_password": PASSWORD, "password": PASSWORD + "new"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/password",
            headers=headers,
            json={"current_password": "wrong", "password": PASSWORD + "new"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/password",
            headers=headers,
            json={"current_password": PASSWORD, "password": PASSWORD + "new"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me").status_code == 401


def test_role_change_disable_and_expiry_invalidate_session(client, accounts):
    login(client, "viewer@example.test")
    cookie = client.cookies.get("hq_session")
    admin = login(client)
    assert (
        client.patch(
            "/api/v1/admin/users/viewer", headers=admin, json={"role": "analyst", "enabled": True}
        ).status_code
        == 200
    )
    client.cookies.set("hq_session", cookie)
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.clear()
    login(client)
    with locked(accounts) as db:
        for record in db.scalars(select(AccessSession)):
            record.expires = int(time.time()) - 1
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_throttling_and_cookie_flags(client, accounts):
    response = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.test", "password": PASSWORD}
    )
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    for _ in range(20):
        response = client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.test", "password": "wrong"}
        )
    assert response.status_code == 429
    assert client.post("/api/v1/auth/register", json={}).status_code == 404


class FakeTelegram:
    def __init__(self, status="administrator"):
        self.status = status

    def verified(self, method, payload):
        if method == "getMe":
            return {"id": 99}
        return {"status": self.status}


def test_linking_preferences_and_delivery_isolation(client, accounts):
    headers = login(client)
    code = client.post("/api/v1/telegram/link-code", headers=headers).json()["code"]
    update = {
        "message": {
            "text": "/link " + code,
            "chat": {"id": -123, "type": "supergroup"},
            "from": {"id": 7},
        }
    }
    assert not process_update(accounts, FakeTelegram("member"), update)
    assert process_update(accounts, FakeTelegram(), update)
    assert not process_update(accounts, FakeTelegram(), update)
    dest = client.get("/api/v1/telegram/destinations").json()["items"][0]
    assert dest["language"] == "en" and dest["enabled"] is False
    assert (
        client.patch(
            "/api/v1/telegram/destinations/" + dest["id"],
            headers=headers,
            json={"enabled": True, "language": "ar", "kinds": ["risk_stop"]},
        ).status_code
        == 200
    )
    with locked(accounts) as db:
        enqueue(db, "risk_stop", "kill-test", {"status": "ENGAGED"})
        enqueue(db, "decision", "decision-test", {"status": "HOLD"})
    items = client.get("/api/v1/telegram/deliveries").json()["items"]
    assert len(items) == 1 and items[0]["status"] == "QUEUED"
    with accounts() as db:
        assert "تنبيه" in db.get(Outbox, items[0]["id"]).text
    other = login(client, "viewer@example.test")
    assert client.get("/api/v1/telegram/deliveries").json()["items"] == []
    assert (
        client.patch(
            "/api/v1/telegram/destinations/" + dest["id"],
            headers=other,
            json={"enabled": False, "language": "en", "kinds": []},
        ).status_code
        == 404
    )
    headers = login(client)
    assert (
        client.patch(
            "/api/v1/telegram/destinations/" + dest["id"],
            headers=headers,
            json={"enabled": False, "language": "en", "kinds": []},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/telegram/deliveries").json()["items"][0]["status"] == "CANCELLED"


def test_private_link_expiry_no_takeover_and_wrong_chat(client, accounts):
    headers = login(client)
    code = client.post("/api/v1/telegram/link-code", headers=headers).json()["code"]
    update = {
        "message": {
            "text": "/start " + code,
            "chat": {"id": 7, "type": "private"},
            "from": {"id": 8},
        }
    }
    assert not process_update(accounts, FakeTelegram(), update)
    update["message"]["from"]["id"] = 7
    assert process_update(accounts, FakeTelegram(), update)
    code = client.post("/api/v1/telegram/link-code", headers=headers).json()["code"]
    update["message"]["text"] = "/link " + code
    assert not process_update(accounts, FakeTelegram(), update)
    with locked(accounts) as db:
        db.get(OneTimeToken, digest(code)).expires = 0
    update["message"]["chat"]["id"] = 8
    update["message"]["from"]["id"] = 8
    assert not process_update(accounts, FakeTelegram(), update)


def test_admin_revokes_other_sessions_and_logout(client, accounts):
    login(client, "viewer@example.test")
    with accounts() as db:
        sid = db.scalar(select(AccessSession.id).where(AccessSession.user_id == "viewer"))
    headers = login(client)
    assert client.delete("/api/v1/auth/sessions/" + sid, headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize(
    "role,path",
    [
        ("analyst", "/api/v1/decisions/evaluate"),
        ("reviewer", "/api/v1/controls/reviews/methodologies"),
        ("operator", "/api/v1/controls/kill-switch/engage"),
        ("broker_reader", "/api/v1/controls/broker/refresh"),
    ],
)
def test_roles_are_enforced_on_existing_backend_routes(client, accounts, role, path):
    admin = login(client)
    client.patch("/api/v1/admin/users/viewer", headers=admin, json={"role": role, "enabled": True})
    headers = login(client, "viewer@example.test")
    # Schema validation is reached only after the correct role authenticates.
    assert client.post(path, headers=headers, json={}).status_code == 422
    assert (
        client.post(
            "/api/v1/admin/invitations", headers=headers, json={"email": "other@example.test"}
        ).status_code
        == 403
    )


def test_events_to_persistent_outbox_and_mock_delivery(client, accounts):
    import httpx

    from services.notifications.delivery import deliver_one
    from tests.controls.operations_fixtures import signal

    with locked(accounts) as db:
        db.add(
            Destination(
                id="all-events",
                user_id="admin",
                chat_id="777",
                enabled=True,
                language="en",
                kinds=["signal", "decision", "risk_stop"],
            )
        )
        db.get(User, "viewer").role = "operator"
    body = signal()
    webhook = {"X-Webhook-Key": "webhook-test"}
    assert (
        client.post("/api/v1/webhooks/tradingview", headers=webhook, json=body).status_code == 200
    )
    assert client.post("/api/v1/webhooks/tradingview", headers=webhook, json=body).json()[
        "duplicate"
    ]
    evaluation = {"evaluation_id": "notify-eval", "signal_id": body["event_id"], "score": 1.0}
    assert (
        client.post(
            "/api/v1/decisions/evaluate",
            headers={"X-Analysis-Key": "analysis-test"},
            json=evaluation,
        ).status_code
        == 200
    )
    assert client.post(
        "/api/v1/decisions/evaluate", headers={"X-Analysis-Key": "analysis-test"}, json=evaluation
    ).json()["duplicate"]
    headers = login(client, "viewer@example.test")
    kill = {
        "record_id": "notify-kill",
        "account_id": "account-test",
        "note": "Test risk-stop evidence only.",
        "references": ["https://example.test/evidence"],
    }
    assert (
        client.post("/api/v1/controls/kill-switch/engage", headers=headers, json=kill).status_code
        == 200
    )
    with locked(accounts) as db:
        db.add(
            Destination(
                id="late-subscriber",
                user_id="admin",
                chat_id="888",
                enabled=True,
                language="en",
                kinds=["risk_stop"],
            )
        )

    assert (
        client.post("/api/v1/controls/kill-switch/engage", headers=headers, json=kill).status_code
        == 200
    )
    login(client)
    items = client.get("/api/v1/telegram/deliveries").json()["items"]
    assert len(items) == 3 and {r["kind"] for r in items} == {"signal", "decision", "risk_stop"}

    class FakeSender:
        calls = 0

        def call(self, method, payload):
            assert method == "sendMessage" and payload["chat_id"] == "777"
            self.calls += 1
            return httpx.Response(200, json={"ok": True, "result": {"message_id": self.calls}})

    sender = FakeSender()
    now = int(time.time())
    for step in range(3):
        assert deliver_one(accounts, sender, now=now + step * 3)
    assert sender.calls == 3
    assert {r["status"] for r in client.get("/api/v1/telegram/deliveries").json()["items"]} == {
        "SENT"
    }
