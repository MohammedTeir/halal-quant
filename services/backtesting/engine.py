"""Single-instrument, whole-share research adapter around Backtesting.py."""

import hashlib
import importlib.metadata
import json
import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from services.market_data.csv_data import Dataset
from services.technical_signals.strategies import StrategyConfig, features


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    cash: float = Field(default=10000, gt=0)
    allocation: float = Field(default=0.1, gt=0, le=1)
    commission_rate: float = Field(default=0.001, ge=0, lt=0.1)
    spread_bps: float = Field(default=5, ge=0, lt=1000)
    slippage_bps: float = Field(default=2, ge=0, lt=1000)
    train_fraction: float = Field(default=0.7, gt=0.2, lt=0.9)
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.commission_rate + self.slippage_bps / 10000 >= 0.1:
            raise ValueError("Combined per-side commission and slippage must be below 10%")
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValueError("start_at must precede end_at")
        return self


class TechnicalStrategy(Strategy):
    config = None
    run_config = None
    trade_start = None
    liquidation_signal_time = None
    baseline = False

    def init(self):
        self.peak = None
        self.events = []
        self.stops = []
        self.baseline_bought = False
        self.blocked_zero_quantity = 0

    def next(self):
        now = self.data.index[-1]
        if now < self.trade_start:
            return
        # The evaluation boundary is fixed in advance. Reserve a final bar to fill
        # liquidation; never use finalize_trades' retroactive last-open replay.
        if now >= self.liquidation_signal_time:
            for order in list(self.orders):
                if not order.is_contingent:
                    order.cancel()
            if self.position:
                self.position.close()
            return
        volatility = float(self.data.ATR[-1])
        if self.position:
            if not self.baseline:
                self.peak = max(self.peak, float(self.data.High[-1]))
                for trade in self.trades:
                    previous = trade.sl
                    trade.sl = max(previous, self.peak - self.config.trail_atr * volatility)
                    self.stops.append(
                        {"bar_close": now.isoformat(), "previous": previous, "updated": trade.sl}
                    )
                if self.data.ExitCandidate[-1]:
                    self.position.close()
            return
        self.peak = None
        if self.orders or (self.baseline and self.baseline_bought):
            return
        if not self.baseline and not self.data.EntryCandidate[-1]:
            return
        close = float(self.data.Close[-1])
        stop = close - self.config.stop_atr * volatility
        if not self.baseline and (not math.isfinite(stop) or stop <= 0):
            return
        charge = self.run_config.commission_rate + self.run_config.slippage_bps / 10000
        unit_cost = close * (1 + self.run_config.spread_bps / 10000) * (1 + charge)
        quantity = math.floor(self.equity * self.run_config.allocation / unit_cost)
        if quantity < 1:
            self.blocked_zero_quantity += 1
            return
        self.buy(size=quantity, sl=None if self.baseline else stop)
        self.peak = close
        self.baseline_bought = self.baseline
        self.events.append(
            {
                "signal_bar": len(self.data) - 1,
                "bar_close": now.isoformat(),
                "action": "ENTRY_CANDIDATE",
                "quantity": quantity,
            }
        )


def _finite(value):
    number = float(value)
    return number if math.isfinite(number) else None


