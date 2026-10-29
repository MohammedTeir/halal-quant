"""Point-in-time target coverage: a fresh company poll cannot cover another target."""

from datetime import timedelta

from sqlalchemy import or_, select

from apps.api.db import DataImport, FeedCoverageRecord
from services.market_data.event_store import aware


def coverage_status(
    session,
    provider,
    symbol,
    asset_class,
    purpose,
    as_of,
    window_start,
    window_end,
    maximum_age=timedelta(minutes=15),
):
    if (
        any(stamp.tzinfo is None for stamp in (as_of, window_start, window_end))
        or window_start >= window_end
        or maximum_age <= timedelta(0)
    ):
        raise ValueError("Aware increasing coverage window and positive freshness required")
    row = session.execute(
        select(FeedCoverageRecord, DataImport)
        .join(DataImport, DataImport.id == FeedCoverageRecord.import_id)
        .where(
            DataImport.provider == provider,
            DataImport.received_at <= as_of,
            or_(FeedCoverageRecord.symbol == symbol, FeedCoverageRecord.symbol == "*"),
            FeedCoverageRecord.asset_class == asset_class,
            FeedCoverageRecord.purpose == purpose,
        )
        .order_by(DataImport.received_at.desc(), DataImport.id.desc())
        .limit(1)
    ).first()
    coverage, poll = row if row else (None, None)
    # Always assess the latest matching poll. A reduced scope cannot borrow an older wide poll.
    age = (as_of - aware(poll.received_at)).total_seconds() if poll else None
    fresh = age is not None and 0 <= age <= maximum_age.total_seconds()
    complete_window = bool(
        coverage
        and aware(coverage.starts_at) <= window_start
        and aware(coverage.ends_at) >= window_end
    )
    return {
        "provider": provider,
        "symbol": symbol,
        "asset_class": asset_class,
        "purpose": purpose,
        "as_of": as_of.isoformat(),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "state": "MISSING"
        if poll is None
        else "STALE"
        if not fresh
        else "INCOMPLETE_WINDOW"
        if not complete_window
        else "FRESH",
        "last_successful_at": aware(poll.received_at).isoformat() if poll else None,
        "coverage_start": aware(coverage.starts_at).isoformat() if coverage else None,
        "coverage_end": aware(coverage.ends_at).isoformat() if coverage else None,
        "required_feed_available": bool(fresh and complete_window and not poll.synthetic),
        "synthetic": poll.synthetic if poll else None,
        "provider_independently_verified": False,
        "authorized_for_entry": False,
    }
