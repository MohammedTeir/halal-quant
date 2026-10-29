"""Archive and atomically ingest official BLS release schedules (no API key)."""

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from packages.config.settings import get_settings
from services.macro_intelligence.bls import BlsError, fetch_calendar
from services.market_data.acquire_news import persist_poll


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    args = parser.parse_args()
    if args.archive.exists():
        parser.error("Archive exists; preserve previous source polls")
    engine = None
    try:
        raw, events = fetch_calendar()
        received = datetime.now(UTC)
        args.archive.mkdir(parents=True, exist_ok=False)
        (args.archive / "source.ics").write_bytes(raw)
        poll_id = str(uuid.uuid4())
        with (args.archive / "observations.json").open("x") as output:
            json.dump(
                {
                    "poll_id": poll_id,
                    "received_at": received.isoformat(),
                    "source_stamp_semantics": "iCalendar LAST-MODIFIED/DTSTAMP when available; otherwise first observed time with publication_basis=observed_at; source publication is unknown",
                    "events": [event.model_dump(mode="json") for event in events],
                },
                output,
                indent=2,
                sort_keys=True,
            )
            output.write("\n")
        engine = create_engine(get_settings().database_url)
        result = persist_poll(engine, events, received, poll_id, provider="bls", kind="calendar")
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
    print("BLS schedule imported; FOMC/company earnings coverage is not supplied by this feed")


if __name__ == "__main__":
    main()