def simulate(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: StrategyConfig,
    settings: RunConfig,
    trade_start: pd.Timestamp,
    baseline=False,
):
    frame = bars.assign(EntryCandidate=signals.entry, ExitCandidate=signals.exit, ATR=signals.atr)
    charge = settings.commission_rate + settings.slippage_bps / 10000
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        simulator = Backtest(
            frame,
            TechnicalStrategy,
            cash=settings.cash,
            commission=charge,
            spread=settings.spread_bps / 10000,
            margin=1,
            trade_on_close=False,
            hedging=False,
            exclusive_orders=True,
            finalize_trades=False,
        )
        result = simulator.run(
            config=config,
            run_config=settings,
            trade_start=trade_start,
            liquidation_signal_time=frame.index[-2],
            baseline=baseline,
        )
    strategy = result["_strategy"]
    trades = []
    for _, row in result["_trades"].iterrows():
        trades.append(
            {
                "size": int(row.Size),
                "entry_bar": int(row.EntryBar),
                "exit_bar": int(row.ExitBar),
                "entry_bar_close": row.EntryTime.isoformat(),
                "exit_bar_close": row.ExitTime.isoformat(),
                "entry_price": float(row.EntryPrice),
                "exit_price": float(row.ExitPrice),
                "pnl_after_costs": float(row.PnL),
                "commission_and_slippage": float(row.Commission),
            }
        )
    curve = result["_equity_curve"].Equity.loc[trade_start:]
    drawdown = 1 - curve / curve.cummax()
    pnls = [trade["pnl_after_costs"] for trade in trades]
    gains, losses = sum(max(p, 0) for p in pnls), -sum(min(p, 0) for p in pnls)
    return {
        "trade_count": len(trades),
        "initial_cash": settings.cash,
        "final_equity": float(curve.iloc[-1]),
        "return_percent": (float(curve.iloc[-1]) / settings.cash - 1) * 100,
        "maximum_drawdown_percent": float(drawdown.max() * 100),
        "expectancy_cash_after_costs": float(np.mean(pnls)) if pnls else None,
        "profit_factor": _finite(gains / losses) if losses else None,
        "profit_factor_note": "undefined_without_losses" if not losses else None,
        "open_positions": len(strategy.trades),
        "pending_orders": len(strategy.orders),
        "zero_quantity_candidates": strategy.blocked_zero_quantity,
        "unfilled_entry_candidates": sum(
            not any(t["entry_bar"] == e["signal_bar"] + 1 for t in trades) for e in strategy.events
        ),
        "engine_warnings": [str(w.message) for w in captured],
        "trades": trades,
        "entry_candidates": strategy.events,
        "stop_updates": strategy.stops,
    }


def source_hash():
    root = Path(__file__).resolve().parents[2]
    paths = [root / "packages/indicators/core.py", *sorted((root / "services").rglob("*.py"))]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def research(
    dataset: Dataset, config: StrategyConfig, settings: RunConfig, benchmark: Dataset | None = None
):
    signals = features(dataset, config, benchmark)
    bars = dataset.bars
    if settings.end_at is not None:
        bars = bars.loc[: pd.Timestamp(settings.end_at)]
    eligible = bars.index
    if settings.start_at is not None:
        eligible = eligible[eligible >= pd.Timestamp(settings.start_at)]
    if len(eligible) < 10:
        raise ValueError("Evaluation window needs at least ten bars")
    split_time = eligible[int(len(eligible) * settings.train_fraction)]
    split = int(bars.index.get_loc(split_time))
    ready = signals.index[signals.ready]
    if len(ready) == 0:
        raise ValueError("Insufficient pre-holdout indicator warm-up")
    train_start = max(ready[0], eligible[0])
    if len(bars.iloc[:split].loc[train_start:]) < 4:
        raise ValueError("Training window needs warm-up and at least four evaluation bars")
    if len(bars) - split < 4:
        raise ValueError("Holdout needs at least four bars")
    manifests = {
        "instrument": dataset.manifest(),
        "benchmark": benchmark.manifest() if benchmark is not None else None,
    }
    provenance = {
        "schema_version": "1.0",
        "strategy_version": "2.0.0-python",
        "strategy": config.model_dump(),
        "run_settings": settings.model_dump(mode="json"),
        "inputs": manifests,
        "source_sha256": source_hash(),
        "lockfile_sha256": hashlib.sha256(
            (Path(__file__).resolve().parents[2] / "uv.lock").read_bytes()
        ).hexdigest(),
        "engine": {
            "backtesting": importlib.metadata.version("backtesting"),
            "numpy": importlib.metadata.version("numpy"),
            "pandas": importlib.metadata.version("pandas"),
        },
    }
    report = provenance | {
        "run_id": hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest(),
        "mode": "technical_research_only",
        "authorized_for_paper": False,
        "synthetic": dataset.spec.synthetic or (benchmark is not None and benchmark.spec.synthetic),
        "split_policy": "chronological; fixed parameters; no optimization or holdout selection",
        "execution": "next bar open; timestamps label bar closes; final bar reserved for liquidation",
        "cost_model": "commission plus slippage charge per side; spread charged by engine on entry",
        "baseline": "buy-and-hold at same initial allocation and costs, without strategy stops",
    }
    windows = {
        "train": (bars.iloc[:split], train_start),
        "holdout": (bars, split_time),
    }
    report["windows"] = {}
    for name, (bars, start) in windows.items():
        report["windows"][name] = {
            "signal_start": start.isoformat(),
            "last_bar_close": bars.index[-1].isoformat(),
            "strategy": simulate(bars, signals.loc[bars.index], config, settings, start),
            "buy_and_hold": simulate(
                bars, signals.loc[bars.index], config, settings, start, baseline=True
            ),
        }
    return report
