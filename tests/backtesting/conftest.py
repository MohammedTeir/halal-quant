from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from services.market_data.csv_data import Dataset, DataSpec


@pytest.fixture
def make_dataset():
    def make(prices=None, asset="stock", seconds=None, count=400, symbol="EXAMPLE"):
        seconds = seconds or (3600 if asset == "gold" else 86400)
        if prices is None:
            i = np.arange(count)
            prices = 100 + i * 0.06 + np.sin(i / 4) * 2 + np.sin(i / 13) * 3
        close = np.asarray(prices, dtype=float)
        opening = np.r_[close[0], close[:-1]]
        bars = pd.DataFrame(
            {
                "Open": opening,
                "High": np.maximum(opening, close) + 0.2,
                "Low": np.minimum(opening, close) - 0.2,
                "Close": close,
                "Volume": 100000 + np.arange(len(close)) % 3 * 10000,
            },
            index=pd.date_range("2020-01-01", periods=len(close), freq=f"{seconds}s", tz="UTC"),
        )
        spec = DataSpec(
            source="test_fixture",
            symbol=symbol,
            asset_class=asset,
            timeframe_seconds=seconds,
            price_basis="split_adjusted",
            retrieved_at=datetime(2026, 10, 28, tzinfo=UTC),
            synthetic=True,
        )
        return Dataset(bars, spec, "test_csv_hash", "test_metadata_hash")

    return make
