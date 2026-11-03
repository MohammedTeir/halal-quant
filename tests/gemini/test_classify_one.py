import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from apps.api.db import Base, ClassificationRecord, GenerationJob
from packages.config.settings import Settings
from packages.schemas.data_events import DataBatch, NewsEvent
from services.market_data.event_store import import_batch
from services.news_intelligence.classify_one import classify_one
from services.news_intelligence.generation import generate_classification
from services.news_intelligence.providers.gemini import Completion, GeminiError
from tests.decision.test_classification import assessment

NOW = datetime(2026, 11, 3, 8, tzinfo=UTC)


@pytest.fixture
def environment(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'one.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        gemini_enabled=True,
        gemini_model="gemini-test",
        gemini_api_key="PRIVATE-KEY",
        _env_file=None,
    )
    yield sessions, settings
    engine.dispose()


def seed(sessions, *, received=NOW - timedelta(minutes=1), **changes):
    event = NewsEvent(
        **(
            {
                "provider": "finnhub",
                "item_id": "one",
                "published_at": NOW - timedelta(hours=1),
                "source_name": "Fixture publisher",
                "url": "https://example.org/news",
                "headline": "Example revenue increased during the quarter",
                "symbols": ["NVDA"],
                "asset_classes": ["stock"],
                "synthetic": False,
            }
            | changes
        )
    )
    with sessions.begin() as db:
        import_batch(
            db,
            DataBatch(
                provider="finnhub",
                kind="news",
                batch_id="seed",
                records=[event],
                synthetic=event.synthetic,
            ),
            received,
        )


def run(environment, **kwargs):
    sessions, settings = environment
    return classify_one(
        sessions,
        settings,
        symbol="NVDA",
        classification_id="fixed-job",
        clock=lambda: NOW,
        **kwargs,
    )


def test_preview_reads_source_without_creating_job_or_calling_model(environment):
    sessions, _ = environment
    seed(sessions)
    result = run(environment, generator=lambda *_: pytest.fail("Preview called model"))
    assert result["status"] == "READY_FOR_GENERATION"
    assert not result["authorized"] and result["advisory_only"]
    assert "PRIVATE-KEY" not in json.dumps(result)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(GenerationJob)) == 0
        assert db.scalar(select(func.count()).select_from(ClassificationRecord)) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"synthetic": True},
        {"symbols": ["OTHER"]},
        {"asset_classes": ["etf"]},
        {"published_at": NOW - timedelta(days=2)},
        {"received": NOW - timedelta(days=2), "published_at": NOW - timedelta(days=3)},
        {"received": NOW + timedelta(minutes=1)},
    ],
)
def test_unsuitable_or_future_news_never_calls_model(environment, changes):
    seed(environment[0], **changes)
    result = run(environment, generate=True, generator=lambda *_: pytest.fail("Model called"))
    assert result["status"] == "RECENT_NON_SYNTHETIC_COMPANY_NEWS_REQUIRED"


@pytest.mark.parametrize("invalid_quote", [False, True])
def test_generation_uses_grounding_and_never_restarts_existing_job(environment, invalid_quote):
    sessions, _ = environment
    seed(sessions)
    calls = []

    def generator(sessions, request, settings, clock):
        calls.append(request)
        output = assessment(
            event_id=request.source_id,
            source_ids=[request.source_id],
            symbol="NVDA",
            asset_class="stock",
            evidence=[
                {
                    "source_id": request.source_id,
                    "quote": "Unrelated fabricated quotation"
                    if invalid_quote
                    else "Example revenue increased during the quarter",
                }
            ],
        )
        adapter = SimpleNamespace(
            complete=lambda _: Completion(json.dumps(output), "gemini-test-001", {})
        )
        return generate_classification(
            sessions, request, settings, clock, adapter_factory=lambda _: adapter
        )

    first = run(environment, generate=True, generator=generator)
    assert first["status"] == ("GENERATION_FAILED" if invalid_quote else "SUCCEEDED")
    again = run(environment, generate=True, generator=generator)
    assert again["existing_job"] and not again["new_generation_requested"]
    assert again["status"] == ("FAILED" if invalid_quote else "SUCCEEDED")
    assert len(calls) == 1
    assert first["orders_submitted"] == first["messages_sent"] == 0
    assert not first["authorized"]
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ClassificationRecord)) == (
            0 if invalid_quote else 1
        )


def test_provider_failure_keeps_fixed_failed_job_without_new_generation(environment):
    seed(environment[0])

    def generator(sessions, request, settings, clock):
        def fail(_):
            raise GeminiError("GEMINI_RATE_LIMITED")

        return generate_classification(
            sessions,
            request,
            settings,
            clock,
            adapter_factory=lambda _: SimpleNamespace(complete=fail),
        )

    first = run(environment, generate=True, generator=generator)
    assert first["error_code"] == "GEMINI_RATE_LIMITED"
    again = run(environment, generate=True, generator=lambda *_: pytest.fail("Restarted model"))
    assert again["status"] == "FAILED" and again["existing_job"]


def test_ambiguous_interruption_leaves_running_job_and_is_not_recalled(environment):
    seed(environment[0])

    def generator(sessions, request, settings, clock):
        def interrupted(_):
            raise OSError("Ambiguous failure after request delivery")

        return generate_classification(
            sessions,
            request,
            settings,
            clock,
            adapter_factory=lambda _: SimpleNamespace(complete=interrupted),
        )

    with pytest.raises(OSError):
        run(environment, generate=True, generator=generator)
    again = run(environment, generate=True, generator=lambda *_: pytest.fail("Restarted model"))
    assert again["status"] == "RUNNING" and again["existing_job"]


def test_cli_does_not_print_private_settings_errors(monkeypatch, capsys):
    from services.news_intelligence import classify_one as module

    monkeypatch.setattr(
        "sys.argv", ["classify_one", "--symbol", "NVDA", "--classification-id", "fixed-job"]
    )
    monkeypatch.setattr(
        module, "get_settings", lambda: (_ for _ in ()).throw(ValueError("PRIVATE-KEY"))
    )
    module.main()
    output = capsys.readouterr().out
    assert "PRIVATE-KEY" not in output
    assert json.loads(output)["status"] == "PRIVATE_CONFIGURATION_OR_DATABASE_UNAVAILABLE"
