"""Exercise default strategies and CLI reproducibility on synthetic data only."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from scripts.generate_research_demo import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output
    data = output / "data"
    generate(data)
    summary = {
        "purpose": "synthetic_software_acceptance_only",
        "authorized_for_paper": False,
        "real_market_performance_verified": False,
        "strategies": {},
    }
    for label, name in [
        ("stock", "adaptive_pullback"),
        ("etf", "regime_trend"),
        ("gold", "breakout_retest"),
    ]:
        arguments = [
            "--strategy",
            name,
            "--csv",
            str(data / f"{label}.csv"),
            "--metadata",
            str(data / f"{label}.json"),
        ]
        if label == "etf":
            arguments += [
                "--benchmark-csv",
                str(data / "benchmark.csv"),
                "--benchmark-metadata",
                str(data / "benchmark.json"),
            ]
        report_path = output / f"{label}.json"
        repeat_path = output / f"{label}.repeat.json"
        for path in (report_path, repeat_path):
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "services.backtesting.cli",
                    *arguments,
                    "--output",
                    str(path),
                ],
                check=True,
            )
        if report_path.read_bytes() != repeat_path.read_bytes():
            raise RuntimeError(f"Non-reproducible report: {label}")
        report = json.loads(report_path.read_text())
        windows = {}
        for window, result in report["windows"].items():
            windows[window] = {}
            for kind in ("strategy", "buy_and_hold"):
                run = result[kind]
                if (
                    run["trade_count"] == 0
                    or run["open_positions"]
                    or run["pending_orders"]
                    or run["unfilled_entry_candidates"]
                ):
                    raise RuntimeError(f"Incomplete synthetic acceptance: {label}/{window}/{kind}")
                if any(
                    not warning.startswith("DatetimeIndex.dayofweek is deprecated")
                    for warning in run["engine_warnings"]
                ):
                    raise RuntimeError(f"Unexpected engine warning: {label}/{window}/{kind}")
                windows[window][kind] = {
                    key: run[key]
                    for key in (
                        "trade_count",
                        "open_positions",
                        "pending_orders",
                        "unfilled_entry_candidates",
                        "engine_warnings",
                    )
                }
        summary["strategies"][name] = {
            "run_id": report["run_id"],
            "source_sha256": report["source_sha256"],
            "lockfile_sha256": report["lockfile_sha256"],
            "inputs": report["inputs"],
            "byte_identical_repeat": True,
            "windows": windows,
        }
    with (output / "summary.json").open("x") as target:
        json.dump(summary, target, indent=2, sort_keys=True, allow_nan=False)
        target.write("\n")
    print(
        "PASS: all three default strategies and baselines trade, reconcile to flat, and reproduce byte-for-byte"
    )


if __name__ == "__main__":
    main()
