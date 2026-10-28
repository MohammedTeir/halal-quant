import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.db import AuditRecord, Base, DataImport, NewsRecord
from services.market_data.event_store import feed_status
from services.market_data.worker import MAX_BATCH_BYTES, ingest_file, run_once

NOW = datetime(2026, 10, 28, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def batch(**changes):
    return {
        "provider": "fixture",
        "kind": "news",
        "batch_id": "poll-1",
        "synthetic": True,
        "records": [
            {
                "kind": "news",
                "provider": "fixture",
                "item_id": "story",
                "revision": 1,
                "synthetic": True,
                "published_at": "2026-10-27T12:00Z",
                "source_name": "fixture",
                "url": "https://example.org/story",
                "headline": "Reported revenue increased",
                "symbols": ["EXAMPLE"],
                "asset_classes": ["stock"],
            }
        ],
    } | changes


def test_resume_does_not_refresh_feed_and_keeps_one_audit(tmp_path, store):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    path = inbox / "one.json"
    path.write_text(json.dumps(batch()))
    first = run_once(store, inbox, "fixture", "news", clock=lambda: NOW)
    second = run_once(store, inbox, "fixture", "news", clock=lambda: NOW + timedelta(hours=1))
    assert first["success"] and second["success"]
    assert second["files"][0]["result"]["duplicate"]
    with Session(store) as session:
        assert session.scalar(select(func.count()).select_from(AuditRecord)) == 1
        assert session.scalar(select(func.count()).select_from(NewsRecord)) == 1
        status = feed_status(session, "fixture", "news", NOW + timedelta(hours=1))
        assert status["state"] == "STALE" and not status["required_feed_available"]
    assert path.exists()


def test_failed_batch_does_not_refresh_or_block_other_files(tmp_path, store):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "0.json").write_text('{"provider":"fixture","provider":"other"}')
    (inbox / "1.json").write_text(json.dumps(batch()))
    result = run_once(store, inbox, "fixture", "news", clock=lambda: NOW)
    assert not result["success"]
    assert [row["status"] for row in result["files"]] == ["FAILED", "IMPORTED"]
    with Session(store) as session:
        assert session.scalar(select(func.count()).select_from(DataImport)) == 1
    with pytest.raises(ValueError, match="exceeds limit"):
        run_once(store, inbox, "fixture", "news", limit=1)


def test_conflict_future_publication_and_scope_fail_atomic(tmp_path, store):
    path = tmp_path / "batch.json"
    path.write_text(json.dumps(batch()))
    ingest_file(store, path, "fixture", "news", clock=lambda: NOW)
    value = batch()
    value["records"][0]["headline"] = "Changed without a new revision"
    path.write_text(json.dumps(value))
    result = run_once(store, tmp_path, "fixture", "news", clock=lambda: NOW)
    assert result["files"][0]["code"] == "IMMUTABLE_CONFLICT"
    value["batch_id"] = "future"
    value["records"][0]["revision"] = 2
    value["records"][0]["published_at"] = "2027-01-01T00:00Z"
    path.write_text(json.dumps(value))
    assert (
        run_once(store, tmp_path, "fixture", "news", clock=lambda: NOW)["files"][0]["code"]
        == "INVALID_BATCH"
    )
    with pytest.raises(ValueError, match="configured"):
        ingest_file(store, path, "other", "news", clock=lambda: NOW)
    path.write_bytes(b"x" * (MAX_BATCH_BYTES + 1))
    with pytest.raises(ValueError, match="4 MiB"):
        ingest_file(store, path, "fixture", "news", clock=lambda: NOW)
    with Session(store) as session:
        assert session.scalar(select(func.count()).select_from(DataImport)) == 1
