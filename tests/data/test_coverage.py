from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.db import Base, FeedCoverageRecord
from packages.schemas.data_events import DataBatch, FeedCoverage
from services.market_data.coverage import coverage_status
from services.market_data.event_store import import_batch

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


@pytest.fixture
def sessions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'coverage.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def scoped_batch(batch_id="poll-1", **changes):
    coverage = FeedCoverage(
        symbols=["AAPL"],
        asset_classes=["stock"],
        purpose="company_news",
        starts_at=NOW - timedelta(days=1),
        ends_at=NOW + timedelta(days=1),
    )
    return DataBatch(
        provider="fixture", kind="news", batch_id=batch_id, coverage=coverage, **changes
    )


def status(session, **changes):
    return coverage_status(
        session,
        **(
            {
                "provider": "fixture",
                "symbol": "AAPL",
                "asset_class": "stock",
                "purpose": "company_news",
                "as_of": NOW,
                "window_start": NOW - timedelta(hours=2),
                "window_end": NOW,
            }
            | changes
        ),
    )


def test_target_purpose_and_asset_never_borrow_another_poll(sessions):
    with Session(sessions) as session, session.begin():
        import_batch(session, scoped_batch(), NOW)
        assert status(session)["required_feed_available"]
        for changes in (
            {"symbol": "OTHER"},
            {"asset_class": "gold"},
            {"purpose": "earnings"},
            {"provider": "other"},
        ):
            result = status(session, **changes)
            assert result["state"] == "MISSING" and not result["required_feed_available"]
        assert not status(session)["provider_independently_verified"]
        assert not status(session)["authorized_for_entry"]


def test_replay_cannot_refresh_and_future_receipts_cannot_leak(sessions):
    with Session(sessions) as session, session.begin():
        import_batch(session, scoped_batch(), NOW)
        import_batch(session, scoped_batch(), NOW + timedelta(hours=1))
        assert status(session, as_of=NOW - timedelta(seconds=1))["state"] == "MISSING"
        assert status(session, as_of=NOW + timedelta(hours=1))["state"] == "STALE"
        assert session.scalar(select(func.count()).select_from(FeedCoverageRecord)) == 1


def test_latest_reduced_window_cannot_borrow_older_broad_poll(sessions):
    with Session(sessions) as session, session.begin():
        import_batch(session, scoped_batch(), NOW)
        narrow = scoped_batch("poll-2").model_copy(
            update={
                "coverage": FeedCoverage(
                    symbols=["AAPL"],
                    asset_classes=["stock"],
                    purpose="company_news",
                    starts_at=NOW - timedelta(minutes=30),
                    ends_at=NOW + timedelta(minutes=30),
                )
            }
        )
        import_batch(session, narrow, NOW + timedelta(seconds=1))
        result = status(session, as_of=NOW + timedelta(seconds=2))
        assert result["state"] == "INCOMPLETE_WINDOW" and not result["required_feed_available"]


def test_synthetic_and_legacy_unscoped_polls_cannot_supply_target_coverage(sessions):
    with Session(sessions) as session, session.begin():
        import_batch(session, DataBatch(provider="fixture", kind="news", batch_id="legacy"), NOW)
        assert status(session)["state"] == "MISSING"
        import_batch(session, scoped_batch(synthetic=True), NOW)
        assert (
            status(session)["state"] == "FRESH" and not status(session)["required_feed_available"]
        )


def test_macro_wildcard_is_only_for_requested_purpose(sessions):
    with Session(sessions) as session, session.begin():
        batch = DataBatch(
            provider="fixture",
            kind="calendar",
            batch_id="macro",
            coverage=FeedCoverage(
                symbols=[],
                asset_classes=["stock", "gold"],
                purpose="macro_releases",
                starts_at=NOW - timedelta(days=1),
                ends_at=NOW + timedelta(days=1),
            ),
        )
        import_batch(session, batch, NOW)
        assert status(session, purpose="macro_releases", asset_class="gold")[
            "required_feed_available"
        ]
        assert status(session, purpose="earnings")["state"] == "MISSING"
        assert status(session, purpose="macro_releases", asset_class="etf")["state"] == "MISSING"


@pytest.mark.parametrize(
    "change",
    [{"symbols": []}, {"asset_classes": ["stock", "stock"]}, {"ends_at": NOW - timedelta(days=2)}],
)
def test_invalid_coverage_rejected(change):
    with pytest.raises(ValueError):
        FeedCoverage.model_validate(scoped_batch().coverage.model_dump() | change)


def test_wrong_kind_and_out_of_scope_fact_rejected():
    batch = scoped_batch().model_dump(mode="json")
    with pytest.raises(ValueError):
        DataBatch.model_validate(batch | {"kind": "calendar"})
    batch["records"] = [
        {
            "kind": "news",
            "provider": "fixture",
            "item_id": "bad",
            "published_at": NOW.isoformat(),
            "source_name": "Fixture",
            "url": "https://example.org/story",
            "headline": "Revenue increased",
            "symbols": ["OTHER"],
            "asset_classes": ["stock"],
        }
    ]
    with pytest.raises(ValueError, match="outside"):
        DataBatch.model_validate(batch)


def test_coverage_offsets_normalize_before_sqlite_storage(sessions):
    coverage = FeedCoverage(
        symbols=["AAPL"],
        asset_classes=["stock"],
        purpose="company_news",
        starts_at="2026-10-28T00:00:00-04:00",
        ends_at="2026-10-29T00:00:00-04:00",
    )
    batch = DataBatch(provider="fixture", kind="news", batch_id="offset", coverage=coverage)
    with Session(sessions) as session, session.begin():
        import_batch(session, batch, NOW)
        invalid = status(
            session,
            window_start=datetime(2026, 10, 28, 2, tzinfo=UTC),
            window_end=datetime(2026, 10, 29, 2, tzinfo=UTC),
        )
        valid = status(
            session,
            window_start=datetime(2026, 10, 28, 4, tzinfo=UTC),
            window_end=datetime(2026, 10, 29, 4, tzinfo=UTC),
        )
        assert invalid["state"] == "INCOMPLETE_WINDOW"
        assert valid["state"] == "FRESH"
