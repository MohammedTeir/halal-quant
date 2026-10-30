"""Offline multi-asset research: JSON manifest paths are local, no orders or network."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from services.backtesting.engine import source_hash
from services.backtesting.portfolio import PortfolioConfig, portfolio
from services.backtesting.replay import ReplayEvidence
from services.backtesting.validation import monte_carlo, research_gates
from services.market_data.csv_data import load_csv
from services.technical_signals.strategies import StrategyConfig, features


class Instrument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv: str
    metadata: str
    sector: str = Field(min_length=1)
    strategy: StrategyConfig
    benchmark_csv: str | None = None
    benchmark_metadata: str | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruments: list[Instrument] = Field(min_length=1, max_length=100)
    settings: PortfolioConfig = PortfolioConfig()
    start_at: AwareDatetime
    evidence: list[ReplayEvidence] = Field(default_factory=list)
    monte_carlo_seed: int = 0
    monte_carlo_iterations: int = Field(default=1000, ge=1, le=10000, strict=True)


def run(manifest, base):
    datasets, signals, sectors, inputs = {}, {}, {}, {}
    for item in manifest.instruments:
        data = load_csv(base / item.csv, base / item.metadata)
        if data.spec.symbol in datasets:
            raise ValueError("Duplicate portfolio symbol")
        if bool(item.benchmark_csv) != bool(item.benchmark_metadata):
            raise ValueError("Both benchmark files required")
        benchmark = (
            load_csv(base / item.benchmark_csv, base / item.benchmark_metadata)
            if item.benchmark_csv
            else None
        )
        symbol = data.spec.symbol
        datasets[symbol], sectors[symbol] = data, item.sector
        signals[symbol] = features(data, item.strategy, benchmark).assign(
            stop_atr=item.strategy.stop_atr, trail_atr=item.strategy.trail_atr
        )
        inputs[symbol] = {
            "instrument": data.manifest(),
            "benchmark": benchmark.manifest() if benchmark else None,
        }
    provenance = {
        "manifest": manifest.model_dump(mode="json"),
        "inputs": inputs,
        "source_sha256": source_hash(),
        "lockfile_sha256": hashlib.sha256(
            (Path(__file__).resolve().parents[2] / "uv.lock").read_bytes()
        ).hexdigest(),
        "engine": {name: importlib.metadata.version(name) for name in ("numpy", "pandas")},
    }
    runs = {
        mode: portfolio(
            datasets,
            signals,
            sectors,
            manifest.settings,
            manifest.evidence,
            manifest.start_at,
            mode,
        )
        for mode in ("controlled", "technical_only", "buy_and_hold")
    }
    controlled = runs["controlled"]
    return {
        **provenance,
        "run_id": hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest(),
        "authorized": False,
        "synthetic": any(d.spec.synthetic for d in datasets.values()),
        "historical_sources_verified": False,
        "baseline_note": "Technical-only and buy-and-hold bypass replay evidence as counterfactual comparisons only; no approvals",
        "runs": runs,
        "gates": research_gates([controlled]),
        "monte_carlo": monte_carlo(
            [t["pnl_after_costs"] for t in controlled["trades"]],
            manifest.settings.cash,
            seed=manifest.monte_carlo_seed,
            iterations=manifest.monte_carlo_iterations,
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; preserve previous research")
    try:
        manifest = Manifest.model_validate_json(args.manifest.read_text())
        report = run(manifest, args.manifest.parent)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as target:
            json.dump(report, target, sort_keys=True, indent=2, allow_nan=False)
            target.write("\n")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print("Saved offline portfolio research; trading remains unauthorized")


if __name__ == "__main__":
    main()
