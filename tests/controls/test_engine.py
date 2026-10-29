import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from packages.schemas.controls import ControlScenario
from services.controls.engine import FIELDS, preview

NOW = datetime(2025, 1, 2, 15, tzinfo=UTC)


def scenario_data(now=NOW):
    def evidence(name):
        return {
            "evidence_id": name,
            "provider": "demo_fixture",
            "document_sha256": "a" * 64,
            "observed_at": now.isoformat(),
            "recorded_at": now.isoformat(),
            "effective_at": (now - timedelta(days=1)).isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
        }

    return {
        "mode": "hypothetical",
        "as_of": now.isoformat(),
        "candidate": {
            "symbol": "EXAMPLE",
            "asset_class": "stock",
            "sector": "technology",
            "action": "BUY",
            "stop_price": "95",
        },
        "policy": {"methodology": "demo-fixture-v1"},
        "assessment": {
            "symbol": "EXAMPLE",
            "asset_class": "stock",
            "status": "APPROVED",
            "methodology": "demo-fixture-v1",
            "evidence": evidence("screen-fixture"),
            "purification_guidance": "Synthetic example only; no real asset or scholarly approval.",
            "business_activity_pass": True,
            "financial_ratios_pass": True,
        },
        "instrument": {
            "symbol": "EXAMPLE",
            "asset_class": "stock",
            "kind": "equity",
            "evidence": evidence("instrument-fixture"),
            "settlement_and_possession_pass": True,
        },
        "account": {
            "account_id": "demo-cash",
            "evidence": evidence("account-fixture"),
            "connected": True,
            "account_type": "cash",
            "lending_enabled": False,
            "borrowing_enabled": False,
            "positions_complete": True,
            "reservations_complete": True,
            "equity": "10000",
            "day_start_equity": "10000",
            "peak_equity": "10000",
            "settled_cash": "10000",
            "trading_day": now.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
        },
        "quote": {
            "symbol": "EXAMPLE",
            "asset_class": "stock",
            "evidence": evidence("quote-fixture"),
            "bid": "100",
            "ask": "100",
            "required_feeds_fresh": True,
        },
    }


def evaluate(data):
    return preview(ControlScenario.model_validate(data))


def reasons(result):
    return [code for check in result["checks"].values() for code in check["reasons"]]


def position(symbol="EXAMPLE", sector="technology", value="500", risk="25"):
    return {
        "symbol": symbol,
        "asset_class": "stock",
        "sector": sector,
        "quantity": "10",
        "sellable_quantity": "8",
        "market_value": value,
        "open_risk": risk,
    }


def reservation(
    side="BUY", symbol="EXAMPLE", notional="500", risk="25", quantity="5", sector="technology"
):
    return {
        "reservation_id": "reserved-1",
        "symbol": symbol,
        "sector": sector,
        "side": side,
        "quantity": quantity,
        "notional": notional,
        "estimated_fee": "0",
        "planned_risk": risk,
    }


def test_blueprint_example_is_whole_cash_sized_and_never_authorized():
    data = scenario_data()
    result = evaluate(data)
    risk = result["checks"]["risk"]
    assert result["status"] == "SIMULATION_PASS"
    assert risk["quantity"] == 10 and risk["planned_risk"] == "50"
    assert risk["estimated_cash_required"] == "1000"
    assert not result["authorized"] and not result["evidence_authority_verified"]
    assert result["input_authority"] == "caller_supplied_unverified_scenario"
    assert result == evaluate(copy.deepcopy(data))


