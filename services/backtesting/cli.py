"""Run: python -m services.backtesting.cli --help."""

import argparse
import json
from pathlib import Path

from services.backtesting.engine import RunConfig, research
from services.market_data.csv_data import load_csv
from services.technical_signals.strategies import StrategyConfig, defaults


def main():
    parser = argparse.ArgumentParser(
        description="Reproducible technical research; no order authorization"
    )
    parser.add_argument(
        "--strategy",
        required=True,
        choices=["adaptive_pullback", "regime_trend", "breakout_retest"],
    )
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--benchmark-csv", type=Path)
    parser.add_argument("--benchmark-metadata", type=Path)
    parser.add_argument(
        "--strategy-config", type=Path, help="Full/partial StrategyConfig JSON including name"
    )
    parser.add_argument(
        "--run-config", type=Path, help="RunConfig JSON; costs, split and allocation"
    )
    parser.add_argument(
        "--walk-forward-config",
        type=Path,
        help="Fixed-parameter chronological validation partition JSON",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if bool(args.benchmark_csv) != bool(args.benchmark_metadata):
        parser.error("Provide both benchmark files")
    if args.output.exists():
        parser.error("Output already exists; choose a new path to preserve previous research")
    try:
        config = (
            StrategyConfig.model_validate_json(args.strategy_config.read_text())
            if args.strategy_config
            else defaults(args.strategy)
        )
        if config.name != args.strategy:
            raise ValueError("Strategy config name does not match --strategy")
        settings = (
            RunConfig.model_validate_json(args.run_config.read_text())
            if args.run_config
            else RunConfig()
        )
        dataset = load_csv(args.csv, args.metadata)
        benchmark = (
            load_csv(args.benchmark_csv, args.benchmark_metadata) if args.benchmark_csv else None
        )
        if args.walk_forward_config:
            from services.backtesting.walk_forward import WalkForwardConfig, walk_forward

            plan = WalkForwardConfig.model_validate_json(args.walk_forward_config.read_text())
            report = walk_forward(dataset, config, settings, plan, benchmark)
        else:
            report = research(dataset, config, settings, benchmark)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental report overwrite, including racing runs.
    with args.output.open("x") as output:
        json.dump(report, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
    print(f"Saved {report['run_id']} to {args.output}; paper authorization remains disabled")


if __name__ == "__main__":
    main()
