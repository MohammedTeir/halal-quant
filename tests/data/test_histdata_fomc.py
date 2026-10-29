import io
from datetime import UTC, datetime, timedelta
from zipfile import ZipFile

import httpx
import pytest

from services.macro_intelligence.fomc import FomcError, parse_calendar
from services.market_data.providers.histdata import HistDataError, convert_archive, download_month

NOW = datetime(2026, 10, 29, tzinfo=UTC)


def archive(minutes=240, *, gap=False, duplicate=False, wrong_name=False, volume=0):
    start = datetime(2025, 9, 1, 3)  # fixed EST 03:00 = UTC 08:00, a 4h boundary
    rows = []
    for i in range(minutes):
        if gap and i == 15:
            continue
        stamp = (start + timedelta(minutes=i)).strftime("%Y%m%d %H%M%S")
        rows.append(f"{stamp};2000;2002;1999;2001;{volume}")
    if duplicate:
        rows.append(rows[-1])
    output = io.BytesIO()
    with ZipFile(output, "w") as z:
        z.writestr(
            "../escape.csv" if wrong_name else "DAT_ASCII_XAUUSD_M1_202509.csv", "\n".join(rows)
        )
    return output.getvalue()


def test_fixed_est_conversion_aggregation_and_zero_volume_are_explicit():
    text, audit = convert_archive(archive(720), 2025, 9, 3600)
    assert text.splitlines()[1].startswith(
        "2025-09-01T09:00:00+00:00,2000.0,2002.0,1999.0,2001.0,0"
    )
    assert audit["complete_bars"] == 12 and not audit["volume_available"]
    assert not audit["missing_minutes_filled"]
    text, audit = convert_archive(archive(720), 2025, 9, 14400)
    assert audit["complete_bars"] == 3 and "2025-09-01T12:00:00+00:00" in text


def test_incomplete_bucket_is_reported_not_filled():
    text, audit = convert_archive(archive(720, gap=True), 2025, 9, 3600)
    assert audit["complete_bars"] == 11 and audit["incomplete_buckets"][0]["observed_minutes"] == 59
    assert "2025-09-01T09:00:00+00:00" not in text


@pytest.mark.parametrize("change", [{"duplicate": True}, {"wrong_name": True}, {"volume": 1}])
def test_bad_gold_archive_rejected(change):
    with pytest.raises(HistDataError):
        convert_archive(archive(720, **change), 2025, 9, 3600)


def test_download_form_never_posts_to_another_host_or_payment_route():
    def handler(request):
        assert request.url.host == "www.histdata.com"
        return httpx.Response(
            200,
            text='<form id="file_down" method="POST" action="https://attacker.invalid/steal"><input type="hidden" name="tk" value="fixture"></form>',
        )

    with pytest.raises(HistDataError, match="FORM_REJECTED"):
        download_month(2025, 9, transport=httpx.MockTransport(handler))


def page(month="October", days="27-28", year=2026):
    return f'<h4><a>{year} FOMC Meetings</a></h4><div class="row fomc-meeting"><div class="fomc-meeting__month"><strong>{month}</strong></div><div class="fomc-meeting__date">{days}</div></div>'.encode()


def test_fomc_actual_markup_date_only_cross_month_and_year_scope():
    events = parse_calendar(
        page() + page("December", "8-9*") + page("January", "27-28", 2025), 2026, NOW
    )
    assert len(events) == 2
    assert events[0].scheduled_at.isoformat() == "2026-10-28T04:00:00+00:00"
    assert events[0].scheduled_precision == "date" and events[0].publication_basis == "observed_at"
    cross = parse_calendar(page("Apr/May", "30-1"), 2026, NOW)[0]
    assert cross.scheduled_at.month == 5 and cross.scheduled_at.day == 1


@pytest.mark.parametrize(
    "raw",
    [
        page("Unknown", "1-2"),
        page("October", "unannounced"),
        page() + page(),
        b"<h4>2026 FOMC Meetings</h4>",
    ],
)
def test_changed_or_ambiguous_calendar_fails_closed(raw):
    with pytest.raises(FomcError):
        parse_calendar(raw, 2026, NOW)


def test_missing_volume_metadata_cannot_label_reported_volume_as_placeholder(
    tmp_path, make_dataset
):
    from services.market_data.csv_data import load_csv
    from tests.backtesting.test_data import files

    dataset = make_dataset(asset="gold", count=10)
    dataset.spec = dataset.spec.model_copy(
        update={"quote_basis": "bid", "volume_semantics": "unavailable_zero_placeholder"}
    )
    csv_path, metadata = files(tmp_path, dataset)
    with pytest.raises(ValueError, match="Unavailable volume"):
        load_csv(csv_path, metadata)