@pytest.mark.parametrize(
    "part,field,value,code",
    [
        ("candidate", "margin_requested", True, "MARGIN_FORBIDDEN"),
        ("candidate", "borrow_requested", True, "SHARE_BORROWING_FORBIDDEN"),
        ("candidate", "action", "SHORT", "SHORT_SELLING_FORBIDDEN"),
        ("candidate", "quantity", "0.5", "FRACTIONAL_QUANTITY_UNSUPPORTED"),
        ("account", "account_type", "margin", "CASH_ACCOUNT_REQUIRED"),
        ("account", "lending_enabled", True, "LENDING_ENABLED_OR_UNKNOWN"),
        ("account", "lending_enabled", None, "LENDING_ENABLED_OR_UNKNOWN"),
        ("account", "borrowing_enabled", True, "BORROWING_ENABLED_OR_UNKNOWN"),
        ("account", "connected", False, "BROKER_UNAVAILABLE"),
        ("account", "positions_complete", False, "POSITIONS_INCOMPLETE"),
        ("account", "reservations_complete", False, "RESERVATIONS_INCOMPLETE"),
        ("quote", "required_feeds_fresh", False, "REQUIRED_FEEDS_UNAVAILABLE"),
        ("quote", "symbol", "OTHER", "QUOTE_SCOPE_MISMATCH"),
        ("assessment", "status", "PENDING", "ASSET_PENDING"),
        ("assessment", "status", "REJECTED", "ASSET_REJECTED"),
        ("assessment", "business_activity_pass", False, "BUSINESS_ACTIVITY_PASS_UNVERIFIED"),
        ("assessment", "financial_ratios_pass", None, "FINANCIAL_RATIOS_PASS_UNVERIFIED"),
        ("assessment", "symbol", "OTHER", "ASSESSMENT_SCOPE_MISMATCH"),
        ("assessment", "methodology", "different", "METHODOLOGY_MISMATCH"),
        (
            "instrument",
            "settlement_and_possession_pass",
            None,
            "SETTLEMENT_OR_POSSESSION_UNVERIFIED",
        ),
        ("policy", "methodology", None, "METHODOLOGY_UNSELECTED"),
        ("policy", "kill_switch", True, "KILL_SWITCH_ACTIVE"),
        ("candidate", "stop_price", "100", "INVALID_LONG_STOP"),
    ],
)
def test_entry_blockers(part, field, value, code):
    data = scenario_data()
    data[part][field] = value
    result = evaluate(data)
    assert result["status"] == "SIMULATION_BLOCKED" and code in reasons(result)
    assert not result["authorized"]


@pytest.mark.parametrize("kind", ["cfd", "future", "option", "unknown", "allocated_gold"])
def test_forbidden_or_wrong_instrument_kind(kind):
    data = scenario_data()
    data["instrument"]["kind"] = kind
    assert "INSTRUMENT_FORBIDDEN_OR_UNKNOWN" in reasons(evaluate(data))


@pytest.mark.parametrize("asset", ["etf", "gold"])
def test_every_asset_specific_evidence_item_required(asset):
    data = scenario_data()
    for part in ["candidate", "assessment", "instrument", "quote"]:
        data[part]["asset_class"] = asset
    data["instrument"]["kind"] = "fund" if asset == "etf" else "allocated_gold"
    for field in FIELDS[asset]:
        data["assessment"][field] = True
    assert evaluate(data)["status"] == "SIMULATION_PASS"
    for field in FIELDS[asset]:
        changed = copy.deepcopy(data)
        changed["assessment"][field] = None
        assert field.upper() + "_UNVERIFIED" in reasons(evaluate(changed))


@pytest.mark.parametrize("part", ["assessment", "instrument", "account", "quote"])
def test_receipt_after_cutoff_and_exact_expiry_are_unavailable(part):
    for field, value in [("recorded_at", NOW + timedelta(seconds=1)), ("expires_at", NOW)]:
        data = scenario_data()
        data[part]["evidence"][field] = value.isoformat()
        assert evaluate(data)["status"] == "SIMULATION_BLOCKED"


@pytest.mark.parametrize(
    "part,seconds,code",
    [
        ("account", 31, "ACCOUNT_SNAPSHOT_UNAVAILABLE_OR_STALE"),
        ("quote", 16, "QUOTE_UNAVAILABLE_OR_STALE"),
    ],
)
def test_stale_snapshots_block(part, seconds, code):
    data = scenario_data()
    data[part]["evidence"]["observed_at"] = (NOW - timedelta(seconds=seconds)).isoformat()
    assert code in reasons(evaluate(data))


@pytest.mark.parametrize("missing", ["assessment", "instrument", "account", "quote"])
def test_missing_evidence_blocks(missing):
    data = scenario_data()
    data[missing] = None
    assert evaluate(data)["status"] == "SIMULATION_BLOCKED"


