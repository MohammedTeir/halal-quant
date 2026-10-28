# Risk policy specification

Status: **requirements only; portfolio risk and order sizing are not implemented**.
Pine's 10% simulated allocation is a research setting, not enforcement of this policy.

| Initial limit | Default |
|---|---|
| Risk per trade | 0.5% equity |
| Aggregate open-position risk | 3% equity |
| Single position allocation | 10% equity |
| Sector exposure | 25% equity |
| Daily realized loss guard | 2% equity |
| Portfolio drawdown guard | 10% |
| Consecutive-loss cooldown | 3 losses |
| Stale required data | Block new entries |
| Broker unavailable | Block new entries |

For a long candidate with entry above a positive stop, whole-share sizing must be
bounded by the risk budget divided by stop distance, available cash after costs,
single-position capacity, and remaining portfolio/sector limits. Round down; reject
zero quantity and invalid prices. Pending orders/reservations and current holdings
must consume capacity. Slippage and gaps can exceed planned stop risk.

Daily loss guards, cooldowns, entry windows and kill switches must block new risk
without preventing protective exits or liquidation of owned sellable holdings.
Recheck prices, cash, ownership and limits at order authorization; a candidate's
historical approval cannot substitute for current broker/account evidence.

Milestone 5 acceptance includes boundary sizing, insufficient cash, pending-order
capacity, portfolio/sector caps, stale data, disconnected broker and owned protective
exit cases. Reset timing, valuation conventions and cooldown duration must be made
explicit before implementing those policies. Critical live risk-limit changes
require human approval under the blueprint.
