from dataclasses import replace

from services.backtesting.engine import RunConfig
from services.backtesting.walk_forward import WalkForwardConfig, walk_forward
from tests.backtesting.test_strategies import config


def test_training_selection_never_reads_test_or_holdout(make_dataset):
    data = make_dataset(count=400)
    base = config("adaptive_pullback")
    candidates = [base, base.model_copy(update={"stop_atr": 3})]
    plan = WalkForwardConfig(initial_history_bars=200, test_bars=50, final_holdout_bars=100)
    settings = RunConfig()
    original = walk_forward(data, base, settings, plan, candidates=candidates)
    changed = replace(data, bars=data.bars.copy())
    changed.bars.loc[changed.bars.index[300:], ["Open", "High", "Low", "Close"]] *= 1.5
    rerun = walk_forward(changed, base, settings, plan, candidates=candidates)
    assert original["windows"][:-1] == rerun["windows"][:-1]
    assert original["windows"][-1]["selection"] == rerun["windows"][-1]["selection"]
    for window in original["windows"]:
        assert window["selection"]["training_last_bar_close"] < window["signal_start"]
        assert len(window["selection"]["candidates"]) == 2
