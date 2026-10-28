"""Causal features evaluated at bar close. No order or compliance authorization."""

from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.indicators.core import adx, atr, ema, previous_donchian, rsi, sma
from services.market_data.csv_data import Dataset

StrategyName = Literal["adaptive_pullback", "regime_trend", "breakout_retest"]


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    name: StrategyName
    fast_period: int = Field(default=50, ge=2)
    slow_period: int = Field(default=200, ge=3)
    pullback_period: int = Field(default=20, ge=2)
    rsi_period: int = Field(default=14, ge=2)
    rsi_threshold: float = Field(default=50, gt=0, lt=100)
    adx_period: int = Field(default=14, ge=2)
    minimum_adx: float = Field(default=20, ge=0, le=100)
    volume_period: int = Field(default=20, ge=1)
    volume_multiplier: float = Field(default=1, gt=0)
    pullback_atr: float = Field(default=0.5, ge=0)
    slope_period: int = Field(default=20, ge=1)
    maximum_atr_percent: float = Field(default=3, gt=0)
    channel_period: int = Field(default=20, ge=2)
    higher_timeframe_hours: int = Field(default=24, ge=1)
    require_retest: bool = True
    retest_bars: int = Field(default=5, ge=1)
    retest_atr: float = Field(default=0.25, ge=0)
    atr_period: int = Field(default=14, ge=1)
    stop_atr: float = Field(default=2, gt=0)
    trail_atr: float = Field(default=3, gt=0)

    @model_validator(mode="after")
    def ordered_periods(self):
        if self.fast_period >= self.slow_period:
            raise ValueError("Fast period must be shorter than slow period")
        return self


def defaults(name: StrategyName) -> StrategyConfig:
    return StrategyConfig(name=name, maximum_atr_percent=4 if name == "regime_trend" else 3)


def _series(values, index):
    return pd.Series(np.array(values, dtype=float), index=index)


def _cross_above(left, right):
    return (left > right) & (
        left.shift(1) <= (right.shift(1) if isinstance(right, pd.Series) else right)
    )