def test_cash_costs_and_stop_risk_use_decimal_slippage_and_both_exit_fees():
    data = scenario_data()
    data["policy"].update(fee_per_share="0.10", fee_per_order="1", slippage_bps="10")
    data["account"]["settled_cash"] = "900"
    result = evaluate(data)["checks"]["risk"]
    assert result["quantity"] == 8
    assert Decimal(result["estimated_cash_required"]) <= Decimal(900)
    assert Decimal(result["planned_risk"]) <= Decimal(50)
    assert result["entry_with_slippage"] == "100.100" and result["stop_with_slippage"] == "94.905"
    data["account"]["settled_cash"] = "1"
    assert "ZERO_CAPACITY" in reasons(evaluate(data))


def test_other_cash_holds_pending_fees_and_explicit_oversize_are_not_ignored():
    data = scenario_data()
    data["account"].update(
        settled_cash="1100", other_cash_holds="100", reservations=[reservation(notional="500")]
    )
    result = evaluate(data)["checks"]["risk"]
    assert result["maximum_quantity"] == 5
    data["candidate"]["quantity"] = "6"
    assert "REQUESTED_QUANTITY_EXCEEDS_CAPACITY" in reasons(evaluate(data))
    data["account"]["reservations"][0]["estimated_fee"] = "1"
    data["candidate"]["quantity"] = "5"
    assert evaluate(data)["checks"]["risk"]["maximum_quantity"] == 4


def test_open_risk_budget_includes_positions_and_pending_buys():
    data = scenario_data()
    data["account"]["positions"] = [position("OTHER", "other", risk="290")]
    data["account"]["reservations"] = [
        reservation(symbol="NEXT", sector="other", notional="100", risk="5")
    ]
    assert evaluate(data)["checks"]["risk"]["maximum_quantity"] == 1
    data["account"]["reservations"][0]["planned_risk"] = "10"
    assert "ZERO_CAPACITY" in reasons(evaluate(data))


def test_unknown_risk_and_sector_mismatch_fail_closed():
    data = scenario_data()
    data["account"]["positions"] = [position(risk=None)]
    assert "POSITION_RISK_UNKNOWN" in reasons(evaluate(data))
    data["account"]["positions"] = []
    data["account"]["reservations"] = [reservation(risk=None)]
    assert "RESERVED_RISK_UNKNOWN" in reasons(evaluate(data))
    data["account"]["reservations"] = [reservation(sector="other")]
    assert "SECTOR_SCOPE_MISMATCH" in reasons(evaluate(data))


def test_sector_capacity_and_existing_other_position_breach():
    data = scenario_data()
    data["account"]["positions"] = [
        position("OTHER1", value="1000"),
        position("OTHER2", value="1000"),
    ]
    assert evaluate(data)["checks"]["risk"]["maximum_quantity"] == 5
    data["account"]["positions"] = [position("OTHER1", "different", value="1001")]
    assert "EXISTING_POSITION_LIMIT_BREACH" in reasons(evaluate(data))


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("realized_pnl_today", "-200", "DAILY_LOSS_LIMIT"),
        ("peak_equity", "11111.12", "DRAWDOWN_LIMIT"),
        ("consecutive_losses", 3, "CONSECUTIVE_LOSS_COOLDOWN"),
        ("trading_day", "2025-01-01", "LOSS_DAY_SNAPSHOT_MISMATCH"),
    ],
)
def test_loss_guards_at_boundaries(field, value, code):
    data = scenario_data()
    data["account"][field] = value
    assert code in reasons(evaluate(data))


def test_consecutive_loss_cooldown_expires_at_exact_deadline():
    data = scenario_data()
    data["account"]["consecutive_losses"] = 3
    data["account"]["last_loss_at"] = (NOW - timedelta(minutes=60)).isoformat()
    assert evaluate(data)["status"] == "SIMULATION_PASS"
    data["account"]["last_loss_at"] = (NOW - timedelta(minutes=59, seconds=59)).isoformat()
    assert "CONSECUTIVE_LOSS_COOLDOWN" in reasons(evaluate(data))


def test_loss_day_is_new_york_calendar_date_not_utc_date():
    data = scenario_data(datetime(2025, 1, 3, 2, tzinfo=UTC))
    assert evaluate(data)["status"] == "SIMULATION_PASS"
    data["account"]["trading_day"] = "2025-01-03"
    assert "LOSS_DAY_SNAPSHOT_MISMATCH" in reasons(evaluate(data))


