# Optional Pine strategies and acceptance protocol

Python is now the primary acceptance path; these TradingView checks are optional
and do not block development. See [Python research](python-research.md).

## Implementation

Each standalone v6 strategy is long-only, pyramiding disabled, evaluates signals
on confirmed chart closes, and simulates entry at the next available tick
(normally next bar open). Default commission is 0.10% and slippage 2 ticks;
change these in TradingView Strategy Properties to match actual assumptions.
Default simulated allocation is 10% of equity. It is not risk-engine sizing and
may produce fractional quantities unsuitable for a broker.

Stock: EMA50/200 trend, prior-bar pullback toward EMA20/50, RSI recovery, ADX and
volume confirmation. ETF: SMA200 with positive slope, confirmed benchmark trend,
ATR volatility cap. Gold: confirmed higher-timeframe EMA50/200, previous Donchian
high, ADX and volatility filter, optional subsequent-bar retest with expiry.

All scripts attach an ATR stop to the pending entry; once owned in the simulation,
a high-water-mark ATR trailing stop can only tighten. Trend deterioration and the
end date close existing simulated positions. End dates prevent new entries but do
not suppress exits. Stops can gap and fill worse than planned. Trailing stop updates
occur at chart close and take effect prospectively; they cannot retroactively
protect an earlier intrabar low.

ETF regime timeframe must be >= chart timeframe (set it to W on a weekly chart).
Gold trend timeframe must be strictly higher than chart timeframe. Higher-timeframe
requests deliberately use **previous completed values with `[1]` and
`lookahead_on`**; this combination avoids leaking future higher-timeframe closes.
Donchian uses `[1]` to exclude the breakout bar. Avoid nonstandard synthetic charts.
No intrabar calculation or fill recalculation is enabled.

Python reference indicators have explicit seeds and warm-ups: EMA starts from the
first observation; RMA uses an SMA seed; RSI needs period+1 closes; ADX uses an
initial zero directional movement and needs 2*period-1 bars. Pine native indicators
may differ during initialization, particularly DMI. Exact cross-platform numeric
parity is **not yet verified**; compare exported chart fixtures before using Python
calculations to reproduce TradingView performance.

## Alerts and trust boundary

Create an alert for **alert() function calls only**. Built-in strategy order-fill
alerts are disabled to prevent confusing candidates with authorizations. Payloads
follow [signal-v1.schema.json](contracts/signal-v1.schema.json). `bar_time` is the
closed signal bar's UTC close, and `price` is its close, not an execution fill.
Exit candidate alerts report a simulated transition to flat at the next chart
close; the payload is an observation, not the stop's actual fill price or time.

TradingView cannot send this API's custom `X-Webhook-Key` header directly. A trusted
TLS gateway must authenticate TradingView via an opaque endpoint credential,
remove that credential from logs, and forward the JSON with `X-Webhook-Key`.
The gateway is not implemented in this increment. Do not place secrets in Pine,
open this API unauthenticated, or claim direct TradingView delivery is validated.

Earnings, economic events, news freshness, screening, gold possession, sellable
ownership and portfolio sizing are **backend gates deferred to Milestones 3–5**.
These scripts intentionally emit unapproved candidates. Local research entries
are independent of those gates and do not establish permissible deployment.

## Manual acceptance — pending

This environment has no TradingView compiler or chart session. For each script:

1. Paste into TradingView Pine Editor, select v6, compile and add to a standard
   candlestick chart (stock 4H/1D, ETF 1D/1W, gold 1H/4H). Save compiler evidence.
2. Confirm nonzero trades on a sufficiently long sample, all long entries, no
   pyramiding, sensible warm-up, date controls and configurable cost effects.
3. Inspect a gap through a stop, initial protection, trailing tightening, trend
   exit and end-date exit. Confirm event restrictions cannot suppress protection.
4. Use Bar Replay and chart reload to compare candidate timestamps; inspect the
   higher-timeframe boundary and verify prior-bar data stays unchanged.
5. Check gold retests occur after breakout, expire, and invalidate below the
   configured tolerance. Check invalid timeframe settings fail explicitly.
6. Capture all three alert JSON payloads, schema-validate, test gateway authentication
   and replay behavior, and compare exported indicators with Python reference data.

Record symbols, data provider, timeframe, script version, property settings, test
period and results. No compile, non-repainting, performance, or compliance claim
is accepted merely because source guardrails pass. Historical and forward research
gates in the blueprint remain outstanding.
