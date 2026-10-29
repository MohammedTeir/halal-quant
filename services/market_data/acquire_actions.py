"""Archive and atomically ingest observed Alpaca splits/dividends; never backdate receipts."""

import argparse
import json
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from packages.config.settings import get_settings
from packages.schemas.data_events import FeedCoverage
from services.market_data.acquire_news import persist_poll
from services.market_data.providers.actions import AlpacaActions
from services.market_data.providers.alpaca import AlpacaError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("start", "end"):
        parser.add_argument(f"--{name}", type=date.fromisoformat, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--asset-class", choices=("stock", "etf"), default="stock")
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    if args.archive.exists():
        parser.error("Archive exists; preserve previous action observations")
    engine = None
    try:
        settings = get_settings()
        pages, records, now = AlpacaActions(
            settings.alpaca_api_key, settings.alpaca_secret_key
        ).acquire(args.symbol, args.start, args.end)
        args.archive.mkdir(parents=True, exist_ok=False)
        for name, value in (
            ("raw.json", pages),
            (
                "observations.json",
                [
                    {"action": record.model_dump(mode="json"), "received_at": now.isoformat()}
                    for record in records
                ],
            ),
        ):
            with (args.archive / name).open("x") as output:
                json.dump(value, output, indent=2, sort_keys=True)
                output.write("\n")
        engine = create_engine(settings.database_url)
        result = persist_poll(
            engine,
            records,
            now,
            str(uuid.uuid4()),
            provider="alpaca_iex",
            kind="corporate_actions",
            coverage=FeedCoverage(
                symbols=[args.symbol],
                asset_classes=[args.asset_class],
                purpose="corporate_actions",
                starts_at=datetime.combine(args.start, time.min, ZoneInfo("America/New_York")),
                ends_at=datetime.combine(
                    args.end + timedelta(days=1), time.min, ZoneInfo("America/New_York")
                ),
            ),
        )
        with (args.archive / "import-result.json").open("x") as output:
            json.dump(result, output, indent=2, sort_keys=True)
            output.write("\n")
    except AlpacaError as error:
        parser.exit(1, str(error) + "\n")
    except (ValueError, OSError, SQLAlchemyError):
        parser.exit(1, "Action acquisition/import failed; preserve the archive for review\n")
    finally:
        if engine is not None:
            engine.dispose()
    print(
        "Actions imported with observed-time provenance; upstream completeness remains unverified"
    )


if __name__ == "__main__":
    main()
