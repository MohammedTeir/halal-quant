from dataclasses import replace
from datetime import timedelta

import pandas as pd
import pytest

from services.backtesting.portfolio import PortfolioConfig, portfolio
from services.backtesting.replay import ReplayEvidence, replay_gate, validate_replay
from services.backtesting.validation import monte_carlo, research_gates


def evidence(data, *, state="ALLOW", receipt=None, revision="first"):
    at = data.bars.index[0].to_pydatetime()
    return [
        ReplayEvidence(
            revision_id=f"{revision}-{symbol}-{kind}",
            scope=symbol,
            kind=kind,
            state=state,
            published_at=at,
            received_at=receipt or at,
            effective_at=at,
            expires_at=at + timedelta(days=100),
            source_sha256="a" * 64,
        )
        for symbol, kind in [
            ("AAA", "compliance"),
            ("AAA", "news"),
            ("BBB", "compliance"),
            ("BBB", "news"),
            ("MARKET", "macro"),
        ]
    ]


def setup(make_dataset, volume=100000):
    data = {
        s: make_dataset(prices=[100, 100, 101, 103, 104, 105, 106, 107], symbol=s)
        for s in ["AAA", "BBB"]
    }
    signals = {}
    for s, d in data.items():
        d.bars["Volume"] = volume
        signals[s] = pd.DataFrame(
            {
                "ready": True,
                "entry": False,
                "exit": False,
                "atr": 1.0,
                "stop_atr": 10.0,
                "trail_atr": 100.0,
            },
            index=d.bars.index,
        )
        signals[s].loc[d.bars.index[1], "entry"] = True
    return data, signals


def run(data, signals, records, **config):
    return portfolio(
        data,
        signals,
        {"AAA": "technology", "BBB": "technology"},
        PortfolioConfig(**config),
        records,
        data["AAA"].bars.index[1],
    )


def test_shared_cash_sector_cap_next_open_and_flat(make_dataset):
    data, signals = setup(make_dataset)
    r = run(
        data,
        signals,
        evidence(data["AAA"]),
        position_fraction=1,
        sector_fraction=0.15,
        risk_fraction=0.1,
        total_risk_fraction=0.5,
    )
    assert len(r["trades"]) == 1  # AAA uses sector budget; BBB cannot independently spend it.
    t = r["trades"][0]
    assert t["symbol"] == "AAA"
    assert t["quantity"] * t["entry_unit_cost"] <= 1500
    assert pd.Timestamp(t["entry_at"]) == data["AAA"].bars.index[1]
    assert t["entry_unit_cost"] > float(data["AAA"].bars.iloc[2].Open)
    assert r["open_positions"] == r["pending_orders"] == 0
    assert all(v["cash"] >= 0 for v in r["equity_curve"])
    assert r["final_equity"] == pytest.approx(
        10000 + sum(t["pnl_after_costs"] for t in r["trades"])
    )


def test_missing_or_late_evidence_blocks_controlled_only(make_dataset):
    data, signals = setup(make_dataset)
    assert run(data, signals, [])["trade_count"] == 0
    late = evidence(data["AAA"], receipt=data["AAA"].bars.index[4].to_pydatetime())
    assert run(data, signals, late)["trade_count"] == 0
    technical = portfolio(
        data,
        signals,
        {"AAA": "tech", "BBB": "tech"},
        PortfolioConfig(),
        [],
        data["AAA"].bars.index[1],
        "technical_only",
    )
    assert technical["trade_count"] == 2


def test_latest_expired_block_does_not_fall_back(make_dataset):
    data, _ = setup(make_dataset)
    records = evidence(data["AAA"])
    at = data["AAA"].bars.index[2].to_pydatetime()
    block = records[0].model_copy(
        update={
            "revision_id": "block",
            "state": "BLOCK",
            "received_at": at,
            "expires_at": at + timedelta(hours=1),
        }
    )
    blocked, refs = replay_gate([*records, block], "AAA", at + timedelta(days=1))
    assert blocked == ["COMPLIANCE_MISSING_EXPIRED_OR_BLOCKED"]
    assert refs["compliance"] == "block"
    with pytest.raises(ValueError, match="unique"):
        validate_replay([records[0], records[0]])
    with pytest.raises(ValueError, match="Ambiguous"):
        validate_replay([records[0], records[0].model_copy(update={"revision_id": "other"})])


def test_liquidity_and_unreconciled_exit_are_reported(make_dataset):
    data, signals = setup(make_dataset, volume=0)
    assert run(data, signals, evidence(data["AAA"]))["trade_count"] == 0
    data, signals = setup(make_dataset)
    for d in data.values():
        d.bars.loc[d.bars.index[-2], "Volume"] = 0
    r = run(data, signals, evidence(data["AAA"]))
    assert r["open_positions"] == r["pending_orders"] == 2
    assert research_gates([r])["passed"] is False


def test_gap_stop_uses_worse_open_and_future_gate_cannot_change_past(make_dataset):
    data, signals = setup(make_dataset)
    for d in data.values():
        d.bars.loc[d.bars.index[3], ["Open", "Low", "High", "Close"]] = [70, 69, 72, 71]
    records = evidence(data["AAA"])
    r = run(data, signals, records)
    assert all(t["exit_unit_proceeds"] < 70 for t in r["trades"])
    assert all(t["reason"] == "STOP" for t in r["trades"])
    future = evidence(
        data["AAA"],
        state="BLOCK",
        receipt=data["AAA"].bars.index[6].to_pydatetime(),
        revision="later",
    )
    assert run(data, signals, [*records, *future])["trades"] == r["trades"]


def test_grids_and_raw_equities_rejected(make_dataset):
    data, signals = setup(make_dataset)
    data["BBB"] = replace(data["BBB"], bars=data["BBB"].bars.iloc[:-1])
    with pytest.raises(ValueError, match="grids"):
        run(data, signals, [])
    data, signals = setup(make_dataset)
    data["AAA"].spec = data["AAA"].spec.model_copy(update={"price_basis": "unadjusted"})
    with pytest.raises(ValueError, match="Raw equity"):
        run(data, signals, [])


def test_seeded_trade_order_sensitivity_and_gates_fail_closed():
    r = monte_carlo([100, -50, 20, -150, 200], 1000, iterations=100, seed=17)
    assert r == monte_carlo([100, -50, 20, -150, 200], 1000, iterations=100, seed=17)
    assert r["terminal_cash"] == 1120
    assert r["maximum_drawdown_p95_percent"] >= r["maximum_drawdown_p50_percent"]
    assert monte_carlo([], 1000)["status"] == "INSUFFICIENT_TRADES"
    with pytest.raises(ValueError):
        monte_carlo([float("nan")], 1000)
    good = {
        "expectancy_cash_after_costs": 2,
        "profit_factor": 2,
        "maximum_drawdown_percent": 2,
        "return_percent": 1,
        "open_positions": 0,
        "pending_orders": 0,
    }
    gates = research_gates([good, good])
    assert gates["passed"] is False
    assert gates["checks"]["positive_return_multiple_periods"] is True


def test_open_sizing_never_uses_current_bar_volume(make_dataset):
    data, signals = setup(make_dataset)
    before = run(data, signals, evidence(data["AAA"]))
    for d in data.values():
        d.bars.loc[d.bars.index[2], "Volume"] = 1
    after = run(data, signals, evidence(data["AAA"]))
    entries = lambda r: [a["entry_quantity"] for a in r["audit"] if "entry_quantity" in a]
    assert entries(before) == entries(after)
