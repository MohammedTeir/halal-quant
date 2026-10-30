"""Safe operator setup modes: mocked transport, never real Telegram requests."""

import sys
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from services.notifications import worker
from services.notifications.models import ServiceState


class FakeTelegram:
    def __init__(self, name="halalquant_bot", webhook=""):
        self.name, self.webhook, self.calls = name, webhook, []

    def verified(self, method, payload):
        self.calls.append(method)
        if method == "getMe":
            return {"is_bot": True, "username": self.name}
        if method == "getWebhookInfo":
            return {"url": self.webhook}
        raise AssertionError("Setup must not poll updates or send messages")


def test_check_is_read_only_and_confirms_bot_without_consuming_updates(client):
    sessions = sessionmaker(client.app.state.engine)
    with sessions() as db:
        before = [(s.id, s.value) for s in db.scalars(select(ServiceState))]
    telegram = FakeTelegram()
    result = worker.check_configuration(sessions, telegram, "@halalquant_bot")
    assert result == {
        "database": "ready",
        "bot": "@halalquant_bot",
        "pending_messages": 0,
        "webhook": False,
        "messages_sent": 0,
    }
    assert telegram.calls == ["getMe", "getWebhookInfo"]
    with sessions() as db:
        assert [(s.id, s.value) for s in db.scalars(select(ServiceState))] == before


@pytest.mark.parametrize(
    "name,webhook",
    [("different_bot", ""), ("halalquant_bot", "https://example.test/private-webhook")],
)
def test_check_rejects_wrong_bot_and_webhook_without_disclosing_secrets(client, name, webhook):
    sessions = sessionmaker(client.app.state.engine)
    with pytest.raises(ValueError) as error:
        worker.check_configuration(sessions, FakeTelegram(name, webhook), "halalquant_bot")
    assert "private-webhook" not in str(error.value)


@pytest.mark.parametrize("mode", ["--check", "--link-only"])
def test_setup_modes_cannot_reach_delivery(client, monkeypatch, mode):
    engine = Mock()
    sessions = object()
    telegram = Mock()
    monkeypatch.setattr(worker, "session_factory", lambda _: (engine, sessions))
    monkeypatch.setattr(worker, "Telegram", lambda _: telegram)
    monkeypatch.setattr(worker, "check_configuration", lambda *args: {"messages_sent": 0})
    poll = Mock()
    send = Mock(side_effect=AssertionError("No sends permitted in setup mode"))
    monkeypatch.setattr(worker, "poll_links", poll)
    monkeypatch.setattr(worker, "deliver_one", send)
    monkeypatch.setattr(sys, "argv", ["worker", mode, "--once", "--expected-bot", "halalquant_bot"])
    worker.main()
    assert not send.called
    assert poll.call_count == (1 if mode == "--link-only" else 0)
    telegram.close.assert_called_once()
    engine.dispose.assert_called_once()


def test_normal_worker_mode_can_deliver_after_identity_check(client, monkeypatch):
    engine, telegram = Mock(), Mock()
    sessions = object()
    monkeypatch.setattr(worker, "session_factory", lambda _: (engine, sessions))
    monkeypatch.setattr(worker, "Telegram", lambda _: telegram)
    checks = Mock(return_value={"messages_sent": 0})
    poll, send = Mock(), Mock()
    monkeypatch.setattr(worker, "check_configuration", checks)
    monkeypatch.setattr(worker, "poll_links", poll)
    monkeypatch.setattr(worker, "deliver_one", send)
    monkeypatch.setattr(sys, "argv", ["worker", "--once", "--expected-bot", "halalquant_bot"])
    worker.main()
    checks.assert_called_once_with(sessions, telegram, "halalquant_bot")
    poll.assert_called_once_with(sessions, telegram)
    send.assert_called_once_with(sessions, telegram)
    telegram.close.assert_called_once()
