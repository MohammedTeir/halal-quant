"""Deterministic synthetic OHLCV for plumbing tests, never market performance evidence."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from services.market_data.csv_data import DataSpec, write_metadata


def generate(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    for seed, (name, asset, count, seconds) in enumerate(
        [
            ("stock", "stock", 1000, 86400),
            ("etf", "etf", 1000, 86400),
            ("benchmark", "etf", 1000, 86400),
            ("gold", "gold", 6000, 14400),
        ],
        start=1,
    ):
        csv, metadata = directory / f"{name}.csv", directory / f"{name}.json"
        if csv.exists() or metadata.exists():
            raise ValueError(f"Refusing to overwrite demo input {name}")
        random = np.random.default_rng(seed)
        i = np.arange(count)
        close = (
            100
            + 0.035 * i
            + 4 * np.sin(i / 13)
            + 1.4 * np.sin(i / 3)
            + random.normal(0, 0.35, count)
        )
        opening = np.r_[close[0], close[:-1]] + random.normal(0, 0.1, count)
        frame = pd.DataFrame(
            {
                "timestamp": pd.date_range(
                    "2020-01-01", periods=count, freq=f"{seconds}s", tz="UTC"
                ),
                "Open": opening,
                "High": np.maximum(opening, close) + 0.5,
                "Low": np.minimum(opening, close) - 0.5,
                "Close": close,
                "Volume": random.integers(100000, 300000, count),
            }
        )
        frame.to_csv(csv, index=False, float_format="%.8f")
        write_metadata(
            metadata,
            DataSpec(
                source="deterministic_synthetic_demo_v1",
                symbol=f"DEMO_{name.upper()}",
                asset_class=asset,
                timeframe_seconds=seconds,
                price_basis="split_adjusted" if asset != "gold" else "unadjusted",
                retrieved_at=datetime(2026, 10, 28, tzinfo=UTC),
                synthetic=True,
            ),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    generate(parser.parse_args().output)
