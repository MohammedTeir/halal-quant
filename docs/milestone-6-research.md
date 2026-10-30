# Milestone 6: portfolio replay and research validation

This increment implements offline synchronous-grid portfolio research, historical
review/news/macro replay, training-only walk-forward parameter selection,
trade-order Monte Carlo and explicit research gates. Software verification and
strategy performance acceptance are separate. No result authorizes orders.

## Portfolio CLI

```bash
uv run python -m scripts.portfolio_smoke --output reports/generated/portfolio-demo
uv run python -m services.backtesting.portfolio_cli \
  --manifest reports/generated/portfolio-demo/manifest.json \
  --output reports/generated/portfolio-new-run.json
```

The first command creates fully synthetic CSVs and a manifest, including fictional
review/coverage evidence, runs controlled/technical-only/buy-and-hold comparisons,
then repeats portfolio and training-selected walk-forward runs byte-for-byte.
These fixtures are explicitly not human approvals or real performance evidence.

Manifest paths resolve relative to the manifest directory. Each instrument names
its CSV, metadata, sector and StrategyConfig; ETFs also require benchmark CSV and
metadata. Distinct symbols must share the same exact timestamp grid and timeframe.
Mixed calendars/frequencies are rejected, rather than silently forward-filled or
resampled. Run separate experiments for incompatible gold/equity grids.

The shared simulated cash account enforces whole long positions, available cash,
position/sector exposure, per-trade and total planned stop-risk budgets, maximum
position count and a shared liquidity capacity proxy. Exits fill before buys in
sorted-symbol order; a proposed sale does not release cash until filled. Caps
restrict new entries, not forced rebalancing after market movement. Stop losses
can exceed planned risk on gaps or illiquidity; no maximum realized loss guarantee
is implied. This is a research simulator, not the qualified controls authority.

Signals at completed bar close execute at the following bar's open. The simulator
models per-side commission/slippage and entry-side spread. Stops are gap-aware,
active on entry, and trailing levels update only after a completed bar for the
next bar. Intrabar stop time is unknown; non-gap stop exits use the bar-close
observation timestamp, not a fabricated exact intrabar time.

Liquidity uses the **previous completed bar's volume** times a configured
participation fraction. Current-bar total volume cannot size an order at its open.
This is a lagged liquidity proxy, not guaranteed contemporaneous market depth.
Entry/exit fills share that capacity. Unfilled exits remain pending; a final
boundary cannot fabricate liquidity or force a fictitious reconciled close.
The report retains unresolved positions/orders, and the research gate fails.

Cash proceeds are reused immediately in simulation. This deliberately does not
claim actual settled cash, borrow eligibility, allocated gold, corporate-action
cash accounting or broker compatibility. Adjusted-equity data is mandatory;
existing corporate-action audits and CSV provenance remain required. Adjustment
metadata alone does not prove a survivorship-free historical universe.

## Historical evidence replay

Each local research evidence revision has a unique ID, symbol scope (macro uses
`MARKET`), kind (`compliance`, `news`, `macro`), ALLOW/BLOCK, source SHA-256,
publication, receipt, effective and expiry times. It is a normalized historical
review/coverage decision, not an automatically inferred interpretation of raw news.
Both news absence coverage and event policies must be justified in the input data.

An entry needs all three current ALLOW records. Both publication and receipt must
be known by the simulated execution time. Later corrections cannot rewrite prior
visibility. The latest known effective revision wins, including expired or BLOCK
revisions; no fallback to older approval. Ambiguous same-scope/kind receipt ties
and duplicate IDs are rejected. New entries are revalidated at fill time. A newly
blocked existing holding is flagged for review without inventing a divestment
ruling. Historical local files cannot establish actual scholarly/source approval.

Technical-only and buy-and-hold bypass this replay as explicit counterfactual
baselines. They keep cash, exposure, liquidity and cost constraints, and never
confer authorization. Buy-and-hold enters once per symbol and has no strategy
stop; final boundary liquidation still applies.

