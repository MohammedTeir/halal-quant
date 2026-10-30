"""Fixed-parameter chronological validation, without tuning or order authority."""

import hashlib
import importlib.metadata
import json
from dataclasses import replace
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from services.backtesting.engine import simulate, source_hash
from services.technical_signals.strategies import features


class WalkForwardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    initial_history_bars: int = Field(ge=10, strict=True)
    test_bars: int = Field(ge=4, strict=True)
    final_holdout_bars: int = Field(ge=4, strict=True)


def walk_forward(dataset, config, settings, plan, benchmark=None, candidates=None):
    if settings.start_at is not None or settings.end_at is not None:
        raise ValueError("Walk-forward uses explicit bar partitions; omit run start/end dates")
    if candidates and any(c.name != config.name for c in candidates):
        raise ValueError("Candidate family must match requested strategy")
    bars = dataset.bars
    development_end = len(bars) - plan.final_holdout_bars
    if development_end - plan.initial_history_bars < plan.test_bars:
        raise ValueError("Need at least one full development test and a final holdout")
    # Partial trailing development periods are excluded explicitly, never folded
    # into the final holdout or silently given different test lengths.
    starts = list(
        range(plan.initial_history_bars, development_end - plan.test_bars + 1, plan.test_bars)
    )
    windows = [("development", start, start + plan.test_bars) for start in starts]
    windows.append(("final_holdout", development_end, len(bars)))
    results = []
    for kind, start, end in windows:
        prefix = replace(dataset, bars=bars.iloc[:end].copy())
        reference = (
            replace(benchmark, bars=benchmark.bars.loc[: prefix.bars.index[-1]].copy())
            if benchmark is not None
            else None
        )
        chosen, selection = config, None
        if candidates:
            from services.backtesting.selection import select_parameters

            training = replace(dataset, bars=bars.iloc[:start].copy())
            training_reference = (
                replace(benchmark, bars=benchmark.bars.loc[: training.bars.index[-1]].copy())
                if benchmark is not None
                else None
            )
            chosen, selection = select_parameters(
                training, candidates, settings, training_reference
            )
        signals = features(prefix, chosen, reference)
        first = prefix.bars.index[start]
        if not bool(signals.loc[first, "ready"]):
            raise ValueError("Initial history is insufficient for indicator warm-up")
        runs = {
            name: simulate(prefix.bars, signals, chosen, settings, first, baseline=baseline)
            for name, baseline in [("strategy", False), ("buy_and_hold", True)]
        }
        if any(run["open_positions"] or run["pending_orders"] for run in runs.values()):
            raise ValueError("Unreconciled validation window")
        results.append(
            {
                "kind": kind,
                "selection": selection,
                "strategy_configuration": chosen.model_dump(mode="json"),
                "history_bars": start,
                "test_bars": end - start,
                "signal_start": first.isoformat(),
                "last_bar_close": prefix.bars.index[-1].isoformat(),
                **runs,
            }
        )
    provenance = {
        "schema_version": "1.0",
        "strategy": config.model_dump(mode="json"),
        "run_settings": settings.model_dump(mode="json"),
        "walk_forward_settings": plan.model_dump(mode="json"),
        "inputs": {
            "instrument": dataset.manifest(),
            "benchmark": benchmark.manifest() if benchmark else None,
        },
        "candidates": [c.model_dump(mode="json") for c in candidates] if candidates else None,
        "source_sha256": source_hash(),
        "lockfile_sha256": hashlib.sha256(
            (Path(__file__).resolve().parents[2] / "uv.lock").read_bytes()
        ).hexdigest(),
        "engine": {
            name: importlib.metadata.version(name) for name in ("backtesting", "numpy", "pandas")
        },
    }
    return {
        **provenance,
        "run_id": hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest(),
        "mode": "training_selected_walk_forward_research_only"
        if candidates
        else "fixed_parameter_walk_forward_research_only",
        "authorized_for_paper": False,
        "synthetic": dataset.spec.synthetic or bool(benchmark and benchmark.spec.synthetic),
        "parameter_selection": "historical prefix only; predeclared candidates; no holdout objective"
        if candidates
        else "none; one configuration fixed before all windows",
        "capital_policy": "independent windows reset cash; returns must not be summed as a portfolio",
        "holdout_policy": "final holdout excluded from development; no automatic pass/fail or selection",
        "execution": "next bar open; final bar reserved for liquidation; existing per-side cost model",
        "unused_development_bars": development_end - (starts[-1] + plan.test_bars),
        "windows": results,
    }
