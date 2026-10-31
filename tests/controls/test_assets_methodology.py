from packages.schemas.control_operations import FinancialScreen, MethodologyApproval
from packages.schemas.controls import ControlEvidence
from services.controls.store import ratios
from tests.controls.operations_fixtures import asset, methodology


def assets_method():
    return MethodologyApproval.model_validate(
        methodology()
        | {
            "maximum_debt_ratio": "0.33333",
            "maximum_interest_assets_ratio": "0.33333",
            "maximum_receivables_cash_ratio": "0.50",
            "maximum_impure_income_ratio": "0.05",
            "impure_income_boundary": "at_or_below",
        }
    )


def test_old_method_and_financial_serialization_preserve_original_request_hash_inputs():
    method = methodology()
    financial = asset()["financials"]
    expected = method | {
        "evidence": ControlEvidence.model_validate(method["evidence"]).model_dump(mode="json")
    }
    assert MethodologyApproval.model_validate(method).model_dump(mode="json") == expected
    assert FinancialScreen.model_validate(financial).model_dump(mode="json") == financial
    result = ratios(
        FinancialScreen.model_validate(financial), MethodologyApproval.model_validate(method)
    )
    assert len(result["checks"]) == 3 and "missing_required_inputs" not in result


def test_assets_method_requires_receivables_cash_and_checks_its_strict_boundary():
    financial = asset()["financials"]
    missing = ratios(FinancialScreen.model_validate(financial), assets_method())
    assert not missing["eligible_for_reviewer_consideration"]
    assert missing["missing_required_inputs"] == ["receivables_cash"]
    for value, allowed in [("499.99", True), ("500", False), ("500.01", False)]:
        result = ratios(
            FinancialScreen.model_validate(financial | {"receivables_cash": value}), assets_method()
        )
        assert result["eligible_for_reviewer_consideration"] is allowed
        assert not result["automatic_shariah_approval"]


def test_income_five_percent_is_inclusive_only_when_method_explicitly_selects_it():
    financial = asset()["financials"] | {"impure_revenue": "5", "receivables_cash": "100"}
    assert ratios(FinancialScreen.model_validate(financial), assets_method())["checks"][
        "impure_income"
    ]
    legacy = MethodologyApproval.model_validate(methodology())
    assert not ratios(FinancialScreen.model_validate(financial), legacy)["checks"]["impure_income"]


def test_other_ratios_stay_strict_and_denominator_mismatch_still_blocks():
    financial = asset()["financials"] | {"receivables_cash": "100"}
    for field in ("debt", "interest_assets"):
        result = ratios(
            FinancialScreen.model_validate(financial | {field: "333.33"}), assets_method()
        )
        assert not result["checks"][field]
        assert not result["eligible_for_reviewer_consideration"]
    financial["denominator"] = "average_market_cap"
    assert not ratios(FinancialScreen.model_validate(financial), assets_method())[
        "eligible_for_reviewer_consideration"
    ]
