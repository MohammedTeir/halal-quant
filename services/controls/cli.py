"""Evaluate hypothetical controls offline; never stores authority or places orders."""

import argparse
import json
from pathlib import Path

from packages.schemas.controls import ControlScenario
from services.controls.engine import preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        scenario = ControlScenario.model_validate_json(args.scenario.read_bytes())
        result = preview(scenario)
        # Retain exact hypothetical inputs for reproducibility; never load them as authorities.
        result["scenario"] = scenario.model_dump(mode="json")
        encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as f:
            f.write(encoded)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    parser.exit(0 if result["status"] == "SIMULATION_PASS" else 1)


if __name__ == "__main__":
    main()
