### HALAL QUANT

Production-Grade Master System Blueprint · Version 2.0

System type: AI-assisted quantitative trading and portfolio intelligence platform Markets: Shariah-compliant stocks, ETFs, and physically or constructively owned gold Core technologies: TradingView Pine Script v6, Python, FastAPI, PostgreSQL, Next.js, Telegram Initial operating mode: Research, backtesting, paper trading, and alerts Future operating mode: Broker-integrated, ownership-verified live execution

This blueprint defines the system we should actually build: its architecture, modules, trading strategies, data flows, database, APIs, testing requirements, security controls, and implementation sequence.

The most important design decision is to separate trading intelligence from trading execution.

TradingView generates technical candidates. The backend evaluates news, macroeconomic conditions, compliance, and portfolio risk. The execution layer only acts on an approved decision.

### 1\. System objectives

HALAL QUANT — Design principles

Specification

Shariah first

Mandatory compliance gates

Profitable expectancy

Not win rate alone

Evidence-based AI

News assists, never overrides risk

Ownership aware

Never sell unowned assets

Test before trade

Historical and forward validation

Modular architecture

Independent and replaceable services

### Success criteria

A strategy is considered ready for paper deployment only if it demonstrates positive out-of-sample expectancy after costs, acceptable drawdown, adequate sample size, stable behavior across market regimes, and no critical compliance or data-integrity violations.

No specific win rate or return is guaranteed.

### 2\. Production system architecture

Next.js Dashboard

Market scanner · Portfolio · Strategy lab · Compliance · Analytics

FastAPI Gateway

Authentication · REST API · Webhooks · Access control

Signal Engine

Pine Script + Python

News Intelligence

News + LLM analysis

Macro Intelligence

Economic data + events

Compliance Engine

Shariah + ownership

Risk Engine

Sizing + exposure

Decision Engine

Signal fusion + policies

Research Engine

Backtest + optimization

Broker Adapter

Paper first; live later

PostgreSQL + Redis + Object Storage

Market history · Events · Decisions · Holdings · Audit trails

Telegram Alerts

Broker / Custodian

Architecture choice: Start as a modular monolith with independent background workers. Do not begin with microservices. This reduces deployment complexity, latency, and operational costs while preserving clear module boundaries.

### 3\. Trading strategy specifications

We will implement three independent strategies, all long-only.

| Configuration      | Stocks             | ETFs               | Gold               |
| ------------------ | ------------------ | ------------------ | ------------------ |
| Strategy           | Adaptive pullback  | Regime trend       | Breakout + retest  |
| Primary timeframe  | 4H / 1D            | 1D / 1W            | 1H / 4H            |
| Trend              | EMA 50/200         | SMA 200            | EMA 50/200         |
| Entry confirmation | RSI + ADX + volume | Trend + volatility | Donchian + ADX     |
| Stop model         | ATR                | ATR / trend exit   | ATR                |
| News focus         | Earnings + company | Macro + sector     | Fed + USD + yields |
| Position type      | Long only          | Long only          | Long only          |

### A. Stock strategy — Adaptive Trend Pullback

Entry candidate conditions:

* EMA 50 is above EMA 200.

* Price is above EMA 200.

* Price pulls back toward EMA 20 or EMA 50.

* RSI recovers above a configurable threshold.

* ADX confirms adequate trend strength.

* Volume confirms the recovery.

* No prohibited earnings/event window is active.

* The stock passes current Shariah screening.

Exit conditions include an ATR stop, trailing stop, trend deterioration, or a mandatory compliance review outcome.

### B. ETF strategy — Regime-Aware Trend Following

Entry candidate conditions:

* ETF price is above its 200-day SMA.

* The long-term moving-average slope is positive.

* The broader market regime is acceptable.

* Volatility and exposure limits permit a position.

* The ETF's holdings and fund structure meet the selected Shariah methodology.

Exit on trailing-stop breach, sustained trend deterioration, or a mandatory compliance event.

### C. Gold strategy — Trend-Aligned Breakout

Entry candidate conditions:

* Higher-timeframe trend is bullish.

* Price breaks a previous Donchian-channel high.

* ADX and volatility conditions confirm the setup.

* An optional retest confirms the breakout.

* High-impact economic event restrictions are clear.

* The execution instrument supports the required ownership and possession.

Important: XAUUSD chart signals do not establish that the traded instrument is halal. The gold execution adapter must separately verify the contract, custody, possession, settlement, and redemption structure.

### 4\. News, macroeconomic and AI intelligence

The intelligence layer must distinguish factual events from model-generated interpretations.

* Data acquisition

    Collect news headlines, article metadata, earnings announcements, economic calendars, official releases, and relevant market indicators.

