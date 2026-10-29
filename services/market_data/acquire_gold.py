"""Acquire free HistData XAUUSD bid history with explicit missing-volume semantics."""

import argparse
from pathlib import Path

from services.market_data.providers.histdata import HistDataError, download_month, save_month


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; retain prior source archives")
    try:
        raw, url, received = download_month(args.year, args.month)
        manifest = save_month(args.output, raw, args.year, args.month, received, url)
    except HistDataError as error:
        parser.exit(1, str(error) + "\n")
    except (ValueError, OSError):
        parser.exit(1, "Gold acquisition/validation failed; retain partial archives\n")
    print(
        "Validated XAUUSD bid datasets:",
        {label: item["audit"]["complete_bars"] for label, item in manifest["datasets"].items()},
    )


if __name__ == "__main__":
    main()
