from unittest.mock import Mock

from packages.config.settings import Settings
from services.paper import preflight
from services.paper.models import PaperRun


def test_inventory_is_read_only_and_reports_missing_private_flags(forward_env):
    sessions, *_ = forward_env
    with sessions() as db:
        before = dict(db.get(PaperRun, "run-test").state)
    result = preflight.inspect(
        sessions, Settings(alpaca_api_key="", alpaca_secret_key="", _env_file=None)
    )
    assert result["status"] == "BLOCKED"
    assert "FORWARD_FLAGS_DISABLED" in result["blockers"]
    assert "ALPACA_NOT_CONFIGURED" in result["blockers"]
    assert result["enabled_roles"] == {"operator": 1, "reviewer": 1}
    assert result["mutations"] == result["provider_calls"] == result["messages_sent"] == 0
    with sessions() as db:
        assert db.get(PaperRun, "run-test").state == before


def test_missing_database_binding_does_not_attempt_default_connection(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "get_settings", lambda: Settings(_env_file=None))
    factory = Mock(side_effect=AssertionError("Must not connect to a default database"))
    monkeypatch.setattr(preflight, "session_factory", factory)
    preflight.main()
    assert "DATABASE_URL_NOT_CONFIGURED" in capsys.readouterr().out
    factory.assert_not_called()


def test_private_configuration_errors_are_sanitized(monkeypatch, capsys):
    monkeypatch.setattr(
        preflight, "get_settings", lambda: (_ for _ in ()).throw(ValueError("PRIVATE-SECRET"))
    )
    preflight.main()
    output = capsys.readouterr().out
    assert "PRIVATE-SECRET" not in output
    assert "PRIVATE_CONFIGURATION_OR_DATABASE_UNAVAILABLE" in output
