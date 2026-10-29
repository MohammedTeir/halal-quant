"""Download an auditable IEX daily equity snapshot using backend-only credentials."""

import argparse
from datetime import date
from pathlib import Path

from packages.config.settings import get_settings
from services.market_data.csv_data import load_csv
from services.market_data.providers.alpaca import AlpacaDaily, AlpacaError, save_snapshot
from services.market_data.sessions import Schedule, audit_sessions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--asset-class", choices=("stock", "etf"), required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--adjustment", choices=("split", "raw"), default="split")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Snapshot directory exists; preserve previous acquisitions")
    try:
        settings = get_settings()
        adapter = AlpacaDaily(settings.alpaca_api_key, settings.alpaca_secret_key)
        snapshot = adapter.fetch(
            args.symbol, args.asset_class, args.start, args.end, adjustment=args.adjustment
        )
        save_snapshot(args.output, snapshot)
        dataset = load_csv(
            args.output / "bars.csv",
            args.output / "metadata.json",
            allow_raw_for_audit=args.adjustment == "raw",
        )
        schedule = Schedule.model_validate(snapshot["schedule"])
        result = audit_sessions(dataset, schedule, dataset.spec.retrieved_at)
        if not result["consistent"]:
            parser.exit(
                1, "Snapshot saved but session completeness failed; inspect the source files\n"
            )
    except AlpacaError as error:
        parser.exit(1, str(error) + "\n")
    except (ValueError, OSError):
        parser.exit(
            1, "Acquisition validation failed; preserve any saved source files for review\n"
        )
    print(
        "Snapshot saved and session-consistent; IEX coverage and corporate-action verification remain limited"
    )


if __name__ == "__main__":
    main()
