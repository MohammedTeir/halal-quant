"""Validate daily/intraday candles against an explicitly sourced exchange schedule.

Schedules are supplied by the operator/provider, never inferred from weekdays.
This checks consistency, not the authenticity/completeness of the schedule itself.
"""

from datetime import UTC, datetime, timedelta

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from services.market_data.csv_data import Dataset
from services.market_data.event_store import digest


class Session(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    opens_at: AwareDatetime
    closes_at: AwareDatetime

    @model_validator(mode="after")
    def chronological(self):
        if self.opens_at >= self.closes_at:
            raise ValueError("Session open must precede close")
        return self


class Schedule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: str = Field(min_length=1, max_length=200)
    venue: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=64)
    retrieved_at: AwareDatetime
    coverage_start: AwareDatetime
    coverage_end: AwareDatetime
    synthetic: bool = False
    sessions: list[Session] = Field(max_length=100000)

    @model_validator(mode="after")
    def ordered(self):
        if self.coverage_start >= self.coverage_end:
            raise ValueError("Invalid schedule coverage")
        previous = None
        for session in self.sessions:
            if not self.coverage_start <= session.opens_at < session.closes_at <= self.coverage_end:
                raise ValueError("Session outside declared coverage")
            if previous is not None and session.opens_at < previous:
                raise ValueError("Schedule sessions must be ordered and cannot overlap")
            previous = session.closes_at
        return self


def audit_sessions(dataset: Dataset, schedule: Schedule, as_of: datetime):
    """Daily bars close at the session close; intraday bars cover complete intervals.

    No partial last bars, extended-hours candles or weekly aggregation are implied.
    Coverage is explicit, so missing holiday sessions cannot silently become weekdays.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if dataset.spec.symbol != schedule.symbol:
        raise ValueError("Schedule symbol mismatch")
    if dataset.spec.retrieved_at > as_of or schedule.retrieved_at > as_of:
        raise ValueError("Snapshots were unavailable at as_of")
    if schedule.coverage_end > dataset.spec.retrieved_at:
        raise ValueError("Schedule coverage must end before snapshot retrieval")
    seconds = dataset.spec.timeframe_seconds
    if seconds > 86400:
        raise ValueError("Weekly/session aggregation requires a separate audited schedule")
    first, last = dataset.bars.index[0].to_pydatetime(), dataset.bars.index[-1].to_pydatetime()
    if not schedule.coverage_start < first <= last <= schedule.coverage_end:
        raise ValueError("Schedule does not cover the candle window")
    expected = set()
    for session in schedule.sessions:
        if seconds == 86400:
            closes = [session.closes_at]
        else:
            opening = session.opens_at.astimezone(UTC)
            closing = session.closes_at.astimezone(UTC)
            count = int((closing - opening).total_seconds() // seconds)
            closes = [opening + timedelta(seconds=seconds * i) for i in range(1, count + 1)]
        expected.update(close.astimezone(UTC) for close in closes)
    actual = {stamp.to_pydatetime().astimezone(UTC) for stamp in dataset.bars.index}
    missing, unexpected = sorted(expected - actual), sorted(actual - expected)
    return {
        "consistent": not missing and not unexpected,
        "venue": schedule.venue,
        "symbol": schedule.symbol,
        "as_of": as_of.astimezone(UTC).isoformat(),
        "schedule_sha256": digest(schedule.model_dump(mode="json")),
        "dataset": dataset.manifest(),
        "missing_bar_closes": [stamp.isoformat() for stamp in missing],
        "unexpected_bar_closes": [stamp.isoformat() for stamp in unexpected],
        "synthetic": dataset.spec.synthetic or schedule.synthetic,
        "schedule_independently_verified": False,
        "authorized_for_entry": False,
    }
