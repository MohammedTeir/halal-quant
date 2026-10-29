"""Deterministic hypothetical checks. Caller facts never become trusted authorities."""

import hashlib
from datetime import timedelta
from decimal import ROUND_FLOOR, Decimal, localcontext
from zoneinfo import ZoneInfo

from packages.schemas.controls import ControlScenario

ZERO = Decimal(0)
FIELDS = {
    "stock": ("business_activity_pass", "financial_ratios_pass"),
    "etf": (
        "fund_mandate_pass",
        "holdings_process_pass",
        "fund_structure_pass",
        "shariah_supervision_pass",
    ),
    "gold": (
        "gold_ownership_pass",
        "gold_possession_pass",
        "gold_custody_pass",
        "gold_settlement_pass",
        "gold_redemption_pass",
    ),
}
KINDS = {"stock": "equity", "etf": "fund", "gold": "allocated_gold"}


def evidence_current(evidence, as_of, max_age=None):
    return (
        evidence.observed_at <= evidence.recorded_at <= as_of
        and evidence.effective_at <= as_of < evidence.expires_at
        and (max_age is None or as_of - evidence.observed_at <= timedelta(seconds=max_age))
    )


def compliance(s):
    c, p, a, i = s.candidate, s.policy, s.assessment, s.instrument
    reasons = []
    if p.methodology is None:
        reasons.append("METHODOLOGY_UNSELECTED")
    if a is None:
        reasons.append("ASSESSMENT_MISSING")
    else:
        if (a.symbol, a.asset_class) != (c.symbol, c.asset_class):
            reasons.append("ASSESSMENT_SCOPE_MISMATCH")
        if a.methodology != p.methodology:
            reasons.append("METHODOLOGY_MISMATCH")
        if not evidence_current(a.evidence, s.as_of):
            reasons.append("ASSESSMENT_UNAVAILABLE_OR_EXPIRED")
        if a.status != "APPROVED":
            reasons.append("ASSET_" + a.status)
        for field in FIELDS[c.asset_class]:
            if getattr(a, field) is not True:
                reasons.append(field.upper() + "_UNVERIFIED")
    if i is None:
        reasons.append("INSTRUMENT_REVIEW_MISSING")
    else:
        if (i.symbol, i.asset_class) != (c.symbol, c.asset_class):
            reasons.append("INSTRUMENT_SCOPE_MISMATCH")
        if not evidence_current(i.evidence, s.as_of):
            reasons.append("INSTRUMENT_REVIEW_UNAVAILABLE_OR_EXPIRED")
        if i.kind != KINDS[c.asset_class]:
            reasons.append("INSTRUMENT_FORBIDDEN_OR_UNKNOWN")
        if i.settlement_and_possession_pass is not True:
            reasons.append("SETTLEMENT_OR_POSSESSION_UNVERIFIED")
    if c.action == "SHORT":
        reasons.append("SHORT_SELLING_FORBIDDEN")
    if c.margin_requested:
        reasons.append("MARGIN_FORBIDDEN")
    if c.borrow_requested:
        reasons.append("SHARE_BORROWING_FORBIDDEN")
    if c.quantity is not None and c.quantity != c.quantity.to_integral_value():
        reasons.append("FRACTIONAL_QUANTITY_UNSUPPORTED")
    return reasons


def account_reasons(s, *, entry):
    a, p = s.account, s.policy
    if a is None:
        return ["ACCOUNT_SNAPSHOT_MISSING"]
    reasons = []
    if not evidence_current(a.evidence, s.as_of, p.broker_max_age_seconds):
        reasons.append("ACCOUNT_SNAPSHOT_UNAVAILABLE_OR_STALE")
    if not a.positions_complete:
        reasons.append("POSITIONS_INCOMPLETE")
    if not a.reservations_complete:
        reasons.append("RESERVATIONS_INCOMPLETE")
    if entry:
        if not a.connected:
            reasons.append("BROKER_UNAVAILABLE")
        if a.account_type != "cash":
            reasons.append("CASH_ACCOUNT_REQUIRED")
        if a.lending_enabled is not False:
            reasons.append("LENDING_ENABLED_OR_UNKNOWN")
        if a.borrowing_enabled is not False:
            reasons.append("BORROWING_ENABLED_OR_UNKNOWN")
    return reasons