def features(dataset: Dataset, config: StrategyConfig, benchmark: Dataset | None = None):
    """Prefix-stable output: adding future bars never changes earlier candidates."""
    bars, spec = dataset.bars, dataset.spec
    expected = {"adaptive_pullback": "stock", "regime_trend": "etf", "breakout_retest": "gold"}
    periods = {"stock": (14400, 86400), "etf": (86400, 604800), "gold": (3600, 14400)}
    if (
        spec.asset_class != expected[config.name]
        or spec.timeframe_seconds not in periods[spec.asset_class]
    ):
        raise ValueError("Strategy asset class or supported timeframe mismatch")
    if spec.asset_class in ("stock", "etf") and spec.price_basis == "unadjusted":
        raise ValueError("Raw equity prices may only be loaded for corporate-action audits")
    c = bars.Close
    a = _series(
        atr(bars.High.tolist(), bars.Low.tolist(), c.tolist(), config.atr_period), bars.index
    )
    strength = _series(
        adx(bars.High.tolist(), bars.Low.tolist(), c.tolist(), config.adx_period), bars.index
    )
    fast, slow = (_series(ema(c, p), bars.index) for p in (config.fast_period, config.slow_period))
    warm = pd.Series(
        np.arange(len(bars)) >= max(config.slow_period, 2 * config.adx_period), index=bars.index
    )
    context = pd.Series(True, index=bars.index)
    if config.name == "adaptive_pullback":
        pull = _series(ema(c, config.pullback_period), bars.index)
        oscillator = _series(rsi(c.tolist(), config.rsi_period), bars.index)
        average_volume = _series(sma(bars.Volume, config.volume_period), bars.index)
        touched = (bars.Low.shift(1) <= pull.shift(1) + a.shift(1) * config.pullback_atr) | (
            bars.Low.shift(1) <= fast.shift(1) + a.shift(1) * config.pullback_atr
        )
        entry = (
            (fast > slow)
            & (c > slow)
            & touched
            & _cross_above(oscillator, config.rsi_threshold)
            & (c > bars.Open)
            & (strength >= config.minimum_adx)
            & (bars.Volume > average_volume * config.volume_multiplier)
        )
        exit_signal = (c < slow) | (fast < slow)
    elif config.name == "regime_trend":
        if benchmark is None:
            raise ValueError("ETF strategy requires a separate benchmark dataset")
        if benchmark.spec.symbol == spec.symbol or benchmark.spec.asset_class != "etf":
            raise ValueError("Choose a distinct ETF benchmark instrument")
        if benchmark.spec.price_basis != spec.price_basis:
            raise ValueError("Benchmark and ETF price adjustment bases must match")
        if benchmark.spec.timeframe_seconds != spec.timeframe_seconds:
            raise ValueError("Benchmark timeframe must match ETF timeframe")
        trend = _series(sma(c, config.slow_period), bars.index)
        benchmark_trend = _series(
            sma(benchmark.bars.Close, config.slow_period), benchmark.bars.index
        )
        # Exact close-time join: absent/stale benchmark data cannot be forward-filled into approval.
        regime = (benchmark.bars.Close > benchmark_trend).reindex(bars.index, fill_value=False)
        context = regime
        warm &= np.arange(len(bars)) >= config.slow_period + config.slope_period
        entry = (
            (c > trend)
            & (trend > trend.shift(config.slope_period))
            & regime
            & (a / c * 100 <= config.maximum_atr_percent)
        )
        exit_signal = (c < trend) & (c.shift(1) < trend.shift(1))
    else:
        seconds = config.higher_timeframe_hours * 3600
        if seconds <= spec.timeframe_seconds or seconds % spec.timeframe_seconds:
            raise ValueError("Gold trend timeframe must be a higher multiple of chart timeframe")
        if (bars.index.as_unit("ns").asi8 % (spec.timeframe_seconds * 1_000_000_000)).any():
            raise ValueError("Gold bar closes must align to the declared fixed UTC timeframe")
        # Input timestamps are bar CLOSES. A group labelled t contains only closes <= t.
        # A partial higher-timeframe bucket is labelled in the future, so cannot join yet.
        grouped = c.resample(
            f"{config.higher_timeframe_hours}h", origin="epoch", closed="right", label="right"
        )
        buckets = grouped.last()
        higher = buckets.where(grouped.count() == seconds // spec.timeframe_seconds).dropna()
        hfast = _series(ema(higher, config.fast_period), higher.index)
        hslow = _series(ema(higher, config.slow_period), higher.index)
        hready = pd.Series(np.arange(len(higher)) >= config.slow_period, index=higher.index)
        trend = ((hfast > hslow) & hready).reindex(buckets.index, fill_value=False)
        trend = trend.reindex(bars.index, method="ffill").fillna(False)
        warm &= (
            hready.reindex(buckets.index, fill_value=False)
            .reindex(bars.index, method="ffill")
            .fillna(False)
        )
        context = trend
        channel = _series(previous_donchian(bars.High, config.channel_period), bars.index)
        breakout = _cross_above(c, channel)
        trigger = breakout.copy()
        if config.require_retest:
            trigger[:] = False
            level, pending = None, None
            for i in range(len(bars)):
                if pending is not None:
                    if (
                        i - pending > config.retest_bars
                        or c.iloc[i] < level - a.iloc[i] * config.retest_atr
                    ):
                        level, pending = None, None
                    elif (
                        i > pending
                        and bars.Low.iloc[i] <= level + a.iloc[i] * config.retest_atr
                        and c.iloc[i] > level
                    ):
                        trigger.iloc[i] = True
                        level, pending = None, None
                if breakout.iloc[i] and not trigger.iloc[i]:
                    level, pending = channel.iloc[i], i
        entry = (
            trend
            & trigger
            & (strength >= config.minimum_adx)
            & (a / c * 100 <= config.maximum_atr_percent)
        )
        exit_signal = ~trend
    return pd.DataFrame(
        {
            "entry": (entry & warm & (a > 0) & (c - config.stop_atr * a > 0)).fillna(False),
            "exit": exit_signal.fillna(False),
            "atr": a,
            "ready": warm & a.notna(),
            "context_allowed": context,
        },
        index=bars.index,
    )
