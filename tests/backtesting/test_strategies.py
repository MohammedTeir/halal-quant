from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from services.technical_signals.strategies import StrategyConfig, features


def config(name, **changes):
    values = {
        "name": name,
        "fast_period": 3,
        "slow_period": 8,
        "pullback_period": 3,
        "rsi_period": 3,
        "adx_period": 2,
        "minimum_adx": 0,
        "volume_period": 2,
        "volume_multiplier": 0.8,
        "pullback_atr": 2,
        "slope_period": 3,
        "atr_period": 2,
        "channel_period": 3,
        "higher_timeframe_hours": 6,
        "maximum_atr_percent": 30,
    }
    return StrategyConfig(**(values | changes))


@pytest.mark.parametrize(
    ("name", "asset", "retest"),
    [
        ("adaptive_pullback", "stock", True),
        ("regime_trend", "etf", True),
        ("breakout_retest", "gold", False),
        ("breakout_retest", "gold", True),
    ],
)
def test_candidates_warmup_and_no_future_leakage(make_dataset, name, asset, retest):
    data = make_dataset(asset=asset)
    benchmark = make_dataset(asset="etf", symbol="BENCHMARK") if asset == "etf" else None
    settings = config(name, require_retest=retest)
    full = features(data, settings, benchmark)
    assert full.entry.sum() > 0, "Fixture must exercise entries, not just pass with no trades"
    assert not full.entry.iloc[:8].any()
    assert full.exit.any()
    for end in [3, 9, 47, 111, 239, 399]:
        prefix = replace(data, bars=data.bars.iloc[:end])
        prefix_benchmark = replace(benchmark, bars=benchmark.bars.iloc[:end]) if benchmark else None
        pd.testing.assert_frame_equal(features(prefix, settings, prefix_benchmark), full.iloc[:end])
    modified = data.bars.copy()
    modified.loc[modified.index[240:], ["Open", "High", "Low", "Close"]] *= 20
    pd.testing.assert_frame_equal(
        features(replace(data, bars=modified), settings, benchmark).iloc[:240], full.iloc[:240]
    )


def test_etf_missing_benchmark_blocks_entries(make_dataset):
    data = make_dataset(asset="etf")
    settings = config("regime_trend")
    with pytest.raises(ValueError, match="benchmark"):
        features(data, settings)
    benchmark = make_dataset(asset="etf", symbol="BENCHMARK")
    baseline = features(data, settings, benchmark)
    missing_time = baseline.index[baseline.entry][0]
    benchmark.bars = benchmark.bars.drop(index=missing_time)
    assert not features(data, settings, benchmark).loc[missing_time, "entry"]


def test_gold_partial_higher_bar_cannot_change_past_trend(make_dataset):
    data = make_dataset(asset="gold")
    settings = config("breakout_retest", require_retest=False)
    full = features(data, settings)
    # Hour 81 is inside a 6h bucket, which is not complete until hour 84.
    changed = data.bars.copy()
    changed.loc[changed.index[81:84], ["Open", "High", "Low", "Close"]] *= 20
    other = features(replace(data, bars=changed), settings)
    # Local indicators may react at 81; no indicator can alter times through 80.
    pd.testing.assert_frame_equal(full.iloc[:81], other.iloc[:81])
    pd.testing.assert_series_equal(full.context_allowed.iloc[:84], other.context_allowed.iloc[:84])


def test_retest_not_on_breakout_bar(make_dataset):
    data = make_dataset(asset="gold")
    immediate = features(data, config("breakout_retest", require_retest=False))
    retest = features(data, config("breakout_retest", require_retest=True))
    assert retest.entry.any()
    assert not np.array_equal(immediate.entry, retest.entry)
    # A simple monotonic run has no fresh crossover following warm-up.
    trend = make_dataset(prices=list(range(100, 300)), asset="gold")
    assert not features(trend, config("breakout_retest", require_retest=True)).entry.any()


def test_asset_timeframe_and_config_validation(make_dataset):
    with pytest.raises(ValueError):
        features(make_dataset(asset="gold"), config("adaptive_pullback"))
    with pytest.raises(ValueError):
        features(make_dataset(asset="gold"), config("breakout_retest", higher_timeframe_hours=1))
    off_grid = make_dataset(asset="gold")
    off_grid.bars.index += pd.Timedelta(minutes=30)
    with pytest.raises(ValueError, match="align"):
        features(off_grid, config("breakout_retest"))
    with pytest.raises(ValueError):
        StrategyConfig(name="adaptive_pullback", fast_period=200, slow_period=50)
    with pytest.raises(ValueError):
        StrategyConfig(name="adaptive_pullback", stop_atr=float("nan"))


def test_incomplete_gold_bucket_and_incompatible_benchmark_fail_closed(make_dataset):
    data = make_dataset(asset="gold")
    missing_close = data.bars.index[200]
    incomplete = replace(data, bars=data.bars.drop(index=missing_close))
    signals = features(incomplete, config("breakout_retest", require_retest=False))
    bucket_close = missing_close.ceil("6h")
    assert not signals.loc[bucket_close, "context_allowed"]
    assert not signals.loc[bucket_close, "entry"]
    etf = make_dataset(asset="etf")
    with pytest.raises(ValueError, match="distinct"):
        features(etf, config("regime_trend"), etf)
    benchmark = make_dataset(asset="etf", symbol="BENCHMARK")
    benchmark.spec = benchmark.spec.model_copy(update={"price_basis": "total_return_adjusted"})
    with pytest.raises(ValueError, match="adjustment"):
        features(etf, config("regime_trend"), benchmark)
