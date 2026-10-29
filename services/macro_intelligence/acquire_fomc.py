"""Archive and atomically ingest the official FOMC calendar without inventing release times."""

import argparse
import json
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from packages.config.settings import get_settings
from services.macro_intelligence.fomc import FomcError, coverage_window, fetch_calendar
from services.market_data.acquire_news import persist_poll


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    if args.archive.exists():
        parser.error("Archive exists; retain historical observations")
    engine = None
    try:
        raw, events, now = fetch_calendar(args.year)
        args.archive.mkdir(parents=True, exist_ok=False)
        (args.archive / "source.html").write_bytes(raw)
        (args.archive / "observations.json").write_text(
            json.dumps([event.model_dump(mode="json") for event in events], indent=2) + "\n"
        )
        engine = create_engine(get_settings().database_url)
        result = persist_poll(
            engine,
            events,
            now,
            str(uuid.uuid4()),
            provider="federal_reserve",
            kind="calendar",
            coverage=coverage_window(args.year),
        )
        (args.archive / "import-result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
    except FomcError as error:
        parser.exit(1, str(error) + "\n")
    except (ValueError, OSError, SQLAlchemyError):
        parser.exit(1, "FOMC acquisition/import failed; preserve archives\n")
    finally:
        if engine is not None:
            engine.dispose()
    print("Official FOMC calendar imported as conservative date-only observations")


if __name__ == "__main__":
    main()
