"""Public XAUUSD bid-quote history; fixed EST, no DST, no reported volume.

The normal free download form is used. No project secret is sent to this site.
Only complete UTC buckets are emitted; missing minutes are never filled.
"""

import calendar
import csv
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import httpx
import numpy as np
import pandas as pd

from services.market_data.csv_data import DataSpec, load_csv

ROOT = "https://www.histdata.com"
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_CSV = 64 * 1024 * 1024
EST = timezone(timedelta(hours=-5))


class HistDataError(RuntimeError):
    pass


class DownloadForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active, self.fields = False, {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form":
            self.active = values.get("id") == "file_down"
            if self.active and (
                values.get("action") != "/get.php" or values.get("method", "").upper() != "POST"
            ):
                raise HistDataError("HISTDATA_FORM_REJECTED")
        elif self.active and tag == "input" and values.get("type") == "hidden":
            name = values.get("name")
            if name in self.fields:
                raise HistDataError("HISTDATA_FORM_REJECTED")
            self.fields[name] = values.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.active = False


def download_month(year, month, *, transport=None):
    now = datetime.now(UTC)
    if (
        not 2000 <= year <= now.year
        or not 1 <= month <= 12
        or (year, month) >= (now.year, now.month)
    ):
        raise ValueError("A completed historical month is required")
    url = f"{ROOT}/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/XAUUSD/{year}/{month}"
    try:
        with httpx.Client(
            timeout=40, verify=True, trust_env=True, follow_redirects=False, transport=transport
        ) as client:
            response = client.get(url)
            if response.status_code != 200 or len(response.content) > 2 * 1024 * 1024:
                raise HistDataError("HISTDATA_PAGE_REJECTED")
            parser = DownloadForm()
            parser.feed(response.text)
            expected = {
                "date": str(year),
                "datemonth": f"{year}{month:02}",
                "platform": "ASCII",
                "timeframe": "M1",
                "fxpair": "XAUUSD",
            }
            if (
                set(parser.fields) != set(expected) | {"tk"}
                or any(parser.fields.get(k) != v for k, v in expected.items())
                or not parser.fields["tk"]
            ):
                raise HistDataError("HISTDATA_FORM_REJECTED")
            with client.stream(
                "POST", ROOT + "/get.php", data=parser.fields, headers={"Referer": url}
            ) as archive:
                if archive.status_code != 200:
                    raise HistDataError("HISTDATA_DOWNLOAD_REJECTED")
                content = bytearray()
                for chunk in archive.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_ARCHIVE:
                        raise HistDataError("HISTDATA_ARCHIVE_TOO_LARGE")
        return bytes(content), url, datetime.now(UTC)
    except httpx.HTTPError:
        raise HistDataError("HISTDATA_UNAVAILABLE") from None


def convert_archive(raw, year, month, seconds):
    if seconds not in (3600, 14400) or len(raw) > MAX_ARCHIVE:
        raise ValueError("Only 1h/4h bounded historical archives are supported")
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            expected = f"DAT_ASCII_XAUUSD_M1_{year}{month:02}.csv"
            entries = [
                entry for entry in archive.infolist() if entry.filename.lower().endswith(".csv")
            ]
            if (
                len(entries) != 1
                or entries[0].filename != expected
                or entries[0].file_size > MAX_CSV
                or entries[0].flag_bits & 1
            ):
                raise ValueError("Unexpected ZIP member or size")
            with archive.open(entries[0]) as member:
                data = member.read(MAX_CSV + 1)
            if len(data) > MAX_CSV:
                raise ValueError("Expanded CSV too large")
        frame = pd.read_csv(
            io.BytesIO(data),
            sep=";",
            header=None,
            names=["stamp", "Open", "High", "Low", "Close", "Volume"],
        )
        if len(frame) > calendar.monthrange(year, month)[1] * 1440 or frame.isna().any().any():
            raise ValueError("Invalid monthly minute file")
        stamps = [datetime.strptime(value, "%Y%m%d %H%M%S") for value in frame.pop("stamp")]
        if any((stamp.year, stamp.month) != (year, month) or stamp.second != 0 for stamp in stamps):
            raise ValueError("Out-of-month or non-minute observation")
        index = pd.DatetimeIndex([stamp.replace(tzinfo=EST).astimezone(UTC) for stamp in stamps])
        if index.has_duplicates or not index.is_monotonic_increasing:
            raise HistDataError("HISTDATA_DUPLICATE_OR_UNORDERED")
        frame.index = index
        frame = frame.apply(pd.to_numeric, errors="raise").astype(float)
        if (
            not np.isfinite(frame.to_numpy()).all()
            or (frame[["Open", "High", "Low", "Close"]] <= 0).any().any()
            or (frame.Volume != 0).any()
            or (frame.Low > frame[["Open", "Close"]].min(axis=1)).any()
            or (frame.High < frame[["Open", "Close"]].max(axis=1)).any()
        ):
            raise ValueError("Invalid bid OHLC or unexpected volume")
        rows, incomplete = [], []
        for bucket, group in frame.groupby(frame.index.floor(f"{seconds}s")):
            expected_index = pd.date_range(bucket, periods=seconds // 60, freq="min")
            if not group.index.equals(expected_index):
                incomplete.append(
                    {
                        "bucket_open": bucket.isoformat(),
                        "observed_minutes": len(group),
                        "required_minutes": seconds // 60,
                    }
                )
                continue
            rows.append(
                [
                    (bucket + pd.Timedelta(seconds=seconds)).isoformat(),
                    group.Open.iloc[0],
                    group.High.max(),
                    group.Low.min(),
                    group.Close.iloc[-1],
                    0,
                ]
            )
        if len(rows) < 3:
            raise ValueError("Insufficient complete buckets")
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["timestamp", "Open", "High", "Low", "Close", "Volume"])
        writer.writerows(rows)
        gaps = int((index.to_series().diff().dropna() > pd.Timedelta(minutes=1)).sum())
        return output.getvalue(), {
            "minute_rows": len(frame),
            "complete_bars": len(rows),
            "incomplete_buckets": incomplete,
            "minute_gap_count": gaps,
            "missing_minute_slots_between_observations": int(
                (index.to_series().diff().dropna().dt.total_seconds() / 60 - 1).clip(lower=0).sum()
            ),
            "maximum_observed_gap_minutes": float(
                index.to_series().diff().dropna().dt.total_seconds().max() / 60
            ),
            "session_coverage_verified": False,
            "missing_minutes_filled": False,
            "timezone": "fixed EST (UTC-05:00), no DST",
            "volume_available": False,
        }
    except (ValueError, TypeError, BadZipFile, KeyError, OverflowError):
        raise HistDataError("HISTDATA_INVALID_ARCHIVE") from None


def save_month(path: Path, raw, year, month, received, source_url):
    path.mkdir(parents=True, exist_ok=False)
    (path / "source.zip").write_bytes(raw)
    manifest = {
        "source_url": source_url,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "received_at": received.isoformat(),
        "quote_basis": "bid",
        "volume_available": False,
        "provider_independently_verified": False,
        "session_coverage_verified": False,
        "authorized_for_entry": False,
        "datasets": {},
    }
    for seconds in (3600, 14400):
        text, audit = convert_archive(raw, year, month, seconds)
        label = "1h" if seconds == 3600 else "4h"
        spec = DataSpec(
            source="histdata_xauusd_bid",
            symbol="XAUUSD",
            asset_class="gold",
            timeframe_seconds=seconds,
            price_basis="unadjusted",
            retrieved_at=received,
            quote_basis="bid",
            volume_semantics="unavailable_zero_placeholder",
        )
        (path / f"{label}.csv").write_text(text)
        (path / f"{label}.metadata.json").write_text(spec.model_dump_json(indent=2) + "\n")
        dataset = load_csv(path / f"{label}.csv", path / f"{label}.metadata.json")
        manifest["datasets"][label] = {"dataset": dataset.manifest(), "audit": audit}
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