* Normalization and deduplication

    Convert all timestamps to UTC, identify duplicate stories, preserve source attribution, and track original publication and ingestion times.

* Asset relevance mapping

    Match news to symbols, companies, industries, ETF holdings, and gold-related macroeconomic factors.

* LLM classification

    Produce structured assessments of sentiment, event type, severity, relevance, uncertainty, and supporting evidence.

* Deterministic decision policies

    Translate validated classifications into risk adjustments, event restrictions, or trade rejection.

### AI output contract

```json

{
  "schema_version": "1.0",
  "event_id": "evt_123",
  "symbol": "EXAMPLE",
  "event_type": "earnings",
  "sentiment": "negative",
  "sentiment_score": -0.65,
  "relevance": 0.95,
  "severity": "high",
  "confidence": 0.83,
  "source_ids": ["source_001"],
  "evidence": [
    "Reported revenue missed expectations"
  ],
  "market_impact": "uncertain",
  "recommended_policy": "REVIEW",
  "requires_human_review": true
}
```

All fields must be schema-validated. The model cannot invent sources, broker holdings, prices, compliance approvals, or execution permissions.

The AI output is advisory. The policy engine makes the final decision.

### News event rules

| Event                                  | Default behavior                                     |
| -------------------------------------- | ---------------------------------------------------- |
| Earnings within restricted window      | Block new stock entries                              |
| Major Fed announcement                 | Restrict gold and rate-sensitive entries             |
| CPI / employment release               | Restrict affected strategies temporarily             |
| Credible company-specific adverse news | Flag for review and reassess exposure                |
| Conflicting or unreliable news         | Reduce confidence; do not infer certainty            |
| Missing or stale news feed             | Fail closed for strategies requiring news validation |

Existing positions still require risk management during blocked entry windows. A news restriction should not automatically disable protective exits.

### 5\. Shariah compliance specification

The compliance subsystem is separate from the trading signal engine.

### Asset-level compliance

For stocks, store the issuer's business-activity screening, financial-ratio screening, methodology, provider, effective date, expiry date, and purification guidance.

For ETFs, validate the fund's investment mandate, holdings-screening process, structure, and applicable Shariah supervision rather than assuming every ETF is permissible.

For gold, require a documented instrument structure supporting ownership and immediate or qualifying constructive possession, consistent with the chosen scholarly standard.

### Transaction-level compliance

The engine must verify:

* Cash-funded purchase without interest-bearing margin.

* No short selling or share borrowing.

* No conventional CFD, futures, or options exposure.

* Actual position ownership and sellable quantity.

* No unsupported fractional-share or custody arrangement.

* Valid settlement and possession rules for the instrument.

* No automatic securities lending where prohibited by the selected compliance policy.

### Compliance state machine

APPROVED

PENDING

REJECTED

Only APPROVED assets can receive new buy authorization. PENDING and REJECTED assets are blocked from new purchases.

If an already-owned asset becomes noncompliant, the system flags it for review and applies the selected scholarly divestment policy. It must not assume that a newly prohibited asset should be held indefinitely or liquidated without considering the relevant ruling.

### 6\. Decision and risk engines

A trade must pass all mandatory gates before its opportunity score is considered.

```python
def evaluate_candidate(candidate, state):
    if not state.data_is_fresh:
        return "WAIT_DATA"

    if not state.asset_compliance_approved:
        return "BLOCK_COMPLIANCE"

    if not state.instrument_permitted:
        return "BLOCK_INSTRUMENT"

    if not state.news_policy_allows_entry:
        return "WAIT_EVENT"

    if not state.risk_limits_allow_entry:
        return "BLOCK_RISK"

    if candidate.score < state.minimum_score:
        return "WAIT_SIGNAL"

    return "BUY_CANDIDATE"
```

This is illustrative decision logic, not a complete executable engine. The production version must separately authorize the order using broker-verified cash, quantity, ownership, and current market conditions.

### Risk parameters

Position sizing calculator

Simulation

Portfolio equity ($)

Entry price ($)

Stop price ($)

Risk per trade0.5%

Shares

### 10

Capital used

### $1,000

Planned risk

### $50

Assumes whole shares, a 10% maximum single-position allocation, no other holdings, and no fees. Stops may execute at worse prices.

### Portfolio-level protections

| Policy                        | Initial default   |
| ----------------------------- | ----------------- |
| Maximum risk per trade        | 0.5%              |
| Maximum open-position risk    | 3%                |
| Maximum single position       | 10% of equity     |
| Maximum sector exposure       | 25%               |
| Maximum daily realized loss   | 2%                |
| Maximum portfolio drawdown    | 10%               |
| Consecutive-loss cooldown     | 3 losses          |
| Stale data                    | Block new entries |
| Broker connection unavailable | Block new entries |

