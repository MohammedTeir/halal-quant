"""Audit raw versus split-adjusted snapshots using an explicit action ledger."""

import argparse
import json
from pathlib import Path

from pydantic import AwareDatetime, TypeAdapter

from packages.schemas.data_events import ActionObservation
from services.market_data.corporate_actions import verify_split_adjustments
from services.market_data.csv_data import load_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "raw-csv",
        "raw-metadata",
        "adjusted-csv",
        "adjusted-metadata",
        "actions",
        "output",
    ):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; preserve prior audits with a new output path")
    try:
        raw = load_csv(args.raw_csv, args.raw_metadata, allow_raw_for_audit=True)
        adjusted = load_csv(args.adjusted_csv, args.adjusted_metadata)
        observations = TypeAdapter(list[ActionObservation]).validate_json(args.actions.read_text())
        cutoff = TypeAdapter(AwareDatetime).validate_python(args.as_of)
        result = verify_split_adjustments(raw, adjusted, observations, cutoff)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
    if not result["consistent"]:
        parser.exit(1, "FAIL: snapshots do not match the known split ledger; audit report saved\n")
    print(
        "PASS: split arithmetic and declared volume basis match; provider authenticity remains unverified"
    )


if __name__ == "__main__":
    main()
