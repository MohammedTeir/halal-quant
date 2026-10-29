import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from services.market_data.gold_sessions import compare_minutes, reference_schedule
from services.market_data.sessions import Schedule, Session


def schedule():
    return Schedule(
        source="https://example.invalid/reference",
        venue="REFERENCE_ONLY",
        symbol="XAUUSD",
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        coverage_start=datetime(2025, 1, 1, tzinfo=UTC),
        coverage_end=datetime(2025, 1, 1, 0, 10, tzinfo=UTC),
        sessions=[
            Session(
                opens_at=datetime(2025, 1, 1, 0, 2, tzinfo=UTC),
                closes_at=datetime(2025, 1, 1, 0, 8, tzinfo=UTC),
            )
        ],
    )


def test_comparison_accounts_for_both_boundaries_and_never_certifies_reference():
    observed = pd.DatetimeIndex(
        [
            "2025-01-01T00:01:00Z",
            "2025-01-01T00:02:00Z",
            "2025-01-01T00:04:00Z",
            "2025-01-01T00:07:00Z",
        ]
    )
    report = compare_minutes(observed, schedule())
    assert report["observed_minutes"] == 4 and report["missing_minutes"] == 6
    assert report["missing_during_reference_open_minutes"] == 3
    assert report["missing_during_reference_closed_minutes"] == 3
    assert report["observed_during_reference_closed_minutes"] == 1
    assert report["gaps"][0]["starts_at"] == "2025-01-01T00:00:00+00:00"
    assert report["gaps"][-1]["ends_at_exclusive"] == "2025-01-01T00:10:00+00:00"
    assert all(not gap["verified_market_closure"] for gap in report["gaps"])
    assert not report["session_coverage_verified"] and not report["authorized_for_entry"]
    assert json.loads(json.dumps(report)) == report


@pytest.mark.parametrize(
    "values",
    [
        ["2025-01-01T00:02:00"],
        ["2025-01-01T00:02:00Z", "2025-01-01T00:02:00Z"],
        ["2025-01-01T00:03:00Z", "2025-01-01T00:02:00Z"],
        ["2025-01-01T00:02:01Z"],
        ["2024-12-31T23:59:00Z"],
    ],
)
def test_bad_minute_timestamps_are_rejected(values):
    with pytest.raises(ValueError):
        compare_minutes(pd.DatetimeIndex(values), schedule())


def test_reference_rule_uses_new_york_dst_and_does_not_open_on_saturday():
    received = datetime(2026, 1, 1, tzinfo=UTC)
    start = datetime(2025, 3, 8, tzinfo=UTC)
    end = datetime(2025, 3, 11, tzinfo=UTC)
    march = reference_schedule(start, end, received)
    assert march.sessions[0].opens_at == datetime(2025, 3, 9, 22, 5, tzinfo=UTC)
    fall = reference_schedule(
        datetime(2025, 11, 1, tzinfo=UTC), datetime(2025, 11, 4, tzinfo=UTC), received
    )
    assert fall.sessions[0].opens_at == datetime(2025, 11, 2, 23, 5, tzinfo=UTC)


def test_snapshot_must_actually_contain_the_exact_reviewed_gold_rule():
    from services.market_data.gold_sessions import verify_reference_rule

    raw = b"<table><tr><td>XAU/USD</td><td>USD</td><td>New York</td><td>100</td><td>Sun-Fri: 18:05 - 16:59</td></tr></table>"
    assert verify_reference_rule(raw) == "XAU/USD USD New York 100 Sun-Fri: 18:05 - 16:59"
    for changed in [
        raw.replace(b"18:05", b"17:05"),
        raw.replace(b"New York", b"UTC"),
        b"18:05 - 16:59",
        raw + raw,
    ]:
        with pytest.raises(ValueError, match="reference rule"):
            verify_reference_rule(changed)


def test_reference_acquisition_is_exclusive_and_records_verified_snapshot(tmp_path):
    import httpx

    from services.market_data.gold_sessions import acquire_reference

    raw = b"<table><tr><td>XAU/USD</td><td>USD</td><td>New York</td><td>100</td><td>Sun-Fri: 18:05 - 16:59</td></tr></table>"
    calls = []

    def handle(request):
        assert request.url.host == "www.oanda.com" and request.method == "GET"
        calls.append(request)
        return httpx.Response(200, content=raw)

    output = tmp_path / "evidence"
    result = acquire_reference(output, transport=httpx.MockTransport(handle))
    assert (output / "oanda-hours.html").read_bytes() == raw
    assert result[0]["verified_rule_excerpt"].startswith("XAU/USD")
    with pytest.raises(FileExistsError):
        acquire_reference(output, transport=httpx.MockTransport(handle))
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,raw", [(302, b""), (200, b"<table><tr><td>XAU/USD changed hours</td></tr></table>")]
)
def test_reference_acquisition_does_not_follow_redirects_or_accept_changed_hours(
    tmp_path, status, raw
):
    import httpx

    from services.market_data.gold_sessions import acquire_reference

    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, content=raw, headers={"Location": "https://other.invalid"})

    with pytest.raises(ValueError):
        acquire_reference(tmp_path / "evidence", transport=httpx.MockTransport(handle))
    assert len(calls) == 1
    assert not (tmp_path / "evidence/manifest.json").exists()
