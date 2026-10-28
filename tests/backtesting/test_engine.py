from dataclasses import replace
from datetime import timedelta

import pandas as pd
import pytest

from services.backtesting.engine import RunConfig, research, simulate
from services.technical_signals.strategies import defaults
from tests.backtesting.test_strategies import config


def isolated(make_dataset):
    data = make_dataset(prices=[100, 100, 100, 112, 113, 114, 115, 116])
    data.bars.loc[data.bars.index[3], ["Open", "Low"]] = [110, 109]
    signal = pd.DataFrame({"entry": False, "exit": False, "atr": 1.0}, index=data.bars.index)
    signal.loc[data.bars.index[2], "entry"] = True
    return data, signal


def test_next_open_whole_long_and_end_liquidation(make_dataset):
    data, signals = isolated(make_dataset)
    settings = RunConfig(commission_rate=0, spread_bps=0, slippage_bps=0)
    strategy = defaults("adaptive_pullback").model_copy(update={"stop_atr": 20, "trail_atr": 100})
    result = simulate(data.bars, signals, strategy, settings, data.bars.index[1])
    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["entry_bar"] == 3 > result["entry_candidates"][0]["signal_bar"]
    assert trade["entry_price"] == 110
    assert trade["size"] == 10
    assert trade["exit_bar"] == 7
    assert result["open_positions"] == result["pending_orders"] == 0
    assert all(
        w.startswith("DatetimeIndex.dayofweek is deprecated") for w in result["engine_warnings"]
    )


def test_costs_reduce_equity(make_dataset):
    data, signals = isolated(make_dataset)
    strategy = defaults("adaptive_pullback").model_copy(update={"stop_atr": 20, "trail_atr": 100})
    zero = simulate(
        data.bars,
        signals,
        strategy,
        RunConfig(commission_rate=0, spread_bps=0, slippage_bps=0),
        data.bars.index[1],
    )
    costs = simulate(data.bars, signals, strategy, RunConfig(), data.bars.index[1])
    assert costs["final_equity"] < zero["final_equity"]
    assert costs["trades"][0]["commission_and_slippage"] > 0
    assert costs["trades"][0]["entry_price"] > zero["trades"][0]["entry_price"]


def test_stop_gap_fills_worse_than_stop(make_dataset):
    data = make_dataset(prices=[100, 100, 100, 101, 80, 81, 82, 83])
    data.bars.loc[data.bars.index[4], ["Open", "Low", "High"]] = [80, 79, 81]
    signals = pd.DataFrame({"entry": False, "exit": False, "atr": 1.0}, index=data.bars.index)
    signals.loc[data.bars.index[2], "entry"] = True
    strategy = defaults("adaptive_pullback").model_copy(update={"stop_atr": 5, "trail_atr": 100})
    result = simulate(
        data.bars,
        signals,
        strategy,
        RunConfig(spread_bps=0, slippage_bps=0, commission_rate=0),
        data.bars.index[1],
    )
    trade = result["trades"][0]
    assert trade["entry_bar"] == 3
    assert trade["exit_bar"] == 4
    assert trade["exit_price"] == 80
    assert trade["exit_price"] < 95
    assert trade["pnl_after_costs"] < 0


def test_trailing_stop_only_tightens(make_dataset):
    data, signals = isolated(make_dataset)
    signals.iloc[4, signals.columns.get_loc("atr")] = 10
    strategy = defaults("adaptive_pullback").model_copy(update={"stop_atr": 20, "trail_atr": 3})
    result = simulate(data.bars, signals, strategy, RunConfig(), data.bars.index[1])
    assert result["stop_updates"]
    assert all(item["updated"] >= item["previous"] for item in result["stop_updates"])


def test_cash_too_small_never_creates_fractional_or_borrowed_position(make_dataset):
    data, signals = isolated(make_dataset)
    result = simulate(
        data.bars, signals, defaults("adaptive_pullback"), RunConfig(cash=10), data.bars.index[1]
    )
    assert result["trade_count"] == 0
    assert result["zero_quantity_candidates"] == 1
    assert result["open_positions"] == result["pending_orders"] == 0


