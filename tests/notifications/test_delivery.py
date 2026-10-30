import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from apps.api.db import Base
from services.accounts.access import locked
from services.notifications.delivery import deliver_one, enqueue
from services.notifications.linking import poll_links
from services.notifications.models import Destination, Outbox, ServiceState, User
from services.notifications.telegram import Telegram


@pytest.fixture
def sessions(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "delivery.db"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as db:
        db.add_all(
            [
                ServiceState(id="access", value=0),
                ServiceState(id="delivery", value=0),
                ServiceState(id="telegram_offset", value=0),
            ]
        )
        db.add(User(id="u", email="a@example.test", password="", role="viewer", enabled=True))
        db.add(
            Destination(
                id="d",
                user_id="u",
                chat_id="123",
                enabled=True,
                language="en",
                kinds=["signal", "decision", "risk_stop"],
            )
        )
    yield factory
    engine.dispose()


def queued(sessions, key="e"):
    with locked(sessions) as db:
        enqueue(db, "decision", key, {"status": "HOLD"})
    with sessions() as db:
        return db.scalar(select(Outbox).where(Outbox.event_key == key)).id


def record(sessions, identity):
    with sessions() as db:
        return db.get(Outbox, identity)


class Transport:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def call(self, method, payload):
        self.calls.append((method, payload))
        if self.error:
            raise self.error
        return self.result


def response(code, body):
    return httpx.Response(code, json=body)


def test_success_idempotency_and_persistence(sessions):
    identity = queued(sessions)
    assert queued(sessions) == identity
    fake = Transport(response(200, {"ok": True, "result": {"message_id": 42}}))
    assert deliver_one(sessions, fake)
    stored = record(sessions, identity)
    assert stored.status == "SENT" and stored.message_id == "42"
    assert not deliver_one(sessions, fake, now=int(time.time()) + 10)
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "failure",
    [
        "read_timeout",
        "write_error",
        "5xx",
        "malformed",
        "invalid_success",
        "429_no_delay",
        "json_array",
        "429_bad_parameters",
    ],
)
def test_uncertain_is_never_resent(sessions, failure):
    identity = queued(sessions)
    fake = {
        "json_array": Transport(response(200, [])),
        "429_bad_parameters": Transport(
            response(429, {"ok": False, "error_code": 429, "parameters": []})
        ),
        "read_timeout": Transport(error=httpx.ReadTimeout("secret URL must not escape")),
        "write_error": Transport(error=httpx.WriteError("secret")),
        "5xx": Transport(response(502, {"ok": False, "error_code": 502})),
        "malformed": Transport(httpx.Response(200, text="bad")),
        "invalid_success": Transport(response(200, {"ok": True})),
        "429_no_delay": Transport(response(429, {"ok": False, "error_code": 429})),
    }[failure]
    deliver_one(sessions, fake)
    assert record(sessions, identity).status == "UNCERTAIN"
    deliver_one(sessions, fake, now=int(time.time()) + 999)
    assert len(fake.calls) == 1
    assert "secret" not in record(sessions, identity).error


def test_rate_limit_global_pause_and_safe_retry(sessions):
    identity = queued(sessions)
    now = int(time.time())
    fake = Transport(
        response(429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 30}})
    )
    deliver_one(sessions, fake, now=now)
    assert record(sessions, identity).status == "RETRY"
    assert not deliver_one(sessions, fake, now=now + 29)
    fake.result = response(200, {"ok": True, "result": {"message_id": 1}})
    deliver_one(sessions, fake, now=now + 31)
    assert record(sessions, identity).status == "SENT"
    assert len(fake.calls) == 2


def test_connect_failures_are_bounded_safe_retries(sessions):
    identity = queued(sessions)
    fake = Transport(error=httpx.ConnectTimeout("no connection established"))
    now = int(time.time())
    for attempt in range(5):
        deliver_one(sessions, fake, now=now + attempt * 31)
    stored = record(sessions, identity)
    assert stored.status == "FAILED" and stored.attempts == 5
    assert stored.error == "SAFE_RETRIES_EXHAUSTED"


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_confirmed_rejection(sessions, code):
    identity = queued(sessions)
    deliver_one(
        sessions,
        Transport(response(code, {"ok": False, "error_code": code, "description": "sensitive"})),
    )
    stored = record(sessions, identity)
    assert stored.status == "FAILED" and "sensitive" not in stored.error


def test_interrupted_claim_is_uncertain(sessions):
    identity = queued(sessions)
    now = int(time.time())
    with locked(sessions) as db:
        row = db.get(Outbox, identity)
        row.status, row.available = "SENDING", now - 121
    fake = Transport()
    deliver_one(sessions, fake, now=now)
    assert record(sessions, identity).status == "UNCERTAIN"
    assert fake.calls == []


def test_disabled_user_or_destination_cancels_without_network(sessions):
    identity = queued(sessions)
    with locked(sessions) as db:
        db.get(User, "u").enabled = False
    fake = Transport()
    deliver_one(sessions, fake)
    assert record(sessions, identity).status == "CANCELLED" and not fake.calls


def test_parallel_workers_claim_once(sessions):
    identity = queued(sessions)
    fake = Transport(response(200, {"ok": True, "result": {"message_id": 42}}))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: deliver_one(sessions, fake), range(2)))
    assert sum(results) == 1 and len(fake.calls) == 1
    assert record(sessions, identity).status == "SENT"


def test_per_chat_pacing(sessions):
    queued(sessions, "first")
    second = queued(sessions, "second")
    fake = Transport(response(200, {"ok": True, "result": {"message_id": 42}}))
    now = int(time.time())
    deliver_one(sessions, fake, now=now)
    deliver_one(sessions, fake, now=now + 1)
    assert len(fake.calls) == 1
    deliver_one(sessions, fake, now=now + 3)
    assert len(fake.calls) == 2 and record(sessions, second).status == "SENT"


def test_telegram_transport_mock_and_redaction():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return response(200, {"ok": True, "result": {"id": 123}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = Telegram("fake-token", client)
    assert adapter.verified("getMe", {}) == {"id": 123}
    assert seen == ["/botfake-token/getMe"]
    adapter.close()


def test_poll_offset_survives_restart(sessions):
    class Poller:
        def verified(self, method, payload):
            assert method == "getUpdates" and payload["offset"] in (0, 8)
            return (
                [{"update_id": 7, "message": {"text": "unrelated"}}]
                if payload["offset"] == 0
                else []
            )

    poll_links(sessions, Poller())
    poll_links(sessions, Poller())
    with sessions() as db:
        assert db.get(ServiceState, "telegram_offset").value == 8


def test_exhausted_rate_limit_still_pauses_other_messages(sessions):
    identity = queued(sessions)
    now = int(time.time())
    fake = Transport(
        response(429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 30}})
    )
    for attempt in range(5):
        deliver_one(sessions, fake, now=now + attempt * 31)
    assert record(sessions, identity).status == "FAILED"
    queued(sessions, "another-message")
    assert not deliver_one(sessions, fake, now=now + 125)
    assert len(fake.calls) == 5