def exit_checks(s):
    c, a = s.candidate, s.account
    reasons = account_reasons(s, entry=False)
    if c.margin_requested or c.borrow_requested:
        reasons.append("EXIT_MUST_NOT_USE_MARGIN_OR_BORROWING")
    if c.quantity is None:
        reasons.append("EXIT_QUANTITY_REQUIRED")
    elif c.quantity != c.quantity.to_integral_value():
        reasons.append("FRACTIONAL_QUANTITY_UNSUPPORTED")
    position = next((x for x in a.positions if x.symbol == c.symbol), None) if a else None
    if position is None:
        reasons.append("OWNERSHIP_UNVERIFIED")
    available = ZERO
    if position is not None:
        if position.asset_class != c.asset_class:
            reasons.append("POSITION_ASSET_CLASS_MISMATCH")
        reserved = sum(
            (r.quantity for r in a.reservations if r.side == "SELL" and r.symbol == c.symbol), ZERO
        )
        available = max(ZERO, position.sellable_quantity - reserved)
        if c.quantity is not None and c.quantity > available:
            reasons.append("INSUFFICIENT_SELLABLE_QUANTITY")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "available_sellable_quantity": str(available),
        "quantity": str(c.quantity) if not reasons else None,
        "noncompliance_review_required": bool(compliance(s)),
        "broker_connected": bool(a and a.connected),
    }


