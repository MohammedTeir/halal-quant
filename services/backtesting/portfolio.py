"""Synchronous-grid cash-only research simulator; no broker or legal settlement claim."""

import math

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from services.backtesting.replay import replay_gate, validate_replay


class PortfolioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    cash: float = Field(default=10000, gt=0)
    position_fraction: float = Field(default=0.1, gt=0, le=1)
    sector_fraction: float = Field(default=0.3, gt=0, le=1)
    risk_fraction: float = Field(default=0.01, gt=0, le=0.1)
    total_risk_fraction: float = Field(default=0.05, gt=0, le=0.5)
    max_positions: int = Field(default=5, ge=1, strict=True)
    commission_rate: float = Field(default=0.001, ge=0, lt=0.1)
    spread_bps: float = Field(default=5, ge=0, lt=1000)
    slippage_bps: float = Field(default=2, ge=0, lt=1000)
    volume_participation: float = Field(default=0.01, gt=0, le=1)


def portfolio(datasets, signals, sectors, settings, records, start_at, mode="controlled"):
    if mode not in ("controlled", "technical_only", "buy_and_hold"):
        raise ValueError("Unknown research mode")
    symbols = sorted(datasets)
    if not symbols or set(symbols) != set(signals) or set(symbols) != set(sectors):
        raise ValueError("Matching instrument, signal and sector scopes required")
    validate_replay(records)
    grid = datasets[symbols[0]].bars.index
    timeframe = datasets[symbols[0]].spec.timeframe_seconds
    for symbol in symbols:
        data = datasets[symbol]
        if data.spec.symbol != symbol or not sectors[symbol]:
            raise ValueError("Symbol/sector metadata mismatch")
        if not data.bars.index.equals(grid) or data.spec.timeframe_seconds != timeframe:
            raise ValueError("Portfolio requires identical grids/timeframes; no silent resampling")
        if not signals[symbol].index.equals(grid):
            raise ValueError("Signal grid mismatch")
        if data.spec.asset_class in ("stock", "etf") and data.spec.price_basis == "unadjusted":
            raise ValueError("Raw equity actions must be normalized before research")
    if not grid.is_monotonic_increasing or not grid.is_unique or grid.tz is None:
        raise ValueError("Unique ordered aware timestamps required")
    if any((grid[1:] - grid[:-1]).total_seconds() < timeframe):
        raise ValueError("Overlapping portfolio bars")
    start = grid.searchsorted(pd.Timestamp(start_at))
    if start < 1 or len(grid) - start < 4:
        raise ValueError("Need preceding history and at least four evaluation bars")
    if any(not bool(signals[s].iloc[start].ready) for s in symbols):
        raise ValueError("Portfolio indicator warm-up incomplete")
    cash, positions, pending, trades, audit, curve, bought = (
        settings.cash,
        {},
        {},
        [],
        [],
        [],
        set(),
    )
    fee = settings.commission_rate
    spread = settings.spread_bps / 10000
    slip = settings.slippage_bps / 10000

    def sell(symbol, quantity, reference, at, reason):
        nonlocal cash
        p = positions[symbol]
        price = reference * (1 - slip)
        proceeds = quantity * price * (1 - fee)
        cash += proceeds
        trades.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "entry_at": p["at"],
                "exit_at": at.isoformat(),
                "entry_unit_cost": p["unit_cost"],
                "exit_unit_proceeds": price * (1 - fee),
                "pnl_after_costs": proceeds - quantity * p["unit_cost"],
                "reason": reason,
            }
        )
        p["quantity"] -= quantity
        if p["quantity"] == 0:
            del positions[symbol]
            pending.pop(symbol, None)

    for i in range(start, len(grid)):
        at = grid[i]
        opened = at - pd.Timedelta(seconds=timeframe)
        bars = {s: datasets[s].bars.iloc[i] for s in symbols}
        used = {s: 0 for s in symbols}
        capacity = {
            s: math.floor(
                float(datasets[s].bars.iloc[i - 1].Volume) * settings.volume_participation
            )
            for s in symbols
        }
        # Pending exits first; no pending sale frees cash before its actual fill.
        for symbol in symbols:
            if pending.get(symbol) == "SELL" and symbol in positions:
                qty = min(positions[symbol]["quantity"], capacity[symbol])
                if qty:
                    sell(symbol, qty, float(bars[symbol].Open), opened, "SIGNAL_OR_BOUNDARY")
                    used[symbol] += qty
                if symbol not in positions:
                    pending.pop(symbol, None)
        for symbol in symbols:
            if pending.get(symbol) != "BUY":
                continue
            pending.pop(symbol)
            blockers, refs = replay_gate(records, symbol, opened)
            if mode == "controlled" and blockers:
                audit.append(
                    {
                        "at": opened.isoformat(),
                        "symbol": symbol,
                        "blocked": blockers,
                        "evidence": refs,
                    }
                )
                continue
            if len(positions) >= settings.max_positions or symbol in positions:
                continue
            prior = signals[symbol].iloc[i - 1]
            stop = float(datasets[symbol].bars.iloc[i - 1].Close) - float(prior.atr) * float(
                prior.stop_atr
            )
            price = float(bars[symbol].Open) * (1 + spread + slip)
            if mode != "buy_and_hold" and (not math.isfinite(stop) or not 0 < stop < price):
                continue
            equity = cash + sum(p["quantity"] * float(bars[s].Open) for s, p in positions.items())
            sector_value = sum(
                p["quantity"] * float(bars[s].Open)
                for s, p in positions.items()
                if sectors[s] == sectors[symbol]
            )
            budget = min(
                cash,
                equity * settings.position_fraction,
                max(0, equity * settings.sector_fraction - sector_value),
            )
            qty = min(math.floor(budget / (price * (1 + fee))), capacity[symbol] - used[symbol])
            if mode != "buy_and_hold":
                risk_unit = price * (1 + fee) - stop * (1 - slip) * (1 - fee)
                open_risk = sum(
                    max(0, float(bars[s].Open) - p["stop"] * (1 - slip)) * p["quantity"]
                    for s, p in positions.items()
                )
                available_risk = max(0, equity * settings.total_risk_fraction - open_risk)
                qty = min(
                    qty,
                    math.floor(min(equity * settings.risk_fraction, available_risk) / risk_unit),
                )
            if qty <= 0:
                continue
            cash -= qty * price * (1 + fee)
            positions[symbol] = {
                "quantity": qty,
                "unit_cost": price * (1 + fee),
                "stop": stop,
                "peak": float(bars[symbol].Open),
                "at": opened.isoformat(),
            }
            bought.add(symbol)
            used[symbol] += qty
            audit.append(
                {
                    "at": opened.isoformat(),
                    "symbol": symbol,
                    "entry_quantity": qty,
                    "evidence": refs,
                }
            )
        # Gap-aware stops are active on the entry bar. Lagged-volume proxy is a shared capacity cap.
        if mode != "buy_and_hold":
            for symbol in list(positions):
                p, bar = positions[symbol], bars[symbol]
                if float(bar.Low) <= p["stop"]:
                    qty = min(p["quantity"], capacity[symbol] - used[symbol])
                    if qty:
                        sell(
                            symbol,
                            qty,
                            min(float(bar.Open), p["stop"]),
                            opened if float(bar.Open) <= p["stop"] else at,
                            "STOP",
                        )
                        used[symbol] += qty
                    if symbol in positions:
                        pending[symbol] = "SELL"
        equity = cash + sum(p["quantity"] * float(bars[s].Close) for s, p in positions.items())
        if cash < -1e-7 or not math.isfinite(equity):
            raise ValueError("Invalid cash/equity reconciliation")
        curve.append({"at": at.isoformat(), "cash": cash, "equity": equity})
        if i == len(grid) - 1:
            break
        for symbol in symbols:
            signal = signals[symbol].iloc[i]
            if symbol in positions and mode != "buy_and_hold":
                p = positions[symbol]
                p["peak"] = max(p["peak"], float(bars[symbol].High))
                p["stop"] = max(p["stop"], p["peak"] - float(signal.trail_atr) * float(signal.atr))
                if mode == "controlled":
                    blockers, refs = replay_gate(records, symbol, at)
                    if blockers:
                        audit.append(
                            {
                                "at": at.isoformat(),
                                "symbol": symbol,
                                "holding_review_required": blockers,
                                "evidence": refs,
                            }
                        )
            if i >= len(grid) - 2:
                if symbol in positions:
                    pending[symbol] = "SELL"
                else:
                    pending.pop(symbol, None)
            elif symbol in positions:
                if mode != "buy_and_hold" and bool(signal.exit):
                    pending[symbol] = "SELL"
            elif bool(signal.ready) and (
                bool(signal.entry) if mode != "buy_and_hold" else symbol not in bought
            ):
                pending[symbol] = "BUY"
    values = [settings.cash] + [p["equity"] for p in curve]
    peak, maximum_drawdown = values[0], 0
    for value in values:
        peak = max(peak, value)
        maximum_drawdown = max(maximum_drawdown, (peak - value) / peak)
    gains = sum(max(0, t["pnl_after_costs"]) for t in trades)
    losses = -sum(min(0, t["pnl_after_costs"]) for t in trades)
    return {
        "mode": mode,
        "authorized": False,
        "initial_cash": settings.cash,
        "final_equity": values[-1],
        "return_percent": (values[-1] / settings.cash - 1) * 100,
        "maximum_drawdown_percent": maximum_drawdown * 100,
        "profit_factor": gains / losses if losses else None,
        "expectancy_cash_after_costs": sum(t["pnl_after_costs"] for t in trades) / len(trades)
        if trades
        else None,
        "open_positions": len(positions),
        "pending_orders": len(pending),
        "trade_count": len(trades),
        "trades": trades,
        "audit": audit,
        "equity_curve": curve,
        "settlement_model": "instant simulated cash reuse; not a real settled-cash ledger",
        "liquidity_model": "previous completed bar volume participation proxy; no depth/queue or guaranteed current liquidity",
        "priority": "exits then buys in sorted symbol order; no retroactive fill at signal close",
    }
