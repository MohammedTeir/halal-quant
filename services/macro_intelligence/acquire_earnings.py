"""Archive and atomically import conservatively timed company earnings observations."""

import argparse
import json
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from packages.config.settings import get_settings
from services.macro_intelligence.earnings import FinnhubEarnings, coverage_window
from services.market_data.acquire_news import persist_poll
from services.news_intelligence.providers.finnhub import FinnhubError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    if args.archive.exists():
        parser.error("Archive exists; retain prior earnings observations")
    engine = None
    try:
        settings = get_settings()
        raw, events, now = FinnhubEarnings(settings.finnhub_api_key).fetch(
            args.symbol, args.start, args.end
        )
        args.archive.mkdir(parents=True, exist_ok=False)
        (args.archive / "raw.json").write_bytes(raw)
        for name, value in (
            ("observations.json", [event.model_dump(mode="json") for event in events]),
        ):
            with (args.archive / name).open("x") as output:
                json.dump(value, output, indent=2, sort_keys=True)
                output.write("\n")
        engine = create_engine(settings.database_url)
        result = persist_poll(
            engine,
            events,
            now,
            str(uuid.uuid4()),
            provider="finnhub_earnings",
            kind="calendar",
            coverage=coverage_window(args.symbol, args.start, args.end),
        )
        with (args.archive / "import-result.json").open("x") as output:
            json.dump(result, output, indent=2, sort_keys=True)
            output.write("\n")
    except FinnhubError as error:
        parser.exit(1, str(error) + "\n")
    except (ValueError, OSError, SQLAlchemyError):
        parser.exit(1, "Earnings acquisition/import failed; preserve source archives\n")
    finally:
        if engine is not None:
            engine.dispose()
    print("Earnings imported as date-only observations; whole-date restriction windows apply")


if __name__ == "__main__":
    main()
