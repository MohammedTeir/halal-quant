"""Explicit research gates and seeded fixed-PnL trade-order sensitivity."""

import math
import random


def monte_carlo(pnls, cash, *, iterations=1000, seed=0):
    if not math.isfinite(cash) or cash <= 0 or not 1 <= iterations <= 10000:
        raise ValueError("Invalid Monte Carlo cash or iteration count")
    if any(not math.isfinite(p) for p in pnls):
        raise ValueError("Nonfinite trade PnL")
    if not pnls:
        return {"status": "INSUFFICIENT_TRADES", "seed": seed, "iterations": iterations}
    rng, drawdowns, ruined = random.Random(seed), [], 0
    for _ in range(iterations):
        order = list(pnls)
        rng.shuffle(order)
        equity = peak = cash
        dd = 0
        ruin = False
        for pnl in order:
            equity += pnl
            peak = max(peak, equity)
            dd = max(dd, (peak - equity) / peak * 100)
            ruin |= equity <= 0
        drawdowns.append(dd)
        ruined += ruin
    drawdowns.sort()
    return {
        "status": "COMPLETED",
        "seed": seed,
        "iterations": iterations,
        "maximum_drawdown_p50_percent": drawdowns[int(0.5 * (iterations - 1))],
        "maximum_drawdown_p95_percent": drawdowns[int(0.95 * (iterations - 1))],
        "ruin_fraction": ruined / iterations,
        "terminal_cash": cash + math.fsum(pnls),
        "limitation": "fixed realized cash PnL permutation, not compound sizing, liquidity or overlapping-position replay",
    }


def research_gates(runs, *, representative_history_verified=False, pit_sources_verified=False):
    if not runs:
        raise ValueError("Out-of-sample windows required")
    checks = {
        "positive_expectancy_each_window": all(
            r["expectancy_cash_after_costs"] is not None and r["expectancy_cash_after_costs"] > 0
            for r in runs
        ),
        "profit_factor_above_1_3_each_window": all(
            r["profit_factor"] is not None and r["profit_factor"] > 1.3 for r in runs
        ),
        "drawdown_below_15_each_window": all(r["maximum_drawdown_percent"] < 15 for r in runs),
        "positive_return_multiple_periods": len(runs) >= 2
        and all(r["return_percent"] > 0 for r in runs),
        "no_unreconciled_orders": all(
            r["open_positions"] == r["pending_orders"] == 0 for r in runs
        ),
        "representative_history_independently_verified": representative_history_verified is True,
        "pit_sources_independently_verified": pit_sources_verified is True,
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "authorized": False,
        "lookahead_and_compliance_assurance": "Not inferred from PnL; requires provenance review and independent causal/control tests",
    }
