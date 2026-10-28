from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.decision_engine.engine import TrustedState, evaluate
from services.decision_engine.policies import DecisionPolicy, calendar_restrictions

POLICY = DecisionPolicy()
NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)


def allowed(**changes):
    return TrustedState(
        **(
            {
                "data_is_fresh": True,
                "compliance_status": "APPROVED",
                "instrument_permitted": True,
                "news_allows_entry": True,
                "risk_limits_allow_entry": True,
            }
            | changes
        )
    )


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"data_is_fresh": False}, "WAIT_DATA"),
        ({"compliance_status": "PENDING"}, "BLOCK_COMPLIANCE"),
        ({"compliance_status": "REJECTED"}, "BLOCK_COMPLIANCE"),
        ({"instrument_permitted": None}, "BLOCK_INSTRUMENT"),
        ({"instrument_permitted": False}, "BLOCK_INSTRUMENT"),
        ({"news_allows_entry": False}, "WAIT_EVENT"),
        ({"risk_limits_allow_entry": False}, "BLOCK_RISK"),
        ({"risk_limits_allow_entry": None}, "BLOCK_RISK"),
    ],
)
def test_mandatory_gates_cannot_be_overridden_by_perfect_score(changes, expected):
    result = evaluate("ENTRY_CANDIDATE", 1.0, allowed(**changes), POLICY)
    assert result["status"] == expected
    assert not result["authorized"]
    assert len(result["trace"]) == 6


def test_gate_priority_score_threshold_and_candidate_never_execution_permission():
    result = evaluate("ENTRY_CANDIDATE", 1.0, TrustedState(), POLICY)
    assert result["status"] == "WAIT_DATA"
    assert [gate["passed"] for gate in result["trace"]] == [False, False, False, False, False, True]
    assert evaluate("ENTRY_CANDIDATE", 0.64999, allowed(), POLICY)["status"] == "WAIT_SIGNAL"
    candidate = evaluate("ENTRY_CANDIDATE", 0.65, allowed(), POLICY)
    assert candidate["status"] == "BUY_CANDIDATE"
    assert not candidate["authorized"] and candidate["requires_execution_authorization"]
    assert candidate == evaluate("ENTRY_CANDIDATE", 0.65, allowed(), POLICY)


def test_entry_blocks_do_not_disable_owned_protective_exit_candidates():
    blocked = TrustedState(ownership_verified=True, sellable_quantity=Decimal(5))
    exit_result = evaluate("EXIT_CANDIDATE", 0.0, blocked, POLICY)
    assert exit_result["status"] == "EXIT_CANDIDATE"
    assert not exit_result["authorized"]
    assert len(exit_result["trace"]) == 1
    assert evaluate("ENTRY_CANDIDATE", 1.0, blocked, POLICY)["status"] == "WAIT_DATA"
    assert evaluate("EXIT_CANDIDATE", 1.0, TrustedState(), POLICY)["status"] == "WAIT_OWNERSHIP"
    assert (
        evaluate("EXIT_CANDIDATE", 1.0, TrustedState(ownership_verified=True), POLICY)["status"]
        == "WAIT_OWNERSHIP"
    )


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.01, True, "1"])
def test_invalid_scores_are_rejected(score):
    with pytest.raises(ValueError):
        evaluate("ENTRY_CANDIDATE", score, allowed(), POLICY)


def test_untrusted_state_flags_and_short_actions_rejected():
    with pytest.raises(ValueError):
        TrustedState(data_is_fresh="true")
    with pytest.raises(ValueError):
        TrustedState(compliance_status="AI_APPROVED")
    with pytest.raises(ValueError):
        evaluate("SELL_SHORT", 1.0, allowed(), POLICY)


def event(**changes):
    return {
        "source_id": "a" * 64,
        "event_type": "earnings",
        "scheduled_at": NOW.isoformat(),
        "symbols": ["EXAMPLE"],
        "asset_classes": ["stock"],
        "severity": "high",
        "cancelled": False,
        "synthetic": True,
    } | changes


@pytest.mark.parametrize("hours", [-24, 0, 24])
def test_earnings_window_includes_both_boundaries(hours):
    restrictions = calendar_restrictions(
        [event()], "EXAMPLE", "stock", NOW + timedelta(hours=hours), POLICY
    )
    assert restrictions[0]["code"] == "EARNINGS_WINDOW"


def test_calendar_scope_cancellation_outside_window_and_macro_window():
    assert not calendar_restrictions([event()], "OTHER", "stock", NOW, POLICY)
    assert not calendar_restrictions([event(cancelled=True)], "EXAMPLE", "stock", NOW, POLICY)
    assert not calendar_restrictions(
        [event()], "EXAMPLE", "stock", NOW + timedelta(hours=24, microseconds=1), POLICY
    )
    macro = event(event_type="fed", symbols=[], asset_classes=["gold"])
    for offset in [-2, 1]:
        assert calendar_restrictions([macro], "GOLD", "gold", NOW + timedelta(hours=offset), POLICY)
    assert not calendar_restrictions(
        [macro], "GOLD", "gold", NOW - timedelta(hours=2, microseconds=1), POLICY
    )
    assert not calendar_restrictions([macro], "EXAMPLE", "stock", NOW, POLICY)
    assert (
        calendar_restrictions([event(symbols=[])], "EXAMPLE", "stock", NOW, POLICY)[0]["code"]
        == "EVENT_SCOPE_REVIEW"
    )
