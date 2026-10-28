# Python strategy research

Python is the primary strategy acceptance path. TradingView and the existing Pine
scripts are optional visual tools; their compilation and numeric parity remain
unverified. This updates the first-deliverable plan in the original blueprint.

## Reproduce all three runs for free, locally

From the repository root, after `uv sync --frozen`:

```sh
export UV_CACHE_DIR=/tmp/halal-quant-uv-cache
uv run python -m scripts.generate_research_demo --output data/demo
uv run python -m services.backtesting.cli --strategy adaptive_pullback \
  --csv data/demo/stock.csv --metadata data/demo/stock.json \
  --output reports/generated/stock.json
uv run python -m services.backtesting.cli --strategy regime_trend \
  --csv data/demo/etf.csv --metadata data/demo/etf.json \
  --benchmark-csv data/demo/benchmark.csv --benchmark-metadata data/demo/benchmark.json \
  --output reports/generated/etf.json
uv run python -m services.backtesting.cli --strategy breakout_retest \
  --csv data/demo/gold.csv --metadata data/demo/gold.json \
  --output reports/generated/gold.json
```

Demo generation and report creation refuse to overwrite existing files. Choose a
new directory/output path for another run. No API server, credentials, database,
TradingView account or market-data subscription is needed for these synthetic runs.
Demo prices, volumes and benchmark are deterministic **synthetic fixtures**. They
exercise the software and are not financial evidence, historical market data,
Shariah-screened instruments or performance acceptance. The gold demo's unadjusted
prices describe only a synthetic price series, not an owned gold contract.

Use `--strategy-config examples/research/stock-strategy.json` (or ETF/gold) and
`--run-config examples/research/run.json` for explicit versionable parameters.
The default run uses 10,000 USD, 10% allocation, 0.10% commission each side, 5 bps
spread and 2 bps adverse slippage charge each side. No optimizer is implemented.
Configurations reject unknown fields, invalid periods, non-finite numbers, invalid
dates and unsupported costs. Run `uv run pytest tests/backtesting -q` for acceptance.

## Historical CSV inputs

Replace demo paths with a CSV and its metadata JSON. Required columns, in order:

```csv
timestamp,Open,High,Low,Close,Volume
2024-01-02T21:00:00Z,100,102,99,101,1000000
2024-01-03T21:00:00Z,101,103,100,102,1100000
2024-01-04T21:00:00Z,102,104,101,103,1200000
```

This three-row illustration only shows format; strategy warm-up needs substantially
more history. Timestamps label **bar closes**, must carry a timezone, be unique and
strictly increasing, and are normalized to UTC. Do not pass vendor bar-open labels
without converting them using the source's actual session calendar. Do not blindly
add 24 hours to an exchange's daily bar-open label.

Metadata example:

```json
{
  "schema_version": "1.0",
  "source": "YOUR_VERIFIED_DATA_PROVIDER",
  "symbol": "EXAMPLE",
  "asset_class": "stock",
  "timeframe_seconds": 86400,
  "price_basis": "split_adjusted",
  "currency": "USD",
  "retrieved_at": "2026-10-28T12:00:00Z",
  "synthetic": false,
  "timestamp_semantics": "bar_close"
}
```

See [metadata schema](contracts/market-data-v1.schema.json). All OHLC values must
share the declared adjustment basis. The loader rejects unadjusted stocks/ETFs,
nonpositive/nonfinite prices, invalid OHLC bounds, negative/missing volume,
naive/duplicate/unsorted timestamps and overlapping bars. It records SHA-256 hashes
of CSV and metadata. Adjustment declarations are assertions from the supplier;
this loader does not independently reconstruct corporate actions or verify them.
It is not a live-feed freshness monitor. [Data ingestion](data-ingestion.md) now
provides separate versioned fact storage and split-adjustment audits; vendor
adapters, exchange calendars and verified real source data remain Milestone 3 work.

