"""Independent chronological portfolio windows and declared cost stress scenarios."""

from dataclasses import replace

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.backtesting.portfolio import PortfolioConfig, portfolio
from services.backtesting.validation import monte_carlo, research_gates


class PortfolioValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    test_bars: int = Field(ge=4, strict=True)
    final_holdout_bars: int = Field(ge=4, strict=True)
    cost_multipliers: tuple[float, ...] = Field(default=(1, 2), min_length=1, max_length=5)

    @model_validator(mode="after")
    def costs(self):
        if any(not 1 <= value <= 10 for value in self.cost_multipliers):
            raise ValueError("Cost multipliers must be finite values from one to ten")
        if self.cost_multipliers[0] != 1 or len(set(self.cost_multipliers)) != len(
            self.cost_multipliers
        ):
            raise ValueError("Begin with the base-cost scenario and use unique multipliers")
        return self


def validate_portfolio(
    datasets, signals, sectors, settings, records, start_at, plan, *, seed=0, iterations=1000
):
    if not datasets:
        raise ValueError("Portfolio instruments required")
    if set(datasets) != set(signals) or set(datasets) != set(sectors):
        raise ValueError("Matching portfolio scopes required")
    grid = next(iter(datasets.values())).bars.index
    if any(not d.bars.index.equals(grid) for d in datasets.values()) or any(
        not f.index.equals(grid) for f in signals.values()
    ):
        raise ValueError("Full portfolio grids must match before slicing")
    first = int(grid.searchsorted(pd.Timestamp(start_at)))
    development_end = len(grid) - plan.final_holdout_bars
    if first < 1 or development_end - first < plan.test_bars:
        raise ValueError("Need history, a full development period and final holdout")
    starts = list(range(first, development_end - plan.test_bars + 1, plan.test_bars))
    windows = [("development", start, start + plan.test_bars) for start in starts]
    windows.append(("final_holdout", development_end, len(grid)))
    scenarios = []
    for multiplier in plan.cost_multipliers:
        raw = settings.model_dump()
        for key in ("commission_rate", "spread_bps", "slippage_bps"):
            raw[key] *= multiplier
        stress = PortfolioConfig.model_validate(raw)
        results = []
        for kind, start, end in windows:
            prefix = {s: replace(d, bars=d.bars.iloc[:end].copy()) for s, d in datasets.items()}
            frames = {s: f.iloc[:end].copy() for s, f in signals.items()}
            runs = {
                mode: portfolio(prefix, frames, sectors, stress, records, grid[start], mode)
                for mode in ("controlled", "technical_only", "buy_and_hold")
            }
            controlled = runs["controlled"]
            results.append(
                {
                    "kind": kind,
                    "signal_start": grid[start].isoformat(),
                    "last_bar_close": grid[end - 1].isoformat(),
                    "test_bars": end - start,
                    "runs": runs,
                    "monte_carlo": monte_carlo(
                        [t["pnl_after_costs"] for t in controlled["trades"]],
                        stress.cash,
                        seed=seed,
                        iterations=iterations,
                    ),
                }
            )
        scenarios.append(
            {
                "cost_multiplier": multiplier,
                "settings": stress.model_dump(),
                "windows": results,
                "gates": research_gates([w["runs"]["controlled"] for w in results]),
            }
        )
    return {
        "authorized": False,
        "selection": "none; portfolio configurations and cost scenarios fixed before all windows",
        "capital_policy": "each period resets cash; no sum of period returns or pooled trade-order samples",
        "unused_development_bars": development_end - (starts[-1] + plan.test_bars),
        "performance_accepted": all(s["gates"]["passed"] for s in scenarios),
        "scenarios": scenarios,
    }