def test_protective_owned_exit_ignores_entry_kill_loss_and_compliance_guards():
    data = scenario_data()
    data["candidate"].update(action="SELL", quantity="4")
    data["account"]["positions"] = [position()]
    data["account"]["reservations"] = [reservation(side="SELL", quantity="4")]
    data["policy"]["kill_switch"] = True
    data["account"].update(realized_pnl_today="-900", connected=False)
    data["assessment"]["status"] = "REJECTED"
    data["quote"] = None
    result = evaluate(data)
    assert result["status"] == "SIMULATION_PASS" and not result["authorized"]
    assert result["checks"]["exit"]["noncompliance_review_required"]
    data["candidate"]["quantity"] = "5"
    assert "INSUFFICIENT_SELLABLE_QUANTITY" in reasons(evaluate(data))


def test_exit_cannot_invent_ownership_scope_or_borrow_to_sell():
    data = scenario_data()
    data["candidate"].update(action="SELL", quantity="1")
    assert "OWNERSHIP_UNVERIFIED" in reasons(evaluate(data))
    data["account"]["positions"] = [position()]
    data["candidate"]["asset_class"] = "gold"
    assert "POSITION_ASSET_CLASS_MISMATCH" in reasons(evaluate(data))
    data["candidate"].update(asset_class="stock", borrow_requested=True)
    assert "EXIT_MUST_NOT_USE_MARGIN_OR_BORROWING" in reasons(evaluate(data))


@pytest.mark.parametrize(
    "field,value", [("authorized", True), ("tool_calls", []), ("mode", "live")]
)
def test_privileged_extra_fields_or_non_hypothetical_mode_rejected(field, value):
    data = scenario_data()
    data[field] = value
    with pytest.raises(ValidationError):
        ControlScenario.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [("equity", "NaN"), ("settled_cash", "-1"), ("equity", "1e100000"), ("connected", "true")],
)
def test_unsafe_numeric_and_coerced_authority_booleans_rejected(field, value):
    data = scenario_data()
    data["account"][field] = value
    with pytest.raises(ValidationError):
        ControlScenario.model_validate(data)


@pytest.mark.parametrize("cash", ["1", "1000", "10000"])
@pytest.mark.parametrize("fee", ["0", "0.10", "1"])
def test_sized_quantity_never_exceeds_cash_or_risk_or_allocation(cash, fee):
    data = scenario_data()
    data["account"]["settled_cash"] = cash
    data["policy"].update(fee_per_share=fee, fee_per_order=fee, slippage_bps="15")
    result = evaluate(data)["checks"]["risk"]
    if result["passed"]:
        assert result["quantity"] > 0
        assert Decimal(result["estimated_cash_required"]) <= Decimal(cash)
        assert Decimal(result["planned_risk"]) <= Decimal(50)
        assert Decimal(result["entry_with_slippage"]) * result["quantity"] <= Decimal(1000)
    else:
        assert result["quantity"] == 0 and result["maximum_quantity"] == 0


def test_pending_sell_does_not_release_entry_exposure_before_fill():
    data = scenario_data()
    data["account"]["positions"] = [position()]
    data["account"]["reservations"] = [reservation(side="SELL")]
    assert evaluate(data)["checks"]["risk"]["maximum_quantity"] == 5


def test_stale_ownership_blocks_exit_even_when_entry_guards_are_ignored():
    data = scenario_data()
    data["candidate"].update(action="SELL", quantity="1")
    data["account"]["positions"] = [position()]
    data["policy"]["kill_switch"] = True
    data["account"]["evidence"]["observed_at"] = (NOW - timedelta(seconds=31)).isoformat()
    assert "ACCOUNT_SNAPSHOT_UNAVAILABLE_OR_STALE" in reasons(evaluate(data))


def test_owned_exit_flags_incomplete_approved_screen_without_forcing_liquidation():
    data = scenario_data()
    data["candidate"].update(action="SELL", quantity="1")
    data["account"]["positions"] = [position()]
    data["assessment"]["financial_ratios_pass"] = None
    result = evaluate(data)
    assert result["status"] == "SIMULATION_PASS"
    assert result["checks"]["exit"]["noncompliance_review_required"]
    assert not result["authorized"]


@pytest.mark.parametrize(
    "field", ["cooldown_minutes", "broker_max_age_seconds", "quote_max_age_seconds"]
)
def test_policy_durations_cannot_overflow_timedelta(field):
    data = scenario_data()
    data["policy"][field] = 10**100
    with pytest.raises(ValidationError):
        ControlScenario.model_validate(data)