def risk(s):
    c, p, a, q = s.candidate, s.policy, s.account, s.quote
    reasons = account_reasons(s, entry=True)
    if p.kill_switch:
        reasons.append("KILL_SWITCH_ACTIVE")
    if q is None:
        reasons.append("QUOTE_MISSING")
    else:
        if (q.symbol, q.asset_class) != (c.symbol, c.asset_class):
            reasons.append("QUOTE_SCOPE_MISMATCH")
        if not evidence_current(q.evidence, s.as_of, p.quote_max_age_seconds):
            reasons.append("QUOTE_UNAVAILABLE_OR_STALE")
        if not q.required_feeds_fresh:
            reasons.append("REQUIRED_FEEDS_UNAVAILABLE")
    if a:
        if a.trading_day != s.as_of.astimezone(ZoneInfo(p.loss_day_timezone)).date():
            reasons.append("LOSS_DAY_SNAPSHOT_MISMATCH")
        if a.realized_pnl_today <= -a.day_start_equity * p.max_daily_loss:
            reasons.append("DAILY_LOSS_LIMIT")
        if (a.peak_equity - a.equity) / a.peak_equity >= p.max_drawdown:
            reasons.append("DRAWDOWN_LIMIT")
        if a.consecutive_losses >= p.consecutive_loss_limit and (
            a.last_loss_at is None
            or s.as_of < a.last_loss_at + timedelta(minutes=p.cooldown_minutes)
        ):
            reasons.append("CONSECUTIVE_LOSS_COOLDOWN")
        exposures = {}
        sectors = {}
        for symbol, sector, value in [
            *((x.symbol, x.sector, x.market_value) for x in a.positions),
            *((r.symbol, r.sector, r.notional) for r in a.reservations if r.side == "BUY"),
        ]:
            exposures[symbol] = exposures.get(symbol, ZERO) + value
            sectors[sector] = sectors.get(sector, ZERO) + value
        if any(value > a.equity * p.max_position for value in exposures.values()):
            reasons.append("EXISTING_POSITION_LIMIT_BREACH")
        if any(value > a.equity * p.max_sector for value in sectors.values()):
            reasons.append("EXISTING_SECTOR_LIMIT_BREACH")
        if any(x.symbol == c.symbol and x.asset_class != c.asset_class for x in a.positions):
            reasons.append("POSITION_ASSET_CLASS_MISMATCH")
        if any(x.open_risk is None for x in a.positions):
            reasons.append("POSITION_RISK_UNKNOWN")
        if any(r.planned_risk is None for r in a.reservations if r.side == "BUY"):
            reasons.append("RESERVED_RISK_UNKNOWN")
        if any(x.symbol == c.symbol and x.sector != c.sector for x in a.positions) or any(
            r.symbol == c.symbol and r.sector != c.sector for r in a.reservations
        ):
            reasons.append("SECTOR_SCOPE_MISMATCH")
    if c.stop_price is None or (q is not None and c.stop_price >= q.ask):
        reasons.append("INVALID_LONG_STOP")
    if reasons:
        return {"passed": False, "reasons": reasons, "maximum_quantity": 0, "quantity": 0}
    entry = q.ask * (1 + p.slippage_bps / Decimal(10000))
    stop = c.stop_price * (1 - p.slippage_bps / Decimal(10000))
    unit_risk = entry - stop + 2 * p.fee_per_share
    buys = [r for r in a.reservations if r.side == "BUY"]
    used_risk = sum((x.open_risk for x in a.positions), ZERO) + sum(
        (r.planned_risk for r in buys), ZERO
    )
    cash = (
        a.settled_cash
        - a.other_cash_holds
        - sum((r.notional + r.estimated_fee for r in buys), ZERO)
    )
    position_value = sum((x.market_value for x in a.positions if x.symbol == c.symbol), ZERO) + sum(
        (r.notional for r in buys if r.symbol == c.symbol), ZERO
    )
    sector_value = sum((x.market_value for x in a.positions if x.sector == c.sector), ZERO) + sum(
        (r.notional for r in buys if r.sector == c.sector), ZERO
    )

    def floor(value):
        return max(0, int(value.to_integral_value(rounding=ROUND_FLOOR)))

    capacities = {
        "trade_risk": floor((a.equity * p.risk_per_trade - 2 * p.fee_per_order) / unit_risk),
        "open_risk": floor(
            (a.equity * p.max_open_risk - used_risk - 2 * p.fee_per_order) / unit_risk
        ),
        "cash": floor((cash - p.fee_per_order) / (entry + p.fee_per_share)),
        "position": floor((a.equity * p.max_position - position_value) / entry),
        "sector": floor((a.equity * p.max_sector - sector_value) / entry),
    }
    maximum = min(capacities.values())
    quantity = maximum if c.quantity is None else c.quantity
    if maximum == 0:
        reasons.append("ZERO_CAPACITY")
    if quantity > maximum:
        reasons.append("REQUESTED_QUANTITY_EXCEEDS_CAPACITY")
    if quantity != Decimal(quantity).to_integral_value():
        reasons.append("FRACTIONAL_QUANTITY_UNSUPPORTED")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "maximum_quantity": maximum,
        "quantity": int(quantity) if not reasons else 0,
        "capacity_by_limit": capacities,
        "entry_with_slippage": str(entry),
        "stop_with_slippage": str(stop),
        "planned_risk": str(Decimal(quantity) * unit_risk + 2 * p.fee_per_order)
        if not reasons
        else None,
        "estimated_cash_required": str(
            Decimal(quantity) * (entry + p.fee_per_share) + p.fee_per_order
        )
        if not reasons
        else None,
    }


def _preview(s: ControlScenario):
    if s.candidate.action == "SELL":
        result = exit_checks(s)
        checks = {"exit": result}
        passed = result["passed"]
    else:
        compliance_reasons = compliance(s)
        risk_result = risk(s)
        checks = {
            "compliance": {"passed": not compliance_reasons, "reasons": compliance_reasons},
            "risk": risk_result,
        }
        passed = not compliance_reasons and risk_result["passed"]
    return {
        "status": "SIMULATION_PASS" if passed else "SIMULATION_BLOCKED",
        "checks": checks,
        "mode": "hypothetical",
        "input_authority": "caller_supplied_unverified_scenario",
        "authorized": False,
        "evidence_authority_verified": False,
        "policy_version": s.policy.version,
        "scenario_sha256": hashlib.sha256(s.model_dump_json().encode()).hexdigest(),
        "policy_sha256": hashlib.sha256(s.policy.model_dump_json().encode()).hexdigest(),
        "as_of": s.as_of.isoformat(),
    }


def preview(s: ControlScenario):
    # Input precision is bounded by the schema; preserve exact budgets/costs without
    # changing the application's global Decimal context.
    with localcontext() as context:
        context.prec = 80
        return _preview(s)
