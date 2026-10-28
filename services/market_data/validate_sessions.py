"""Audit candle timestamps/completeness against a provider's explicit session schedule."""

import argparse
import json
from pathlib import Path

from pydantic import AwareDatetime, TypeAdapter

from services.market_data.csv_data import load_csv
from services.market_data.sessions import Schedule, audit_sessions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("csv", "metadata", "schedule", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; choose a new audit path")
    try:
        result = audit_sessions(
            load_csv(args.csv, args.metadata),
            Schedule.model_validate_json(args.schedule.read_bytes()),
            TypeAdapter(AwareDatetime).validate_python(args.as_of),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as output:
            json.dump(result, output, sort_keys=True, indent=2, allow_nan=False)
            output.write("\n")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    parser.exit(0 if result["consistent"] else 1)


if __name__ == "__main__":
    main()