These are configurable initial limits. A daily loss guard blocks new risk but must not prevent liquidation of owned holdings or broker-side protective orders.

### 7\. Database design

Use PostgreSQL as the primary system of record. Redis is optional for queues, locks, and short-lived caches.

| Domain       | Core tables                                                            |
| ------------ | ---------------------------------------------------------------------- |
| Identity     | users, roles, api_credentials                                          |
| Assets       | instruments, exchanges, corporate_actions                              |
| Market data  | ohlcv_bars, market_snapshots                                           |
| Strategies   | strategies, strategy_versions, strategy_parameters                     |
| Signals      | signals, signal_features, decisions                                    |
| Intelligence | news_events, news_sources, news_classifications, economic_events       |
| Compliance   | compliance_assessments, compliance_policies, purification_records      |
| Risk         | risk_policies, risk_snapshots, risk_violations                         |
| Portfolio    | accounts, cash_balances, positions, position_lots                      |
| Execution    | orders, order_events, fills, broker_reconciliations                    |
| Research     | backtest_runs, backtest_trades, optimization_runs, performance_metrics |
| Operations   | alerts, webhook_events, audit_logs, system_jobs                        |

Every decision should preserve the strategy version, data timestamps, feature values, model version, compliance decision, risk-policy version, and final explanation.

For reproducibility, historical news classifications must be versioned rather than silently overwritten when an AI model changes.

### 8\. API contracts

INITIAL REST API

POST

/api/v1/webhooks/tradingview

Receive and validate TradingView signals

GET

/api/v1/instruments

List eligible instruments

GET

/api/v1/signals

Retrieve candidate and approved signals

POST

/api/v1/decisions/evaluate

Evaluate a candidate using current policies

GET

/api/v1/news

Retrieve relevant news intelligence

GET

/api/v1/compliance/{instrument_id}

Read compliance evidence and status

GET

/api/v1/portfolio

Retrieve holdings, cash, and exposure

POST

/api/v1/backtests

Submit a research job

GET

/api/v1/backtests/{run_id}

Read backtest results

POST

/api/v1/paper/orders

Submit a paper order

GET

/api/v1/audit

Review authorized system activity

All state-changing endpoints require authorization, audit logging, and appropriate idempotency controls. Public webhook ingestion must be separated from authenticated dashboard APIs.

### 9\. Repository architecture

Use a monorepo with separate application, strategy, infrastructure, and test directories.

```text

halal-quant/
├── apps/
│   ├── dashboard/             # Next.js frontend
│   └── api/                   # FastAPI application
├── services/
│   ├── market_data/
│   ├── technical_signals/
│   ├── news_intelligence/
│   ├── macro_intelligence/
│   ├── compliance/
│   ├── decision_engine/
│   ├── risk_engine/
│   ├── portfolio/
│   ├── execution/
│   ├── backtesting/
│   └── notifications/
├── pine/
│   ├── stocks/
│   │   └── adaptive_pullback.pine
│   ├── etfs/
│   │   └── regime_trend.pine
│   ├── gold/
│   │   └── breakout_retest.pine
│   └── shared/
├── packages/
│   ├── schemas/
│   ├── indicators/
│   └── config/
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── backtesting/
│   ├── compliance/
│   └── security/
├── infra/
│   ├── docker/
│   ├── monitoring/
│   └── deployment/
├── docs/
│   ├── architecture.md
│   ├── strategy-specs.md
│   ├── compliance-policy.md
│   ├── risk-policy.md
│   ├── api-contracts.md
│   └── operations-runbook.md
├── .github/workflows/
├── .env.example
├── docker-compose.yml
└── README.md
```

### Deployment design

For development, Docker Compose can run the API, PostgreSQL, Redis, worker, and dashboard locally.

For production, separate the publicly accessible API from internal workers and the database. Use TLS, encrypted secrets, restricted database access, backups, structured logging, health checks, and deployment rollback procedures.

The first release does not need a live broker connection.

### 10\. Backtesting and validation requirements

We should use two independent testing layers.

TradingView Strategy Tester: Fast iteration on Pine Script entry and exit logic, visual inspection, and preliminary strategy metrics.

Python research engine: Portfolio-aware simulation, timestamped news integration, macroeconomic conditions, compliance history, fees, cash constraints, and reproducible experiments.

The Python backtester should model execution timing realistically, including the fact that a signal produced at a candle's close generally cannot be filled retroactively at an earlier price.

### Required tests

* No repainting or look-ahead bias.

* Correct indicator warm-up periods.

* Corporate actions and adjusted-price consistency.

* Realistic spread, commission, slippage, and liquidity assumptions.

* News publication and ingestion timing.

* Historical point-in-time compliance.

* Walk-forward optimization.

* Out-of-sample testing.

