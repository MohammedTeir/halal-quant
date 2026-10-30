# Risk policy specification

Status: **Decimal sizing, versioned risk state/policies, durable kill switch and serialized research reservations implemented**. See [current Milestone 5 workflow](milestone-5-operations.md). Actual order/settlement/execution authority remains unavailable.
The Python/Pine 10% simulated allocation is a research setting, not enforcement of this policy.
The Python research adapter uses whole shares and cash-only margin, but these
local constraints do not implement the portfolio limits below.

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
exit cases. The preview uses explicit New York loss-day, day-start/peak-equity and 60-minute cooldown conventions; authoritative valuation/history and broker integration remain required before operational use. Critical live risk-limit changes
require human approval under the blueprint.
