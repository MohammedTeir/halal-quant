import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import httpx
import pytest

from services.news_intelligence.providers.gemini import GeminiAdapter
from tests.decision.test_classification import assessment
from tests.gemini.test_adapter import KEY, envelope
from tests.integration.test_api import DASHBOARD
from tests.integration.test_data_api import T0, get, news, send
from tests.integration.test_decisions_api import ANALYSIS, classification, evaluate, setup_sources


@pytest.fixture
def api_overrides():
    return {"gemini_enabled": True, "gemini_api_key": KEY, "gemini_model": "gemini-test"}


@pytest.fixture
def clock(monkeypatch):
    time = {"now": T0}
    monkeypatch.setattr("apps.api.main.utcnow", lambda: time["now"])
    return time


@pytest.fixture(autouse=True)
def prevent_real_model_calls(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Live HTTP is forbidden in Gemini tests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fail)


def install_mock(client, handler):
    client.app.state.gemini_adapter_factory = lambda cfg: GeminiAdapter(
        cfg, transport=httpx.MockTransport(handler), sleep=lambda _: None
    )


def response_for(request, **changes):
    document = json.loads(json.loads(request.content)["contents"][0]["parts"][0]["text"])
    target = document["target"]
    output = (
        assessment(
            **target,
            evidence=[
                {"source_id": target["event_id"], "quote": document["sources"][0]["headline"]}
            ],
        )
        | changes
    )
    body = envelope()
    body["candidates"][0]["content"]["parts"][0]["text"] = json.dumps(output)
    return httpx.Response(200, json=body)


def generate(client, source_id, classification_id="generated-1", **changes):
    return client.post(
        "/api/v1/news/classifications/generate",
        headers=ANALYSIS,
        json={
            "classification_id": classification_id,
            "source_id": source_id,
            "symbol": "EXAMPLE",
            "asset_class": "stock",
        }
        | changes,
    )


def status(client, identity="generated-1"):
    return get(client, f"/api/v1/news/classification-jobs/{identity}")


def test_generated_assessment_grounding_metadata_replay_and_decision_gate(client, clock):
    source_id, _ = setup_sources(client, clock)
    calls = []

    def handler(request):
        calls.append(request)
        # The RUNNING claim is already committed and observable during inference.
        assert status(client)["status"] == "RUNNING"
        return response_for(request)

    install_mock(client, handler)
    response = generate(client, source_id)
    assert response.status_code == 200
    result = response.json()
    assert result["advisory_only"] and result["synthetic"]
    assert result["prompt_version"] == "news-classification-v5"
    assert (
        result["model_name"] == "gemini/gemini-test"
        and result["model_version"] == "gemini-test-001"
    )
    assert result["generation"]["usage"]["totalTokenCount"] == 50
    assert status(client)["status"] == "SUCCEEDED"
    assert "owner" not in status(client) and KEY not in json.dumps(status(client))
    assert generate(client, source_id).json() == result | {"duplicate": True}
    assert len(calls) == 1
    assert generate(client, source_id, symbol="OTHER").status_code == 409
    decision = evaluate(client).json()
    assert decision["status"] == "WAIT_DATA" and not decision["authorized"]
    assert (
        decision["snapshot"]["intelligence"]["classifications"][0]["model_version"]
        == "gemini-test-001"
    )
    audits = [row["action"] for row in get(client, "/api/v1/audit")["items"]]
    assert audits.count("gemini_generation_started") == 1
    assert audits.count("gemini_generation_succeeded") == 1
    assert audits.count("news_classification_received") == 1


def test_concurrent_request_and_manual_collision_cannot_trigger_duplicate_model_call(client, clock):
    source_id, _ = setup_sources(client, clock)
    entered, release = Event(), Event()
    calls = []

    def handler(request):
        calls.append(request)
        entered.set()
        assert release.wait(10)
        return response_for(request)

    install_mock(client, handler)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(generate, client, source_id)
        assert entered.wait(10)
        try:
            assert generate(client, source_id).status_code == 409
            assert status(client)["status"] == "RUNNING"
            manual = classification(source_id, "generated-1")
            assert (
                client.post(
                    "/api/v1/news/classifications", headers=ANALYSIS, json=manual
                ).status_code
                == 409
            )
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 200
    assert len(calls) == 1 and status(client)["status"] == "SUCCEEDED"


@pytest.mark.parametrize(
    "case", ["invented_quote", "changed_target", "tool", "approval", "source_correction"]
)
def test_invalid_or_superseded_generation_is_failed_not_persisted_or_recalled(client, clock, case):
    source_id, _ = setup_sources(client, clock)
    calls = []

    def handler(request):
        calls.append(request)
        if case == "source_correction":
            clock["now"] += timedelta(seconds=1)
            assert (
                send(
                    client,
                    [
                        news(
                            revision=2,
                            headline="Corrected source",
                            published_at=clock["now"].isoformat(),
                        )
                    ],
                    "new-source",
                ).status_code
                == 200
            )
            return response_for(request)
        if case == "invented_quote":
            return response_for(
                request, evidence=[{"source_id": source_id, "quote": "Invented company results"}]
            )
        if case == "changed_target":
            return response_for(request, symbol="OTHER")
        return response_for(
            request,
            **(
                {"tool_calls": [{"name": "place_order"}]}
                if case == "tool"
                else {"authorized": True}
            ),
        )

    install_mock(client, handler)
    response = generate(client, source_id)
    assert response.status_code == 502 and response.json()["detail"] == "GEMINI_OUTPUT_INVALID"
    job = status(client)
    assert job["status"] == "FAILED" and job["error_code"] == "GEMINI_OUTPUT_INVALID"
    assert job["result_metadata"]["usage"]["totalTokenCount"] == 50
    assert get(client, "/api/v1/news/classifications")["items"] == []
    assert generate(client, source_id).status_code == 409 and len(calls) == 1
    actions = [row["action"] for row in get(client, "/api/v1/audit")["items"]]
    assert actions.count("gemini_generation_failed") == 1
    assert "news_classification_received" not in actions


