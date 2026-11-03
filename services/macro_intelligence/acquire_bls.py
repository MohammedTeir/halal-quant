"""Archive and atomically ingest official BLS release schedules (no API key)."""

import argparse
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from packages.config.settings import get_settings
from packages.schemas.data_events import FeedCoverage
from services.macro_intelligence.bls import MAX_BYTES, URL, BlsError, fetch_calendar, parse_calendar
from services.market_data.acquire_news import persist_poll


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument(
        "--input-file",
        type=Path,
        help="Import an operator-downloaded calendar separately, without automated feed coverage",
    )
    args = parser.parse_args()
    if args.archive.exists():
        parser.error("Archive exists; preserve previous source polls")
    engine = None
    try:
        if args.input_file:
            with args.input_file.open("rb") as source:
                raw = source.read(MAX_BYTES + 1)
            received = datetime.now(UTC)
            events = [
                event.model_copy(update={"provider": "bls_manual_file"})
                for event in parse_calendar(raw, received_at=received)
            ]
            provider = "bls_manual_file"
        else:
            raw, events = fetch_calendar()
            received = datetime.now(UTC)
            provider = "bls"
        args.archive.mkdir(parents=True, exist_ok=False)
        (args.archive / "source.ics").write_bytes(raw)
        poll_id = str(uuid.uuid4())
        with (args.archive / "observations.json").open("x") as output:
            json.dump(
                {
                    "poll_id": poll_id,
                    "received_at": received.isoformat(),
                    "acquisition": {
                        "method": "operator_supplied_file" if args.input_file else "direct_https",
                        "source_url": URL,
                        "source_url_basis": "operator_assertion_not_independently_verified"
                        if args.input_file
                        else "fixed_adapter_endpoint",
                        "downloaded_at": None,
                        "file_sha256": hashlib.sha256(raw).hexdigest(),
                        "automated_feed_coverage": not bool(args.input_file),
                    },
                    "source_stamp_semantics": "iCalendar LAST-MODIFIED/DTSTAMP when available; otherwise first observed time with publication_basis=observed_at; source publication is unknown",
                    "events": [event.model_dump(mode="json") for event in events],
                },
                output,
                indent=2,
                sort_keys=True,
            )
            output.write("\n")
        engine = create_engine(get_settings().database_url)
        result = persist_poll(
            engine,
            events,
            received,
            poll_id,
            provider=provider,
            kind="calendar",
            coverage=None
            if args.input_file
            else FeedCoverage(
                symbols=[],
                asset_classes=["stock", "etf", "gold"],
                purpose="macro_releases",
                starts_at=min(event.scheduled_at for event in events),
                ends_at=max(event.scheduled_at for event in events) + timedelta(seconds=1),
            ),
        )
        with (args.archive / "import-result.json").open("x") as output:
            json.dump(result, output, sort_keys=True, indent=2)
            output.write("\n")
    except BlsError as error:
        parser.exit(1, str(error) + "\n")
    except (ValueError, OSError, SQLAlchemyError):
        parser.exit(1, "Calendar acquisition/import failed; preserve the archive for review\n")
    finally:
        if engine is not None:
            engine.dispose()
    if args.input_file:
        print(
            "Calendar file imported as bls_manual_file; source origin/download time unverified; "
            "automated BLS coverage was not refreshed"
        )
    else:
        print("BLS schedule imported; FOMC/company earnings coverage is not supplied by this feed")


if __name__ == "__main__":
    main()
