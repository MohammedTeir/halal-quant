import hashlib
import json
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.db import Base, DataImport, EconomicRecord, FeedCoverageRecord
from services.macro_intelligence import acquire_bls
from services.macro_intelligence.bls import MAX_BYTES

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:browser-cpi
DTSTAMP:20261001T120000Z
DTSTART;TZID=US-Eastern:20261110T083000
SUMMARY:Consumer Price Index
END:VEVENT
END:VCALENDAR
"""


def arguments(monkeypatch, source, archive):
    monkeypatch.setattr(
        sys,
        "argv",
        ["acquire_bls", "--input-file", str(source), "--archive", str(archive)],
    )
    monkeypatch.setattr(
        acquire_bls,
        "fetch_calendar",
        lambda: pytest.fail("File import must not make a network request"),
    )


def test_downloaded_file_is_separate_and_does_not_create_automatic_coverage(
    tmp_path, monkeypatch, capsys
):
    source, archive = tmp_path / "private-download-name.ics", tmp_path / "archive"
    source.write_bytes(ICS)
    url = f"sqlite:///{tmp_path / 'facts.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(acquire_bls, "get_settings", lambda: SimpleNamespace(database_url=url))
    arguments(monkeypatch, source, archive)
    try:
        acquire_bls.main()
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(EconomicRecord)) == 1
            event = db.scalar(select(EconomicRecord))
            assert event.provider == "bls_manual_file"
            assert event.payload["scheduled_at"] == "2026-11-10T13:30:00Z"
            assert db.scalar(select(func.count()).select_from(FeedCoverageRecord)) == 0
            assert db.scalar(select(DataImport)).provider == "bls_manual_file"
        receipt = json.loads((archive / "observations.json").read_text())
        assert receipt["acquisition"]["file_sha256"] == hashlib.sha256(ICS).hexdigest()
        assert receipt["acquisition"]["source_url_basis"] == (
            "operator_assertion_not_independently_verified"
        )
        assert receipt["acquisition"]["downloaded_at"] is None
        assert not receipt["acquisition"]["automated_feed_coverage"]
        assert (archive / "source.ics").read_bytes() == ICS
        assert source.name not in (archive / "observations.json").read_text()
        assert "automated BLS coverage was not refreshed" in capsys.readouterr().out
    finally:
        engine.dispose()


@pytest.mark.parametrize("raw", [b"<html>Access denied</html>", b"x" * (MAX_BYTES + 1)])
def test_invalid_or_oversized_file_fails_before_database_access(tmp_path, monkeypatch, raw):
    source, archive = tmp_path / "download.ics", tmp_path / "archive"
    source.write_bytes(raw)
    arguments(monkeypatch, source, archive)
    monkeypatch.setattr(
        acquire_bls, "create_engine", lambda *_: pytest.fail("No DB access for invalid input")
    )
    with pytest.raises(SystemExit) as error:
        acquire_bls.main()
    assert error.value.code == 1
    assert not archive.exists()


def test_existing_archive_is_preserved_before_reading_file(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "preserve").write_text("prior evidence")
    arguments(monkeypatch, tmp_path / "missing.ics", archive)
    with pytest.raises(SystemExit) as error:
        acquire_bls.main()
    assert error.value.code == 2
    assert (archive / "preserve").read_text() == "prior evidence"


def test_direct_fetch_retains_automatic_provider_and_coverage(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from services.macro_intelligence.bls import parse_calendar

    archive = tmp_path / "direct"
    url = f"sqlite:///{tmp_path / 'direct.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(acquire_bls, "get_settings", lambda: SimpleNamespace(database_url=url))
    monkeypatch.setattr(sys, "argv", ["acquire_bls", "--archive", str(archive)])
    monkeypatch.setattr(
        acquire_bls,
        "fetch_calendar",
        lambda: (ICS, parse_calendar(ICS, received_at=datetime.now(UTC))),
    )
    try:
        acquire_bls.main()
        with Session(engine) as db:
            assert db.scalar(select(EconomicRecord)).provider == "bls"
            assert db.scalar(select(DataImport)).provider == "bls"
            assert db.scalar(select(func.count()).select_from(FeedCoverageRecord)) == 3
        receipt = json.loads((archive / "observations.json").read_text())
        assert receipt["acquisition"]["method"] == "direct_https"
        assert receipt["acquisition"]["source_url_basis"] == "fixed_adapter_endpoint"
    finally:
        engine.dispose()
