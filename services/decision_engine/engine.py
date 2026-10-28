"""Deterministic research decision gates fed only by trusted application state."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from services.decision_engine.policies import DecisionPolicy


class TrustedState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    data_is_fresh: StrictBool = False
    compliance_status: Literal["APPROVED", "PENDING", "REJECTED"] = "PENDING"
    instrument_permitted: StrictBool | None = None
    news_allows_entry: StrictBool = False
    risk_limits_allow_entry: StrictBool | None = None
    ownership_verified: StrictBool = False
    sellable_quantity: Decimal = Field(default=Decimal(0), ge=0, allow_inf_nan=False)


def evaluate(action: str, score: float, state: TrustedState, policy: DecisionPolicy):
    if (
        type(score) not in (int, float)
        or action not in ("ENTRY_CANDIDATE", "EXIT_CANDIDATE")
        or not 0 <= score <= 1
    ):
        raise ValueError("Invalid action or opportunity score")
    if action == "EXIT_CANDIDATE":
        permitted = state.ownership_verified and state.sellable_quantity > 0
        trace = [
            {
                "gate": "ownership",
                "passed": permitted,
                "code": "OWNED_EXIT_REQUIRES_EXECUTION_CHECK"
                if permitted
                else "OWNERSHIP_UNVERIFIED",
            }
        ]
        status = "EXIT_CANDIDATE" if permitted else "WAIT_OWNERSHIP"
    else:
        checks = [
            ("data", state.data_is_fresh, "WAIT_DATA"),
            ("compliance", state.compliance_status == "APPROVED", "BLOCK_COMPLIANCE"),
            ("instrument", state.instrument_permitted is True, "BLOCK_INSTRUMENT"),
            ("news_events", state.news_allows_entry, "WAIT_EVENT"),
            ("risk", state.risk_limits_allow_entry is True, "BLOCK_RISK"),
            ("signal", score >= policy.minimum_score, "WAIT_SIGNAL"),
        ]
        trace = [
            {"gate": gate, "passed": passed, "code": "PASS" if passed else code}
            for gate, passed, code in checks
        ]
        status = next((code for _, passed, code in checks if not passed), "BUY_CANDIDATE")
    return {
        "status": status,
        "trace": trace,
        "policy_version": policy.version,
        "authorized": False,
        "requires_execution_authorization": True,
        "mode": "research",
    }