@pytest.mark.parametrize(
    ("name", "asset"),
    [("adaptive_pullback", "stock"), ("regime_trend", "etf"), ("breakout_retest", "gold")],
)
def test_reproducible_runs_with_holdout_and_funded_baseline(make_dataset, name, asset):
    if asset == "stock":
        motif = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 108, 107, 109, 111, 112]
        data = make_dataset(prices=[value + 6 * cycle for cycle in range(25) for value in motif])
    else:
        data = make_dataset(asset=asset)
    benchmark = make_dataset(asset="etf", symbol="BENCHMARK") if asset == "etf" else None
    settings = RunConfig()
    first = research(data, config(name), settings, benchmark)
    assert first == research(data, config(name), settings, benchmark)
    assert first["synthetic"] and not first["authorized_for_paper"]
    assert first["windows"]["train"]["last_bar_close"] < first["windows"]["holdout"]["signal_start"]
    for window in first["windows"].values():
        for key in ("strategy", "buy_and_hold"):
            result = window[key]
            assert result["trade_count"] > 0
            assert result["open_positions"] == result["pending_orders"] == 0
            assert all(
                w.startswith("DatetimeIndex.dayofweek is deprecated")
                for w in result["engine_warnings"]
            )
            assert all(t["size"] > 0 for t in result["trades"])
            assert all(
                event["bar_close"] >= window["signal_start"] for event in result["entry_candidates"]
            )
    # Changes after the fixed training boundary cannot alter training fills or metrics.
    changed = data.bars.copy()
    changed.loc[changed.index[300:], ["Open", "High", "Low", "Close"]] *= 1.5
    second = research(replace(data, bars=changed), config(name), settings, benchmark)
    assert first["windows"]["train"] == second["windows"]["train"]


def test_date_range_preserves_warmup_and_boundary_liquidation(make_dataset):
    data = make_dataset(asset="etf")
    settings = RunConfig(
        start_at=data.bars.index[100].to_pydatetime(), end_at=data.bars.index[300].to_pydatetime()
    )
    report = research(
        data, config("regime_trend"), settings, make_dataset(asset="etf", symbol="BENCHMARK")
    )
    assert report["windows"]["train"]["signal_start"] == data.bars.index[100].isoformat()
    assert report["windows"]["holdout"]["last_bar_close"] == data.bars.index[300].isoformat()
    with pytest.raises(ValueError):
        RunConfig(start_at=settings.end_at, end_at=settings.start_at)
    with pytest.raises(ValueError):
        RunConfig(start_at=settings.start_at.replace(tzinfo=None))
    with pytest.raises(ValueError):
        research(
            data,
            config("regime_trend"),
            RunConfig(start_at=settings.end_at, end_at=settings.end_at + timedelta(days=2)),
            make_dataset(asset="etf", symbol="BENCHMARK"),
        )


def test_next_open_gap_cannot_borrow_cash_and_rejection_is_visible(make_dataset):
    data, signals = isolated(make_dataset)
    data.bars.loc[data.bars.index[3], ["Open", "High", "Low", "Close"]] = [
        20000,
        20001,
        19999,
        20000,
    ]
    result = simulate(
        data.bars, signals, defaults("adaptive_pullback"), RunConfig(), data.bars.index[1]
    )
    assert result["trade_count"] == 0
    assert result["unfilled_entry_candidates"] == 1
    assert result["final_equity"] == result["initial_cash"]
    assert result["open_positions"] == result["pending_orders"] == 0


def test_invalid_costs_and_insufficient_training_window_rejected(make_dataset):
    with pytest.raises(ValueError, match="Combined"):
        RunConfig(commission_rate=0.09, slippage_bps=200)
    data = make_dataset(asset="etf", count=100)
    with pytest.raises(ValueError, match="Training window"):
        research(
            data,
            config("regime_trend"),
            RunConfig(
                start_at=data.bars.index[80], end_at=data.bars.index[89], train_fraction=0.21
            ),
            make_dataset(asset="etf", symbol="BENCHMARK"),
        )