Stock timeframes: 4H or 1D. ETF: 1D or 1W (periods count chart bars, so a 200-period
weekly SMA covers 200 weeks). Gold: 1H or 4H. ETF requires a distinct ETF benchmark
with matching timeframe and adjustment basis. Exact close-time matching blocks
entries when benchmark data is missing; no stale values are forward-filled.

Gold chart closes must align to their declared fixed UTC grid. Higher-timeframe
periods use fixed UTC buckets (default 24 hours). Each bucket
must contain the expected number of chart bars; incomplete or missing buckets block
the context after their expected close. Only completed buckets may affect signals.
A completed bucket may be used at the chart close that completes it. This is causal
but intentionally does not promise Pine's previous-higher-bar timing parity.
Exchange-specific session calendars remain future work; verify suitability before
feeding real session-based gold data into this conservative continuous-bar model.

## Execution, dates and costs

Signals use only completed bars and prefix-stable indicators. Orders submitted on
a signal close fill at the **next bar open**, not retroactively at that close.
Report entry/exit timestamps are bar-close labels; they are not precise intrabar
execution timestamps. Whole-share quantities are rounded down. Margin is fixed at
1 (cash-funded), shorts and pyramiding are absent. Sizing is allocation-based,
not yet the blueprint's portfolio-risk sizing.

Initial ATR protection is attached to the pending entry. Stops can fill at a worse
open on a gap. Trailing updates use only the just-completed bar, apply prospectively,
and cannot loosen the existing stop. Candle data cannot resolve every intrabar
path or liquidity constraint. Stop-based losses may exceed planned risk.

Backtesting.py's spread model adjusts the entry price by the configured spread.
Commission is charged on entry and exit. Slippage is an additional adverse **cash
charge** on each side, combined with commission; it does not shift simulated fill
prices or trigger levels. The report's `commission_and_slippage` field combines
those charges. This is a transparent first cost model, not a full quote/order-book
or market-impact simulator. Volume participation constraints are not implemented.

`start_at`/`end_at` in the run config accept timezone-aware dates. Earlier input
history remains available for warm-up but cannot create positions before the
selected signal window. The chronological split is fixed before simulation
(default 70% train, 30% holdout); parameters are identical in both windows. Each
window starts flat with fresh cash. Never tune parameters against real holdout
results and then describe that same holdout as untouched.

The penultimate close in each window schedules liquidation, and the final bar
fills it at its open. No new entries are submitted at/after that liquidation close.
This avoids the engine's optional retroactive final-bar replay. Too-short windows
or insufficient training warm-up fail explicitly. The baseline buys once at the
same starting allocation and uses the same costs and liquidation boundary, without
technical stops. It is an exposure-matched baseline, not a 100%-invested benchmark.

## Reports and limitations

Each strict JSON report includes input hashes/provenance, dependency-lock hash,
source-code hash, engine versions, full configuration, stable run ID, chronological
windows, cash returns, drawdown, cash expectancy, profit factor, trade ledger,
entry candidates, stop ratchets, unfilled candidates, zero-sized candidates,
remaining orders/positions and engine warnings. Profit factor is null when there
are no losses, rather than nonstandard JSON Infinity. Zero trades produce null
expectancy and must not count as strategy validation.

Identical inputs, code, lock and settings produce byte-identical reports. Outputs
are not overwritten. The CLI does not send webhook events or create portfolio
orders. Its research version `2.0.0-python` is separate from Pine's `1.0.0` webhook
contract, which remains unchanged. Every report has `authorized_for_paper: false`.

A known upstream pandas deprecation warning about `DatetimeIndex.dayofweek` is
preserved in reports. It does not indicate a failed fill or failed test. Review
other warnings and unfilled candidates before interpreting results.

This increment does not complete portfolio backtesting, news publication/ingestion
replay, historical compliance, broker reconciliation, walk-forward optimization,
Monte Carlo, liquidity modeling, sample-size review or production promotion gates.
Backtesting.py is an AGPL-3.0 dependency; account for its license when distributing
or offering a modified service. Real provider selection and verified data are the
next prerequisites for meaningful historical research.
