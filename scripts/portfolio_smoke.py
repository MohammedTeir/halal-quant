"""Deterministic synthetic portfolio/optimization plumbing, never a performance claim."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from scripts.generate_research_demo import generate
from services.technical_signals.strategies import defaults


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output
    if output.exists():
        parser.error("Output directory exists")
    generate(output / "data")
    instruments = []
    evidence = []
    for label, name, sector in [
        ("stock", "adaptive_pullback", "technology"),
        ("etf", "regime_trend", "diversified"),
    ]:
        item = {
            "csv": f"data/{label}.csv",
            "metadata": f"data/{label}.json",
            "sector": sector,
            "strategy": defaults(name).model_dump(mode="json"),
        }
        if label == "etf":
            item.update(
                benchmark_csv="data/benchmark.csv", benchmark_metadata="data/benchmark.json"
            )
        instruments.append(item)
        for kind in ("compliance", "news"):
            evidence.append(
                {
                    "revision_id": f"demo-{label}-{kind}",
                    "scope": f"DEMO_{label.upper()}",
                    "kind": kind,
                    "state": "ALLOW",
                    "published_at": "2019-01-01T00:00:00Z",
                    "received_at": "2019-01-01T00:00:00Z",
                    "effective_at": "2019-01-01T00:00:00Z",
                    "expires_at": "2024-01-01T00:00:00Z",
                    "source_sha256": "a" * 64,
                }
            )
    evidence.append(
        evidence[0] | {"revision_id": "demo-market", "scope": "MARKET", "kind": "macro"}
    )
    for revision, state, date in [
        ("blocked", "BLOCK", "2021-01-01T00:00:00Z"),
        ("restored", "ALLOW", "2022-01-01T00:00:00Z"),
    ]:
        source = next(r for r in evidence if r["scope"] == "DEMO_STOCK" and r["kind"] == "news")
        evidence.append(
            source
            | {
                "revision_id": revision,
                "state": state,
                "published_at": date,
                "received_at": date,
                "effective_at": date,
            }
        )
    manifest = {
        "instruments": instruments,
        "start_at": "2020-09-01T00:00:00Z",
        "evidence": evidence,
        "validation": {"test_bars": 100, "final_holdout_bars": 200, "cost_multipliers": [1, 2]},
        "monte_carlo_seed": 17,
        "monte_carlo_iterations": 100,
    }
    path = output / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    reports = []
    for suffix in ("first", "repeat"):
        target = output / f"portfolio-{suffix}.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "services.backtesting.portfolio_cli",
                "--manifest",
                str(path),
                "--output",
                str(target),
            ],
            check=True,
        )
        reports.append(target)
    if reports[0].read_bytes() != reports[1].read_bytes():
        raise ValueError("Portfolio replay differs")
    report = json.loads(reports[0].read_text())
    for result in report["runs"].values():
        if result["trade_count"] == 0 or result["open_positions"] or result["pending_orders"]:
            raise ValueError("Synthetic fixture does not exercise flat completed trades")
    if (
        report["runs"]["controlled"]["trade_count"]
        == report["runs"]["technical_only"]["trade_count"]
    ):
        raise ValueError("Replay fixture must change technical entries")
    candidates = output / "candidates.json"
    base = defaults("adaptive_pullback")
    candidates.write_text(
        json.dumps([base.model_dump(), base.model_copy(update={"stop_atr": 3}).model_dump()])
    )
    plan = output / "plan.json"
    plan.write_text(
        json.dumps({"initial_history_bars": 500, "test_bars": 100, "final_holdout_bars": 200})
    )
    selection_reports = []
    for suffix in ("first", "repeat"):
        target = output / f"selection-{suffix}.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "services.backtesting.cli",
                "--strategy",
                "adaptive_pullback",
                "--csv",
                str(output / "data/stock.csv"),
                "--metadata",
                str(output / "data/stock.json"),
                "--walk-forward-config",
                str(plan),
                "--candidate-configs",
                str(candidates),
                "--output",
                str(target),
            ],
            check=True,
        )
        selection_reports.append(target)
    if selection_reports[0].read_bytes() != selection_reports[1].read_bytes():
        raise ValueError("Parameter selection replay differs")
    summary = {
        "purpose": "synthetic_software_acceptance_only",
        "authorized": False,
        "byte_identical_portfolio_repeat": True,
        "byte_identical_optimization_repeat": True,
        "source_sha256": report["source_sha256"],
        "lockfile_sha256": report["lockfile_sha256"],
        "portfolio_run_id": report["run_id"],
        "runs": {
            name: {
                k: result[k]
                for k in [
                    "trade_count",
                    "return_percent",
                    "maximum_drawdown_percent",
                    "profit_factor",
                    "open_positions",
                    "pending_orders",
                ]
            }
            for name, result in report["runs"].items()
        },
        "research_gates": report["gates"],
        "monte_carlo": report["monte_carlo"],
        "portfolio_validation": {
            "performance_accepted": report["validation"]["performance_accepted"],
            "unused_development_bars": report["validation"]["unused_development_bars"],
            "scenarios": [
                {
                    "cost_multiplier": scenario["cost_multiplier"],
                    "gates": scenario["gates"],
                    "windows": [
                        {
                            "kind": window["kind"],
                            "signal_start": window["signal_start"],
                            "last_bar_close": window["last_bar_close"],
                            "controlled_trade_count": window["runs"]["controlled"]["trade_count"],
                            "controlled_return_percent": window["runs"]["controlled"][
                                "return_percent"
                            ],
                            "unreconciled_positions": window["runs"]["controlled"][
                                "open_positions"
                            ],
                            "unreconciled_orders": window["runs"]["controlled"]["pending_orders"],
                        }
                        for window in scenario["windows"]
                    ],
                }
                for scenario in report["validation"]["scenarios"]
            ],
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    print("PASS: portfolio and training-only selection reproduce; research promotion remains gated")


if __name__ == "__main__":
    main()
