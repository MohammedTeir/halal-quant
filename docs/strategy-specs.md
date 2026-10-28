# Strategy specifications

Status: three Pine v6 drafts exist. TradingView compilation, replay, exports and
cross-platform parity remain pending. All positions are simulated, long-only,
with pyramiding disabled. No research performance gate has been demonstrated.

| Setting | Stocks | ETFs | Gold |
|---|---|---|---|
| Script | `pine/stocks/adaptive_pullback.pine` | `pine/etfs/regime_trend.pine` | `pine/gold/breakout_retest.pine` |
| Recommended chart | 4H / 1D | 1D / 1W | 1H / 4H |
| Trend | EMA50 > EMA200, close > EMA200 | Close > SMA200, rising over 20 bars | Previous completed higher-timeframe EMA50 > EMA200 |
| Trigger | Prior bar touches EMA20 or EMA50 tolerance; RSI14 crosses above 50 | Trend and regime filters satisfied | Close crosses previous 20-bar Donchian high; optional subsequent-bar retest |
| Confirmation | Bullish recovery candle, ADX14 >= 20, volume > SMA20 volume | Confirmed benchmark close > benchmark SMA200 | ADX14 >= 20 |
| Volatility filter | ATR-based pullback tolerance | ATR14 / close <= 4% | ATR14 / close <= 3% |
| Additional defaults | Pullback tolerance 0.5 ATR, volume multiplier 1 | Benchmark AMEX:SPY; regime timeframe D | Trend timeframe D; retest enabled, expiry 5 bars, tolerance 0.25 ATR |
| Trend exit | Close < EMA200 or EMA50 < EMA200 | Two consecutive closes below SMA200 | Confirmed higher-timeframe EMA50 <= EMA200 |

Shared defaults: ATR14 initial stop 2 ATR, trailing stop 3 ATR, 10% simulated
equity allocation, initial capital 10,000, commission 0.10%, slippage 2 ticks,
and date range 2020-01-01 through 2035-01-01 UTC. Indicator and stop settings
are inputs; costs and allocation are editable through Strategy Properties.
Date end prevents entries and requests closure of existing simulated positions.

Signals use confirmed chart closes. Market entries fill on the next available
simulation tick; the signal close is not a promised fill. Stops are attached to
pending entries and trail prospectively without loosening. Warm-up and missing
indicator values prevent early entries. See [Pine acceptance](pine-validation.md)
for timeframe restrictions, indicator seeding differences and alert semantics.

Backend requirements still to implement: point-in-time screening, earnings/news
and macro windows, gold custody/possession verification, portfolio risk sizing,
owned/sellable quantities, and order authorization. Pine signals cannot provide
those approvals. The shared v1 candidate contract includes strategy version,
symbol, timeframe, UTC bar close, price and candidate action.
