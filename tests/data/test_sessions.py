from datetime import UTC, datetime

import pandas as pd
import pytest

from services.market_data.csv_data import load_csv
from services.market_data.sessions import Schedule, audit_sessions
from tests.backtesting.test_data import files


def schedule(**changes):
    return Schedule.model_validate(
        {
            "source": "synthetic_schedule",
            "venue": "TEST",
            "symbol": "EXAMPLE",
            "synthetic": True,
            "retrieved_at": "2026-10-28T00:00:00Z",
            "coverage_start": "2024-11-27T00:00:00Z",
            "coverage_end": "2024-12-03T00:00:00Z",
            "sessions": [
                {"opens_at": "2024-11-27T09:30:00-05:00", "closes_at": "2024-11-27T16:00:00-05:00"},
                # Thanksgiving omitted; next day has a shortened session.
                {"opens_at": "2024-11-29T09:30:00-05:00", "closes_at": "2024-11-29T13:00:00-05:00"},
                {"opens_at": "2024-12-02T09:30:00-05:00", "closes_at": "2024-12-02T16:00:00-05:00"},
            ],
        }
        | changes
    )


def dataset(make_dataset, stamps):
    data = make_dataset(count=len(stamps))
    data.bars.index = pd.to_datetime(stamps, utc=True)
    return data


def test_daily_holiday_and_early_close(make_dataset):
    data = dataset(make_dataset, ["2024-11-27T21:00Z", "2024-11-29T18:00Z", "2024-12-02T21:00Z"])
    result = audit_sessions(data, schedule(), datetime(2026, 10, 28, tzinfo=UTC))
    assert result["consistent"] and result["synthetic"]
    assert result["schedule_independently_verified"] is False
    assert result["authorized_for_entry"] is False
    data.bars = data.bars.drop(data.bars.index[1])
    result = audit_sessions(data, schedule(), datetime(2026, 10, 28, tzinfo=UTC))
    assert not result["consistent"]
    assert result["missing_bar_closes"] == ["2024-11-29T18:00:00+00:00"]


def test_off_session_and_dst_conversion(make_dataset):
    sched = schedule(
        coverage_start="2024-03-08T00:00Z",
        coverage_end="2024-03-13T00:00Z",
        sessions=[
            {"opens_at": "2024-03-08T09:30-05:00", "closes_at": "2024-03-08T16:00-05:00"},
            {"opens_at": "2024-03-11T09:30-04:00", "closes_at": "2024-03-11T16:00-04:00"},
            {"opens_at": "2024-03-12T09:30-04:00", "closes_at": "2024-03-12T16:00-04:00"},
        ],
    )
    data = dataset(make_dataset, ["2024-03-08T21:00Z", "2024-03-11T20:00Z", "2024-03-12T20:00Z"])
    assert audit_sessions(data, sched, datetime(2026, 10, 28, tzinfo=UTC))["consistent"]
    data.bars.index = data.bars.index + pd.Timedelta(hours=1)
    assert not audit_sessions(data, sched, datetime(2026, 10, 28, tzinfo=UTC))["consistent"]


def test_intraday_grid_and_no_partial_close(make_dataset):
    data = dataset(make_dataset, ["2024-11-29T15:30Z", "2024-11-29T16:30Z", "2024-11-29T17:30Z"])
    data.spec = data.spec.model_copy(update={"timeframe_seconds": 3600})
    sched = schedule(
        coverage_start="2024-11-29T00:00Z",
        coverage_end="2024-11-30T00:00Z",
        sessions=[schedule().sessions[1]],
    )
    assert audit_sessions(data, sched, datetime(2026, 10, 28, tzinfo=UTC))["consistent"]
    data.bars.index = data.bars.index + pd.Timedelta(minutes=30)
    assert not audit_sessions(data, sched, datetime(2026, 10, 28, tzinfo=UTC))["consistent"]


@pytest.mark.parametrize(
    "change",
    [
        {"symbol": "OTHER"},
        {"coverage_end": "2024-11-28T00:00Z", "sessions": []},
        {"retrieved_at": "2027-01-01T00:00Z"},
    ],
)
def test_unavailable_or_mismatched_schedule_rejected(make_dataset, change):
    data = dataset(make_dataset, ["2024-11-27T21:00Z", "2024-11-29T18:00Z", "2024-12-02T21:00Z"])
    with pytest.raises(ValueError):
        audit_sessions(data, schedule(**change), datetime(2026, 10, 28, tzinfo=UTC))


def test_overlap_and_unknown_fields_rejected():
    value = schedule().model_dump(mode="json")
    value["sessions"].append(value["sessions"][0])
    with pytest.raises(ValueError):
        Schedule.model_validate(value)
    with pytest.raises(ValueError):
        Schedule.model_validate(schedule().model_dump() | {"verified": True})


def test_candle_after_retrieval_rejected(tmp_path, make_dataset):
    data = make_dataset(count=3)
    data.spec = data.spec.model_copy(update={"retrieved_at": datetime(2019, 1, 1, tzinfo=UTC)})
    csv, meta = files(tmp_path, data)
    with pytest.raises(ValueError, match="retrieval"):
        load_csv(csv, meta)


def test_missing_first_or_last_session_is_not_hidden(make_dataset):
    for stamps in (
        ["2024-11-29T18:00Z", "2024-12-02T21:00Z"],
        ["2024-11-27T21:00Z", "2024-11-29T18:00Z"],
    ):
        result = audit_sessions(
            dataset(make_dataset, stamps), schedule(), datetime(2026, 10, 28, tzinfo=UTC)
        )
        assert not result["consistent"] and len(result["missing_bar_closes"]) == 1
