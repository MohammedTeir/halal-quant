from dataclasses import replace

import pandas as pd
import pytest

from services.backtesting.portfolio import PortfolioConfig
from services.backtesting.portfolio_validation import PortfolioValidationConfig, validate_portfolio
from services.backtesting.replay import ReplayEvidence


def inputs(make_dataset):
    data = make_dataset(count=60, symbol="AAA")
    frame = pd.DataFrame(
        {
            "ready": True,
            "entry": True,
            "exit": False,
            "atr": 1.0,
            "stop_atr": 20.0,
            "trail_atr": 100.0,
        },
        index=data.bars.index,
    )
    records = [
        ReplayEvidence(
            revision_id=kind,
            kind=kind,
            scope="MARKET" if kind == "macro" else "AAA",
            state="ALLOW",
            published_at="2019-01-01T00:00:00Z",
            received_at="2019-01-01T00:00:00Z",
            effective_at="2019-01-01T00:00:00Z",
            expires_at="2025-01-01T00:00:00Z",
            source_sha256="a" * 64,
        )
        for kind in ("compliance", "news", "macro")
    ]
    return data, frame, records


def run(data, frame, records):
    return validate_portfolio(
        {"AAA": data},
        {"AAA": frame},
        {"AAA": "tech"},
        PortfolioConfig(),
        records,
        data.bars.index[10],
        PortfolioValidationConfig(test_bars=12, final_holdout_bars=12),
        iterations=20,
    )


def test_portfolio_periods_cost_stress_and_reproduction(make_dataset):
    data, frame, records = inputs(make_dataset)
    report = run(data, frame, records)
    assert report == run(data, frame, records)
    assert report["performance_accepted"] is False
    assert report["unused_development_bars"] == 2
    base, stressed = report["scenarios"]
    assert [s["kind"] for s in base["windows"]] == ["development"] * 3 + ["final_holdout"]
    for left, right in zip(base["windows"], base["windows"][1:]):
        assert left["last_bar_close"] < right["signal_start"]
    for a, b in zip(base["windows"], stressed["windows"]):
        assert a["runs"]["controlled"]["trade_count"] > 0
        assert b["runs"]["controlled"]["final_equity"] < a["runs"]["controlled"]["final_equity"]
        assert (
            a["runs"]["controlled"]["open_positions"]
            == a["runs"]["controlled"]["pending_orders"]
            == 0
        )


def test_final_prices_cannot_change_prior_portfolio_windows(make_dataset):
    data, frame, records = inputs(make_dataset)
    before = run(data, frame, records)
    changed = replace(data, bars=data.bars.copy())
    changed.bars.loc[changed.bars.index[-12:], ["Open", "High", "Low", "Close"]] *= 1.2
    after = run(changed, frame, records)
    for left, right in zip(before["scenarios"], after["scenarios"]):
        assert left["windows"][:-1] == right["windows"][:-1]


def test_validation_rejects_invalid_plans(make_dataset):
    for multipliers in [(2,), (1, 1), (1, float("nan")), (1, 0.5)]:
        with pytest.raises(ValueError):
            PortfolioValidationConfig(
                test_bars=10, final_holdout_bars=10, cost_multipliers=multipliers
            )
    data, frame, records = inputs(make_dataset)
    with pytest.raises(ValueError, match="full development"):
        validate_portfolio(
            {"AAA": data},
            {"AAA": frame},
            {"AAA": "tech"},
            PortfolioConfig(),
            records,
            data.bars.index[50],
            PortfolioValidationConfig(test_bars=12, final_holdout_bars=12),
        )


def test_validation_rejects_extra_future_rows_before_slicing(make_dataset):
    data, frame, records = inputs(make_dataset)
    other = make_dataset(count=61, symbol="BBB")
    with pytest.raises(ValueError, match="Full portfolio grids"):
        validate_portfolio(
            {"AAA": data, "BBB": other},
            {"AAA": frame, "BBB": frame},
            {"AAA": "tech", "BBB": "tech"},
            PortfolioConfig(),
            records,
            data.bars.index[10],
            PortfolioValidationConfig(test_bars=12, final_holdout_bars=12),
        )
