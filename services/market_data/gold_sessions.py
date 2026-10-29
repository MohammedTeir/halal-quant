"""Compare retained gold minute observations with explicitly scoped session evidence.

The OANDA CFD schedule is only a diagnostic reference for HistData. It cannot
certify HistData's undisclosed venue, historical holidays, or Shariah suitability.
"""

import argparse
import hashlib
import io
import json
from datetime import UTC, datetime, time, timedelta
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import pandas as pd

from services.market_data.providers.histdata import EST
from services.market_data.sessions import Schedule, Session
from services.market_data.validate_gold_history import audit_history

NY = ZoneInfo("America/New_York")
REFERENCE_URL = "https://www.oanda.com/bvi-en/cfds/hours-of-operation/"


class _TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active, self.parts, self.rows = False, [], []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.active, self.parts = True, []

    def handle_endtag(self, tag):
        if tag == "tr" and self.active:
            self.rows.append(" ".join(" ".join(self.parts).split()))
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def verify_reference_rule(raw):
    parser = _TableRows()
    parser.feed(raw.decode("utf-8", errors="replace"))
    rows = [row for row in parser.rows if "XAU/USD" in row]
    expected = "XAU/USD USD New York 100 Sun-Fri: 18:05 - 16:59"
    if rows != [expected]:
        raise ValueError("Unsupported/changed XAU/USD reference rule; review the source snapshot")
    return expected


