import sys
from datetime import timedelta
from unittest.mock import Mock

from packages.config.settings import Settings
from services.paper import worker
from services.paper.models import PaperRun


def test_read_only_check_does_not_acquire_lease_or_contact_provider(
    forward_env, monkeypatch, capsys
):
    sessions, now, *_ = forward_env
    engine = Mock()
    settings = Settings(database_url="sqlite://", _env_file=None)
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "session_factory", lambda *args: (engine, sessions))
    monkeypatch.setattr(worker, "utcnow", lambda: now)
    monkeypatch.setattr(
        worker,
        "AlpacaPaperData",
        lambda *args: (_ for _ in ()).throw(AssertionError("No provider calls during --check")),
    )
    monkeypatch.setattr(sys, "argv", ["worker", "--run-id", "run-test", "--check"])
    worker.main()
    assert '"enabled": false' in capsys.readouterr().out
    with sessions() as db:
        assert db.get(PaperRun, "run-test").state["owner"] is None


def test_check_reports_expired_entry_review_but_keeps_owned_protection_available(
    forward_env, monkeypatch
):
    sessions, now, *_ = forward_env
    with sessions.begin() as db:
        run = db.get(PaperRun, "run-test")
        run.state = run.state | {"review_expires_at": (now - timedelta(seconds=1)).isoformat()}
    monkeypatch.setattr(worker, "utcnow", lambda: now)
    result = worker.check(sessions, Settings(_env_file=None), "run-test")
    assert not result["entry_review_current"]


def test_invalid_private_configuration_is_not_echoed_to_logs(monkeypatch, capsys):
    import pytest

    monkeypatch.setattr(sys, "argv", ["worker", "--run-id", "run-test", "--check"])
    monkeypatch.setattr(
        worker, "get_settings", lambda: (_ for _ in ()).throw(ValueError("PRIVATE-CREDENTIAL"))
    )
    with pytest.raises(SystemExit):
        worker.main()
    assert "PRIVATE-CREDENTIAL" not in capsys.readouterr().err
