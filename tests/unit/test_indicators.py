import pytest

from packages.indicators.core import adx, atr, ema, previous_donchian, rma, rsi, sma


def test_hand_calculated_moving_averages():
    assert sma([1, 2, 3, 4], 3) == [None, None, 2, 3]
    assert ema([1, 2, 3, 4], 3) == [1, 1.5, 2.25, 3.125]
    assert rma([1, 2, 3, 4], 3) == [None, None, 2, pytest.approx(8 / 3)]


def test_rsi_warmup_and_extremes():
    assert rsi([1, 2, 3, 4], 3) == [None, None, None, 100]
    assert rsi([4, 3, 2, 1], 3)[-1] == 0
    assert rsi([2, 2, 2, 2], 3)[-1] == 50
    assert rsi([1, 3, 2, 4], 3)[-1] == 80


def test_atr_includes_overnight_gap():
    assert atr([10, 14, 13], [8, 12, 10], [9, 13, 11], 2) == [None, 3.5, 3.25]


def test_adx_warmup_and_trend():
    values = list(range(1, 21))
    result = adx([v + 1 for v in values], values, [v + 0.5 for v in values], 3)
    assert result[:4] == [None] * 4
    assert result[4:] == [100.0] * 16
    assert adx([2] * 10, [1] * 10, [1.5] * 10, 3)[-1] == 0


def test_donchian_excludes_current_bar():
    assert previous_donchian([1, 2, 100, 3], 2) == [None, None, 2, 100]


@pytest.mark.parametrize("indicator", [sma, ema, rma, rsi, previous_donchian])
def test_no_future_leakage(indicator):
    values = [10, 11, 9, 14, 13, 15, 12, 20, 18]
    full = indicator(values, 3)
    for end in range(len(values) + 1):
        assert indicator(values[:end], 3) == full[:end]


@pytest.mark.parametrize("indicator", [atr, adx])
def test_ohlc_no_future_leakage(indicator):
    close = [10, 11, 9, 14, 13, 15, 12, 20, 18]
    high, low = [x + 2 for x in close], [x - 2 for x in close]
    full = indicator(high, low, close, 3)
    for end in range(len(close) + 1):
        assert indicator(high[:end], low[:end], close[:end], 3) == full[:end]


def test_bad_data_rejected():
    with pytest.raises(ValueError):
        sma([1], 0)
    with pytest.raises(ValueError):
        ema([float("nan")], 3)
    with pytest.raises(ValueError):
        atr([1], [2], [1.5])
    with pytest.raises(ValueError):
        atr([1], [], [])