def acquire_reference(output, *, transport=None):
    output.mkdir(parents=True, exist_ok=False)
    with (
        httpx.Client(
            timeout=30, verify=True, trust_env=True, follow_redirects=False, transport=transport
        ) as client,
        client.stream("GET", REFERENCE_URL) as response,
    ):
        if response.status_code != 200:
            raise ValueError("Reference source unavailable; no redirect/retry was attempted")
        raw = bytearray()
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("Reference snapshot exceeds 2MB")
    raw = bytes(raw)
    # Preserve changed source material for review, even when the rule is rejected.
    (output / "oanda-hours.html").write_bytes(raw)
    excerpt = verify_reference_rule(raw)
    evidence = [
        {
            "id": "oanda-hours",
            "url": REFERENCE_URL,
            "status": 200,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "received_at": datetime.now(UTC).isoformat(),
            "verified_rule_excerpt": excerpt,
        }
    ]
    (output / "manifest.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def reference_schedule(start, end, retrieved_at):
    """Published regular Sun–Fri 18:05–16:59 New York rule; holidays unknown."""
    sessions = []
    day = start.astimezone(NY).date() - timedelta(days=1)
    last = end.astimezone(NY).date()
    while day <= last:
        if day.weekday() in (6, 0, 1, 2, 3):
            opens = datetime.combine(day, time(18, 5), NY).astimezone(UTC)
            closes = datetime.combine(day + timedelta(days=1), time(16, 59), NY).astimezone(UTC)
            opens, closes = max(opens, start), min(closes, end)
            if opens < closes:
                sessions.append(Session(opens_at=opens, closes_at=closes))
        day += timedelta(days=1)
    return Schedule(
        source=REFERENCE_URL,
        venue="OANDA_BVI_METALS_CFD_REFERENCE_ONLY",
        symbol="XAUUSD",
        retrieved_at=retrieved_at,
        coverage_start=start,
        coverage_end=end,
        sessions=sessions,
    )


def _runs(mask):
    edges = np.diff(np.r_[False, mask, False].astype(int))
    return zip(
        np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist(), strict=True
    )


def compare_minutes(observed, schedule):
    observed = pd.DatetimeIndex(observed)
    if (
        observed.tz is None
        or observed.hasnans
        or observed.has_duplicates
        or not observed.is_monotonic_increasing
    ):
        raise ValueError("Observed minutes must be aware, unique and ordered")
    observed = observed.tz_convert("UTC")
    if not observed.equals(observed.floor("min")):
        raise ValueError("Minute-open timestamps are required")
    start = pd.Timestamp(schedule.coverage_start).tz_convert("UTC")
    end = pd.Timestamp(schedule.coverage_end).tz_convert("UTC")
    if start != start.floor("min") or end != end.floor("min"):
        raise ValueError("Minute-aligned coverage required")
    if len(observed) == 0 or observed[0] < start or observed[-1] >= end:
        raise ValueError("Observed minutes outside declared coverage")
    grid = pd.date_range(start, end, freq="min", inclusive="left")
    if len(grid) > 600000:
        raise ValueError("Limit the comparison to one calendar year")
    expected = np.zeros(len(grid), dtype=bool)
    for session in schedule.sessions:
        if (
            session.opens_at.second
            or session.opens_at.microsecond
            or session.closes_at.second
            or session.closes_at.microsecond
        ):
            raise ValueError("Minute-aligned sessions required")
        expected[grid.searchsorted(session.opens_at) : grid.searchsorted(session.closes_at)] = True
    actual = grid.isin(observed)
    gaps = []
    for a, b in _runs(~actual):
        open_count = int(expected[a:b].sum())
        closed_count = b - a - open_count
        gaps.append(
            {
                "starts_at": grid[a].isoformat(),
                "ends_at_exclusive": (grid[b - 1] + pd.Timedelta(minutes=1)).isoformat(),
                "missing_minutes": b - a,
                "reference_open_minutes": open_count,
                "reference_closed_minutes": closed_count,
                "comparison": "reference_closed_only"
                if not open_count
                else "reference_open_only"
                if not closed_count
                else "mixed_reference_open_and_closed",
                "verified_market_closure": False,
            }
        )
    outside = [
        {
            "starts_at": grid[a].isoformat(),
            "ends_at_exclusive": (grid[b - 1] + pd.Timedelta(minutes=1)).isoformat(),
            "minutes": b - a,
        }
        for a, b in _runs(actual & ~expected)
    ]
    return {
        "coverage_start": start.isoformat(),
        "coverage_end_exclusive": end.isoformat(),
        "minute_interval_semantics": "[open, close), exact published minute; boundary precision unverified",
        "observed_minutes": int(actual.sum()),
        "missing_minutes": int((~actual).sum()),
        "missing_during_reference_open_minutes": int((~actual & expected).sum()),
        "missing_during_reference_closed_minutes": int((~actual & ~expected).sum()),
        "observed_during_reference_closed_minutes": int((actual & ~expected).sum()),
        "gap_count": len(gaps),
        "gaps": gaps,
        "observations_outside_reference": outside,
        "schedule_venue": schedule.venue,
        "reference_source": schedule.source,
        "provider_venue_binding_verified": False,
        "historical_holiday_schedule_verified": False,
        "session_coverage_verified": False,
        "authorized_for_entry": False,
    }


def audit_year(root, year, evidence_dir):
    structural = audit_history(root, year)
    if not structural["structural_history_pass"]:
        raise ValueError("First pass the complete-year structural/source-artifact audit")
    evidence = json.loads((evidence_dir / "manifest.json").read_bytes())
    source = next(item for item in evidence if item["id"] == "oanda-hours")
    raw = (evidence_dir / "oanda-hours.html").read_bytes()
    if source["status"] != 200 or hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError("Reference source hash/status mismatch")
    excerpt = verify_reference_rule(raw)
    received = datetime.fromisoformat(source["received_at"])
    frames = []
    for month in range(1, 13):
        with ZipFile(root / f"{year}-{month:02}" / "source.zip") as z:
            data = z.read(f"DAT_ASCII_XAUUSD_M1_{year}{month:02}.csv")
        # Structural audit already checked source bounds, OHLC and exact duplicate proof.
        stamps = pd.read_csv(io.BytesIO(data), sep=";", header=None, usecols=[0])[0]
        frame = (
            pd.to_datetime(stamps, format="%Y%m%d %H%M%S").dt.tz_localize(EST).dt.tz_convert("UTC")
        )
        frames.extend(frame.drop_duplicates().tolist())
    start = datetime(year, 1, 1, tzinfo=EST).astimezone(UTC)
    end = datetime(year + 1, 1, 1, tzinfo=EST).astimezone(UTC)
    schedule = reference_schedule(start, end, received)
    report = compare_minutes(pd.DatetimeIndex(frames), schedule)
    report["structural_audit"] = structural
    report["reference_evidence"] = source
    report["verified_reference_rule_excerpt"] = excerpt
    report["reference_schedule_sha256"] = hashlib.sha256(
        schedule.model_dump_json().encode()
    ).hexdigest()
    report["assessment"] = "COMPARISON_ONLY_NOT_PROVIDER_SESSION_CERTIFICATION"
    report["limitations"] = [
        "HistData does not establish that OANDA is its quote venue; no same-source binding",
        "OANDA page observed in 2026 does not establish 2025 historical effective hours/holidays",
        "CFD reference hours do not approve CFD instruments, custody or Shariah compliance",
        "Missing quotes during reference-open time may be holidays or low quote activity; not automatically data loss",
        "Reference-closed gaps are not certified closures of the HistData source",
        "Boundary minute precision is unverified; no tolerance or filling hides mismatches",
    ]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("acquire-reference")
    fetch.add_argument("--output", required=True, type=Path)
    compare = commands.add_parser("compare")
    compare.add_argument("--root", required=True, type=Path)
    compare.add_argument("--year", required=True, type=int)
    compare.add_argument("--evidence", required=True, type=Path)
    compare.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "acquire-reference":
            acquire_reference(args.output)
            parser.exit(0)
        result = audit_year(args.root, args.year, args.evidence)
        encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
        with args.output.open("x") as f:
            f.write(encoded)
    except (ValueError, OSError, KeyError, StopIteration, httpx.HTTPError) as error:
        parser.error(str(error))
    # The command records comparison evidence and never signals certified acceptance.
    parser.exit(1)


if __name__ == "__main__":
    main()
