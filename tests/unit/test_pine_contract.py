"""Source guardrails only; these checks cannot compile or execute Pine Script."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from packages.schemas.signals import Signal

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("folder", "strategy", "asset"),
    [
        ("stocks", "adaptive_pullback", "stock"),
        ("etfs", "regime_trend", "etf"),
        ("gold", "breakout_retest", "gold"),
    ],
)
def test_source_guardrails_and_contract(folder, strategy, asset):
    source = (ROOT / "pine" / folder / f"{strategy}.pine").read_text()
    assert source.startswith("//@version=6")
    assert 'strategy.entry("Long", strategy.long' in source
    assert "strategy.short" not in source
    assert "pyramiding=0" in source
    assert "calc_on_every_tick=false" in source
    assert "process_orders_on_close=false" in source
    assert "barstate.isconfirmed" in source
    assert "stop=stopPrice" in source
    assert "commission_value=0.10" in source
    assert "slippage=2" in source
    # Extract the actual JSON concatenation template used by the script.
    line = next(line.strip() for line in source.splitlines() if line.strip().startswith("'{"))
    line = line.replace("' + eventId + '", f"{strategy}|NASDAQ:EXAMPLE|240|123|ENTRY_CANDIDATE")
    line = line.replace("' + syminfo.tickerid + '", "NASDAQ:EXAMPLE")
    line = line.replace("' + timeframe.period + '", "240")
    line = line.replace("' + action + '", "ENTRY_CANDIDATE")
    line = line.replace("' + stamp + '", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    line = line.replace("' + str.tostring(close, format.mintick) + '", "100.25")
    signal = Signal.model_validate_json(line[1:-1])
    assert signal.strategy == strategy
    assert signal.asset_class == asset