* Monte Carlo analysis of trade-order sensitivity.

* Buy-and-hold and technical-only baselines.

* Paper-trading reconciliation.

### Research acceptance criteria

| Metric                        | Initial research gate            |
| ----------------------------- | -------------------------------- |
| Out-of-sample expectancy      | Positive after costs             |
| Profit factor                 | Above 1.3                        |
| Maximum drawdown              | Below 15%                        |
| Strategy stability            | Positive across multiple periods |
| Look-ahead violations         | Zero                             |
| Compliance violations         | Zero                             |
| Unreconciled simulated orders | Zero                             |

These are provisional engineering gates, not evidence that the strategies can achieve them. A strategy failing the gates must not be promoted simply by increasing parameter optimization.

### 11\. Security and operational controls

The following controls are mandatory before any live execution:

* Role-based access control and secure session management.

* Secrets stored outside source code and Pine Script.

* Webhook authentication through a trusted gateway or opaque endpoint credentials, with replay protection.

* Idempotency keys for order submissions.

* Separate paper and live credentials.

* Broker order-state reconciliation.

* Order quantity caps and available-cash verification.

* Automatic suspension of new orders on stale data or system failure.

* Emergency trading kill switch.

* Complete audit logging of AI outputs, policy decisions, and orders.

* Human approval for enabling live trading or changing critical risk limits.

The AI service must be treated as an untrusted analytical dependency. News text may contain prompt-injection attempts, so its output must never directly invoke privileged execution actions.

### 12\. Development milestones and acceptance tests

Implementation checklist

0/9 complete

1. Foundation and architecture

Repository, schemas, database, configuration, CI and local deployment

Acceptance: API boots, migrations pass, tests run

2. Three Pine Script strategies

Stocks, ETFs and gold technical strategies with configurable parameters

Acceptance: Scripts compile; long-only behavior; no future leakage

3. Market and news data

Historical candles, corporate actions, news ingestion and economic calendar

Acceptance: Timestamps, provenance and freshness validated

4. AI intelligence and decision engine

Structured classification, event policies and explainable decisions

Acceptance: Schema tests, prompt-injection tests, deterministic gate tests

5. Compliance and risk engines

Asset screening, ownership policies, sizing and portfolio constraints

Acceptance: All forbidden-order and insufficient-cash cases rejected

6. Research and backtesting

Point-in-time replay, baseline comparison, optimization and reports

Acceptance: Reproducible runs with costs and untouched test periods

7. Dashboard and Telegram

Scanner, portfolio, analytics, alerts, operational status

Acceptance: End-to-end signal-to-notification tests pass

8. Paper trading release

Simulated broker, order lifecycle and reconciliation

Acceptance: Stable forward testing and no critical operational violations

9. Optional live broker integration

Compatible cash brokerage, custody checks and live execution controls

Acceptance: Independent compliance review and live-readiness approval

Use this as a planning tracker. No milestones have been implemented or verified in this conversation.

### 13\. Decisions to finalize before implementation

| Decision                     | Recommended default                                                   |
| ---------------------------- | --------------------------------------------------------------------- |
| Initial markets              | US-listed Shariah-compliant stocks and ETFs; separately verified gold |
| Trading horizon              | Swing and position trading                                            |
| System architecture          | Modular monolith                                                      |
| AI role                      | News classification and evidence synthesis                            |
| Order authorization          | Deterministic policies                                                |
| Initial broker               | Paper broker                                                          |
| Live trading                 | Disabled                                                              |
| News integration             | Backend only                                                          |
| Primary database             | PostgreSQL                                                            |
| Primary notification channel | Telegram                                                              |
| Primary UI                   | Next.js dashboard                                                     |
| Research priority            | Net expectancy and drawdown, not win rate alone                       |

The live broker, specific gold instrument, Shariah screening methodology, and market-data providers must be selected and verified before implementing their production adapters. These decisions affect legality, accessibility, historical-data quality, and cost.

### 14\. What we should build first

Milestone 1 + 2: Foundation and Pine Script strategies

Our first deliverable should contain a functioning repository foundation and three independently configurable Pine Script v6 strategies.

Each strategy should support long-only signals, configurable indicators, stop-loss and trailing-exit rules, date-range controls, commission and slippage assumptions, alert payloads, and a consistent JSON signal contract.

The first milestone must also include automated tests for the Python-side indicator calculations and explicit documentation of any TradingView limitations.

Start implementation of Milestones 1 and 2

Final architectural recommendation: HALAL QUANT should be a research-first, compliance-gated, ownership-aware trading platform. The three strategies should remain independent, but share one news intelligence service, one risk engine, one portfolio ledger, and one decision framework.

That gives us a system that can be developed, measured, audited, and improved without relying on unverified claims about AI trading performance.
