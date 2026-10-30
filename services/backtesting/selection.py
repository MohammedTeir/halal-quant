"""Deterministic parameter selection using only a historical training prefix."""

from services.backtesting.engine import simulate
from services.technical_signals.strategies import features


def select_parameters(dataset, candidates, settings, benchmark=None):
    if not candidates or len(candidates) > 50:
        raise ValueError("Provide one to fifty predeclared candidate configurations")
    if len({c.name for c in candidates}) != 1:
        raise ValueError("Candidates must use one strategy family")
    results = []
    for index, candidate in enumerate(candidates):
        signals = features(dataset, candidate, benchmark)
        ready = signals.index[signals.ready]
        if len(ready) < 4:
            raise ValueError("Candidate training prefix lacks warm-up/evaluation history")
        result = simulate(dataset.bars, signals, candidate, settings, ready[0])
        eligible = (
            result["trade_count"] > 0 and result["open_positions"] == result["pending_orders"] == 0
        )
        results.append(
            {
                "candidate_index": index,
                "eligible": eligible,
                "return_percent": result["return_percent"],
                "trade_count": result["trade_count"],
            }
        )
    eligible = [r for r in results if r["eligible"]]
    if not eligible:
        raise ValueError("No candidate has a reconciled training trade")
    winner = max(eligible, key=lambda r: (r["return_percent"], -r["candidate_index"]))
    return candidates[winner["candidate_index"]], {
        "objective": "training net return after costs; ties choose earlier declared candidate",
        "training_last_bar_close": dataset.bars.index[-1].isoformat(),
        "selected_index": winner["candidate_index"],
        "candidates": results,
    }