@pytest.mark.parametrize(
    ("failure", "expected", "calls_expected"),
    [
        ("rate_limit", 503, 2),
        ("timeout", 502, 1),
        ("authentication", 502, 1),
        ("blocked", 502, 1),
    ],
)
def test_upstream_failures_sanitized_and_failed_job_not_retried(
    client, clock, caplog, failure, expected, calls_expected
):
    source_id, _ = setup_sources(client, clock)
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout(KEY, request=request)
        if failure == "blocked":
            return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})
        return httpx.Response(429 if failure == "rate_limit" else 401, text=KEY)

    install_mock(client, handler)
    response = generate(client, source_id)
    assert response.status_code == expected
    assert status(client)["status"] == "FAILED"
    assert generate(client, source_id).status_code == 409
    assert len(calls) == calls_expected
    assert (
        KEY not in response.text
        and KEY not in json.dumps(status(client))
        and KEY not in caplog.text
    )


def test_preflight_scope_stale_sources_unknown_fields_and_auth_never_call_provider(client, clock):
    source_id, _ = setup_sources(client, clock)
    calls = []
    install_mock(client, lambda request: calls.append(request))
    assert generate(client, source_id, symbol="OTHER").status_code == 422
    assert generate(client, "b" * 64).status_code == 422
    for field in [
        {"model": "gemini-other"},
        {"api_key": KEY},
        {"endpoint": "https://attacker.example"},
        {"compliance_status": "APPROVED"},
    ]:
        assert generate(client, source_id, **field).status_code == 422
    assert (
        client.post("/api/v1/news/classifications/generate", headers=DASHBOARD, json={}).status_code
        == 401
    )
    assert (
        client.get("/api/v1/news/classification-jobs/generated-1", headers=ANALYSIS).status_code
        == 401
    )
    assert (
        client.get("/api/v1/news/classification-jobs/missing", headers=DASHBOARD).status_code == 404
    )
    assert send(client, [news(revision=2, headline="Revised")], "revision-2").status_code == 200
    assert generate(client, source_id).status_code == 422
    assert calls == []
    assert (
        client.get("/api/v1/news/classification-jobs/generated-1", headers=DASHBOARD).status_code
        == 404
    )


def test_manual_assessment_id_cannot_be_reused_for_billable_generation(client, clock):
    source_id, _ = setup_sources(client, clock)
    assert (
        client.post(
            "/api/v1/news/classifications",
            headers=ANALYSIS,
            json=classification(source_id, "generated-1"),
        ).status_code
        == 200
    )
    calls = []
    install_mock(client, lambda request: calls.append(request))
    assert generate(client, source_id).status_code == 409 and not calls


def test_crash_remains_running_and_never_automatically_regenerates(client, clock):
    source_id, _ = setup_sources(client, clock)

    def crash(request):
        raise RuntimeError("simulated worker termination")

    install_mock(client, crash)
    with pytest.raises(RuntimeError, match="simulated worker termination"):
        generate(client, source_id)
    assert status(client)["status"] == "RUNNING"
    assert generate(client, source_id).status_code == 409


@pytest.mark.parametrize("enabled", [False, True])
def test_disabled_configuration_does_not_create_jobs(client, clock, enabled):
    # A separate app has the feature disabled, sharing the dedicated test database.
    from fastapi.testclient import TestClient

    from apps.api.main import create_app
    from packages.config.settings import Settings
    from tests.integration.test_data_api import DATA

    app = create_app(
        Settings(
            analysis_api_key="analysis-test",
            dashboard_api_key="dashboard-test",
            data_ingestion_key="data-test",
            gemini_enabled=enabled,
            gemini_api_key="",
            gemini_model="",
            _env_file=None,
        )
    )
    with TestClient(app) as disabled:
        assert send(disabled, [news()], headers=DATA).status_code == 200
        source_id = get(disabled, "/api/v1/news")["items"][0]["observations"][0]["source_id"]
        result = generate(disabled, source_id)
        assert result.status_code == 503 and result.json()["detail"] == (
            "GEMINI_NOT_CONFIGURED" if enabled else "GEMINI_DISABLED"
        )
        assert (
            disabled.get(
                "/api/v1/news/classification-jobs/generated-1", headers=DASHBOARD
            ).status_code
            == 404
        )
    app.state.engine.dispose()


def test_gemini_migration_preserves_assessments_and_lost_completed_job_is_not_recalled(
    client, clock
):
    from alembic import command
    from alembic.config import Config

    source_id, _ = setup_sources(client, clock)
    calls = []

    def handler(request):
        calls.append(request)
        return response_for(request)

    install_mock(client, handler)
    assert generate(client, source_id).status_code == 200
    config = Config("alembic.ini")
    command.downgrade(config, "0003_intelligence")
    assert client.get("/health/ready").status_code == 503
    assert len(get(client, "/api/v1/news/classifications")["items"]) == 1
    assert len(get(client, "/api/v1/signals")["items"]) == 1
    command.upgrade(config, "head")
    command.check(config)
    assert client.get("/health/ready").status_code == 200
    assert generate(client, source_id).status_code == 409
    assert len(calls) == 1
