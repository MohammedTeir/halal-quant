import json
import threading
from datetime import UTC, datetime

import httpx
import pytest
from dotenv import dotenv_values
from pydantic import SecretStr

from packages.config.settings import Settings
from packages.schemas.control_operations import MethodologyApproval
from services.paper import prepare, sources
from services.paper.schemas import ForwardProtocol, OpenAccount

NOW = datetime(2026, 12, 30, 15, tzinfo=UTC)


def test_preparation_is_pending_hash_bound_idempotent_and_does_not_invent_screening(tmp_path):
    folder = tmp_path / "setup"
    first = prepare.prepare(folder, NOW)
    assert prepare.prepare(folder) == first
    body = OpenAccount.model_validate_json((folder / "account.json").read_text())
    method = MethodologyApproval.model_validate_json(
        (folder / "methodology-proposal.json").read_text()
    )
    protocol = ForwardProtocol.model_validate_json((folder / "protocol.json").read_text())
    assert len(body.universe) == 10
    assert method.status == "PENDING"
    assert method.evidence.document_sha256 == first["review.md"]
    assert set(protocol.data_review.values()) == {first["review.md"]}
    assert not (folder / "assets.json").exists()
    (folder / "account.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        prepare.prepare(folder)


def test_source_configuration_preserves_secrets_and_rejects_conflicts_before_writing(
    tmp_path, monkeypatch
):
    env = tmp_path / ".env"
    env.write_text("DATABASE_URL=PRIVATE-DB\nTELEGRAM_BOT_TOKEN=PRIVATE-TOKEN\n")
    settings = Settings(finnhub_api_key=SecretStr("existing"), _env_file=None)
    monkeypatch.setattr(prepare, "get_settings", lambda: settings)
    # Production cache reset is irrelevant to these isolated settings.
    prepare.get_settings.cache_clear = lambda: None
    for key in sources.PROVIDERS:
        monkeypatch.delenv(key, raising=False)
    prepare.configure(env, prompt=lambda *_: pytest.fail("Existing key must not be requested"))
    values = dotenv_values(env)
    assert values["DATABASE_URL"] == "PRIVATE-DB"
    assert values["TELEGRAM_BOT_TOKEN"] == "PRIVATE-TOKEN"
    assert all(values[k] == v for k, v in sources.PROVIDERS.items())
    monkeypatch.setenv("NEWS_PROVIDER", "another-source")
    before = env.read_bytes()
    with pytest.raises(ValueError, match="differs"):
        prepare.configure(env)
    assert env.read_bytes() == before


def test_plan_covers_every_symbol_and_year_boundary_without_broker_order_modules(tmp_path):
    folder = tmp_path / "setup"
    prepare.prepare(folder, NOW)
    account = OpenAccount.model_validate_json((folder / "account.json").read_text())
    plan = sources.jobs(account, NOW)
    assert len(plan) == 33
    assert {args[-1] for _, module, args in plan if module.endswith("acquire_fomc")} == {
        "2026",
        "2027",
    }
    assert sum(module.endswith("acquire_news") for _, module, _ in plan) == 10
    assert sum(module.endswith("acquire_earnings") for _, module, _ in plan) == 10
    assert sum(module.endswith("acquire_actions") for _, module, _ in plan) == 10
    assert all("worker" not in module and "controls" not in module for _, module, _ in plan)


def test_poll_failure_is_not_hidden_by_other_successful_sources_and_archives_are_unique(tmp_path):
    account = OpenAccount(account_id="a", mode="forward", universe={"AAPL": "technology"})
    stop = threading.Event()

    def run(command, event):
        assert event is stop
        assert "--archive" in command
        return not command[2].endswith("acquire_actions")

    first = sources.poll(account, tmp_path, stop, run=run, now=NOW)
    second = sources.poll(account, tmp_path, stop, run=run, now=NOW)
    assert first["status"] == second["status"] == "INCOMPLETE"
    assert first["results"][-1] == {"source": "actions-AAPL", "status": "FAILED"}
    assert len(list(tmp_path.glob("*/summary.json"))) == 2
    assert json.loads((tmp_path / "latest.json").read_text())["orders_submitted"] == 0


def test_local_source_lock_prevents_setup_poll_from_overlapping_a_worker(tmp_path):
    import fcntl

    account = OpenAccount(account_id="a", mode="forward", universe={"AAPL": "technology"})
    with (tmp_path / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            sources.single_poll(account, tmp_path)
    assert not (tmp_path / "latest.json").exists()


@pytest.mark.parametrize("role", ["operator", "admin"])
def test_submit_uses_only_login_proposals_logout_and_never_approves(role, tmp_path):
    prepare.prepare(tmp_path / "setup", NOW)
    paths = []

    def handler(request):
        assert request.url.host == "example.test"
        paths.append(request.url.path)
        if request.url.path.endswith("login"):
            return httpx.Response(200, json={"user": {"role": role}, "csrf": "test-csrf"})
        assert request.headers["X-CSRF-Token"] == "test-csrf"
        assert "review" not in request.url.path and "orders" not in request.url.path
        return httpx.Response(200, json={"account_id": "a", "status": "PENDING_REVIEW"})

    if role == "operator":
        result = prepare.submit(
            tmp_path / "setup",
            "https://example.test",
            "operator@test",
            "secret",
            transport=httpx.MockTransport(handler),
        )
        assert result["status"] == "PROPOSED_PENDING_REVIEW"
        assert len(paths) == 4
    else:
        with pytest.raises(ValueError, match="operator login"):
            prepare.submit(
                tmp_path / "setup",
                "https://example.test",
                "admin@test",
                "secret",
                transport=httpx.MockTransport(handler),
            )
        assert len(paths) == 2
    assert paths[-1].endswith("logout")


@pytest.fixture
def api_overrides():
    return {
        "paper_trading_enabled": True,
        "paper_forward_enabled": True,
        "session_cookie_secure": False,
    }


def test_proposal_submission_against_real_api_is_pending_idempotent_and_logs_out(client, tmp_path):
    from sqlalchemy import func, select
    from sqlalchemy.orm import sessionmaker

    from services.accounts.access import password_hash
    from services.notifications.models import AccessSession, User
    from services.paper.models import PaperAccount, PaperRun

    sessions = sessionmaker(client.app.state.engine)
    with sessions.begin() as db:
        db.add(
            User(
                id="setup-operator",
                email="setup@example.test",
                password=password_hash("Setup-Password-123456"),
                role="operator",
                enabled=True,
            )
        )
    folder = tmp_path / "setup"
    prepare.prepare(folder)

    def handler(request):
        return client.request(
            request.method, str(request.url), headers=dict(request.headers), content=request.content
        )

    transport = httpx.MockTransport(handler)
    for _ in range(2):
        result = prepare.submit(
            folder,
            "https://testserver",
            "setup@example.test",
            "Setup-Password-123456",
            transport=transport,
        )
        assert result["status"] == "PROPOSED_PENDING_REVIEW"
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(PaperAccount)) == 1
        run = db.scalar(select(PaperRun))
        assert run.state["status"] == "PENDING_REVIEW"
        assert run.state["reviewed_by"] is None
        assert db.scalar(select(func.count()).select_from(AccessSession)) == 0


def test_non_private_terminal_never_falls_back_to_echoing_a_secret(monkeypatch):
    import warnings

    def fallback(*_):
        warnings.warn("Cannot hide input", prepare.getpass.GetPassWarning)
        pytest.fail("Fallback input must never run")

    monkeypatch.setattr(prepare.getpass, "getpass", fallback)
    with pytest.raises(ValueError, match="private interactive"):
        prepare.hidden("Secret: ")


def test_archive_budget_prevents_new_provider_calls_without_deleting_evidence(tmp_path):
    marker = tmp_path / "old-evidence"
    with marker.open("wb") as output:
        output.truncate(512 * 1024 * 1024)
    account = OpenAccount(account_id="a", mode="forward", universe={"AAPL": "technology"})
    with pytest.raises(ValueError, match="budget"):
        sources.poll(
            account,
            tmp_path,
            threading.Event(),
            run=lambda *_: pytest.fail("No calls over budget"),
            now=NOW,
        )
    assert marker.stat().st_size == 512 * 1024 * 1024


def test_shutdown_does_not_start_remaining_source_jobs(tmp_path):
    stop = threading.Event()
    calls = []

    def run(command, _):
        calls.append(command)
        stop.set()
        return False

    account = OpenAccount(account_id="a", mode="forward", universe={"AAPL": "technology"})
    result = sources.poll(account, tmp_path, stop, run=run, now=NOW)
    assert result["status"] == "INCOMPLETE"
    assert len(calls) == 1
