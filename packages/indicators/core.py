"""Causal, prefix-stable indicators. Missing warm-up values are None.

EMA uses a first-observation seed (TradingView convention); Wilder RMA uses
an SMA seed. ADX needs 2*period-1 bars, RSI needs period+1 closes.
"""

import math
from collections.abc import Sequence
from itertools import pairwise

Series = list[float | None]


def validate(values: Sequence[float], period: int):
    if period < 1:
        raise ValueError("Period must be positive")
    if any(not math.isfinite(v) for v in values):
        raise ValueError("Non-finite observation")


def sma(values: Sequence[float], period: int) -> Series:
    validate(values, period)
    return [
        None if i + 1 < period else sum(values[i - period + 1 : i + 1]) / period
        for i in range(len(values))
    ]


def ema(values: Sequence[float], period: int) -> Series:
    validate(values, period)
    result = []
    current = None
    alpha = 2 / (period + 1)
    for value in values:
        current = value if current is None else alpha * value + (1 - alpha) * current
        result.append(current)
    return result


def rma(values: Sequence[float], period: int) -> Series:
    validate(values, period)
    result: Series = [None] * len(values)
    if len(values) >= period:
        current = sum(values[:period]) / period
        result[period - 1] = current
        for i in range(period, len(values)):
            current = (current * (period - 1) + values[i]) / period
            result[i] = current
    return result


def rsi(closes: Sequence[float], period: int = 14) -> Series:
    validate(closes, period)
    changes = [b - a for a, b in pairwise(closes)]
    gains = rma([max(v, 0) for v in changes], period)
    losses = rma([max(-v, 0) for v in changes], period)
    result: Series = [None] if closes else []
    for gain, loss in zip(gains, losses):
        result.append(
            None
            if gain is None
            else 50.0
            if gain == loss == 0
            else 100.0
            if loss == 0
            else 100 - 100 / (1 + gain / loss)
        )
    return result


def true_range(highs, lows, closes):
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("OHLC lengths differ")
    for series in (highs, lows, closes):
        validate(series, 1)
    if any(low > close or close > high for high, low, close in zip(highs, lows, closes)):
        raise ValueError("Invalid OHLC bounds")
    return [
        high - low
        if i == 0
        else max(high - low, abs(high - closes[i - 1]), abs(low - closes[i - 1]))
        for i, (high, low) in enumerate(zip(highs, lows))
    ]


def atr(highs, lows, closes, period=14) -> Series:
    return rma(true_range(highs, lows, closes), period)


def adx(highs, lows, closes, period=14) -> Series:
    ranges = true_range(highs, lows, closes)
    plus, minus = [0.0] * len(ranges), [0.0] * len(ranges)
    for i in range(1, len(ranges)):
        up, down = highs[i] - highs[i - 1], lows[i - 1] - lows[i]
        plus[i] = up if up > down and up > 0 else 0.0
        minus[i] = down if down > up and down > 0 else 0.0
    tr, pos, neg = rma(ranges, period), rma(plus, period), rma(minus, period)
    dx = []
    for t, p, n in zip(tr, pos, neg):
        if t is not None:
            dx.append(0.0 if p + n == 0 else 100 * abs(p - n) / (p + n))
    return ([None] * min(period - 1, len(ranges))) + rma(dx, period)


def previous_donchian(highs: Sequence[float], period: int) -> Series:
    validate(highs, period)
    return [None if i < period else max(highs[i - period : i]) for i in range(len(highs))]