## Walk-forward selection and untouched periods

Use the existing CLI with `--walk-forward-config` plus optional
`--candidate-configs` pointing to a predeclared StrategyConfig JSON array (1–50).
Candidates must belong to one strategy family. Without this option parameters
remain fixed, as in [the original walk-forward increment](walk-forward-research.md).

For each development test and the final holdout, candidates are scored only on
history ending strictly before that period. Highest net training return after
costs wins; ties choose the earlier declared candidate. Candidates without a
reconciled training trade are ineligible; no eligible candidate fails the run.
Selected parameters and all training scores are recorded before the subsequent
out-of-sample simulation. Final-holdout prices cannot affect its selection.
Windows reset capital and reserve their last bar for liquidation. No summed
window return is presented as continuous portfolio performance. This implements
single-instrument walk-forward selection; portfolio parameter selection is not
silently inferred from it. Repeated human inspection can contaminate a holdout;
freeze candidate sets/partitions and retain original reports before inspecting.

## Monte Carlo and acceptance

A seeded permutation of realized cash trade PnLs reports median/95th-percentile
path drawdown and ruin frequency. Terminal cash is invariant under permutation.
This measures trade-order sensitivity only: it does not replay overlapping
positions, dynamically compound sizes, or estimate market/regime probabilities.
Empty trades produce INSUFFICIENT_TRADES.

Research gates explicitly require positive net expectancy, profit factor >1.3,
maximum drawdown <15%, positive results across multiple out-of-sample periods,
no unresolved orders, and independent verification of representative history and
point-in-time evidence. A no-loss sample has undefined profit factor and does not
silently pass. Causality and compliance assurance require separate tests/review;
profitable PnL alone proves neither. The CLI keeps historical-source verification
false; no manifest boolean can turn synthetic evidence into verified history.

Full milestone performance acceptance remains pending representative verified
historical data and successful untouched out-of-sample gates. Failing results are
retained rather than promoted by changing thresholds. Paper execution and real
broker settlement/reconciliation remain milestone 8 work.

## Multi-period portfolio validation and cost stress

The manifest now optionally accepts:

```json
"validation": {
  "test_bars": 100,
  "final_holdout_bars": 200,
  "cost_multipliers": [1, 2]
}
```

`start_at` fixes the first development period. Development windows are disjoint;
the trailing final holdout is separate. Partial leftover development bars are
reported explicitly. All instrument/signal grids must match before slicing.
Each window resets cash and runs controlled, technical-only and buy-and-hold
comparisons. Costs are multiplied together (commission, spread and slippage);
portfolio constraints and the historical evidence remain fixed. Invalid stressed
cost configurations fail validation instead of being silently clipped. Seeded
trade-order Monte Carlo runs independently per window; samples from reset-cash
periods are never pooled as a continuous portfolio. Gates are evaluated across
all periods for each scenario. No scenario grants trading authority.

The synthetic CI fixture now reproduces these entire multi-period scenarios
byte-for-byte as part of the existing portfolio smoke acceptance.

## Actual 2025 gold history diagnostic

[The real-history diagnostic](../reports/milestone6-real-gold-diagnostic-2026-10-30.json)
checks all twelve normalized monthly CSV and metadata hashes against the prior
normalization audit and concatenates them without inserting missing bars. Both
1h and 4h datasets have zero eligible warm-up bars under the unchanged default
gold strategy: there are insufficient complete higher-timeframe observations for
its configured indicators. Both also contain unavailable-volume zero placeholders.
Thus technical walk-forward is blocked on indicator history; liquidity-aware
execution and historical compliance/news/macro coverage are unverified as well.

This is a failed eligibility diagnostic, not an untouched out-of-sample performance
claim. It neither substitutes smaller indicator periods nor fabricates volume to
make acceptance pass. Longer suitable history, validated sessions and credible
liquidity/evidence coverage are needed before a real performance experiment.
