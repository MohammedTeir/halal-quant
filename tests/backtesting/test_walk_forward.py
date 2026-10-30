from dataclasses import replace

import pytest

from services.backtesting.engine import RunConfig
from services.backtesting.walk_forward import WalkForwardConfig, walk_forward
from services.technical_signals.strategies import defaults


def run(data, **kwargs):
    return walk_forward(
        data,
        defaults("adaptive_pullback"),
        RunConfig(),
        WalkForwardConfig(initial_history_bars=250, test_bars=40, final_holdout_bars=50),
        **kwargs,
    )


def test_disjoint_windows_and_reproducibility(make_dataset):
    data = make_dataset(prices=[100 + i * 0.03 for i in range(423)])
    report = run(data)
    assert report == run(data)
    assert report["authorized_for_paper"] is False
    assert report["unused_development_bars"] == 3
    assert [w["kind"] for w in report["windows"]] == ["development"] * 3 + ["final_holdout"]
    for left, right in zip(report["windows"], report["windows"][1:]):
        assert left["last_bar_close"] < right["signal_start"]
    for window in report["windows"]:
        for name in ["strategy", "buy_and_hold"]:
            assert window[name]["open_positions"] == window[name]["pending_orders"] == 0
            assert window[name]["initial_cash"] == 10000


def test_final_holdout_cannot_change_development(make_dataset):
    data = make_dataset(prices=[100 + (i % 35) for i in range(420)])
    original = run(data)
    changed = replace(data, bars=data.bars.copy())
    changed.bars.loc[changed.bars.index[-50:], ["Open", "High", "Low", "Close"]] *= 2
    assert run(changed)["windows"][:-1] == original["windows"][:-1]


def test_rejects_insufficient_partitions_and_warmup(make_dataset):
    data = make_dataset(prices=[100] * 300)
    with pytest.raises(ValueError, match="full development"):
        run(data)
    with pytest.raises(ValueError, match="warm-up"):
        walk_forward(
            data,
            defaults("adaptive_pullback"),
            RunConfig(),
            WalkForwardConfig(initial_history_bars=10, test_bars=40, final_holdout_bars=50),
        )
    with pytest.raises(ValueError):
        WalkForwardConfig(initial_history_bars=10, test_bars=3, final_holdout_bars=50)
