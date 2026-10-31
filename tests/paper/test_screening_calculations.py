from scripts.paper_screening_calculations import reconcile


def row(concept, value, start=None):
    return {"concept": concept, "value": value, "start": start, "end": "2026-09-30", "unit": "USD"}


def test_debt_components_are_reconciled_without_double_counting_the_total():
    result = reconcile(
        [
            row("LongTermDebtCurrent", 10),
            row("LongTermDebtNoncurrent", 80),
            row("LongTermDebt", 90),
            row("DebtInstrumentCarryingAmount", 92),
        ]
    )
    assert result["debt"]["component_sum"] == "90"
    assert result["debt"]["component_reconciliation"] == "EXACT"
    assert result["debt"]["carrying_minus_components"] == "2"
    assert result["debt"]["consolidated_screening_debt"] is None
    assert not result["approved"]


def test_debt_discrepancy_and_missing_component_do_not_become_zero():
    result = reconcile(
        [row("LongTermDebtCurrent", 10), row("LongTermDebtNoncurrent", 80), row("LongTermDebt", 91)]
    )
    assert result["debt"]["component_reconciliation"] == "DIFFERENCE"
    assert result["debt"]["total_minus_components"] == "1"
    assert reconcile([row("LongTermDebtCurrent", 10)])["debt"]["component_sum"] is None


def test_partial_interest_ratio_does_not_imply_a_complete_screen():
    facts = [row("Revenues", 1000, "2026-07-01"), row("InvestmentIncomeInterest", 10, "2026-07-01")]
    result = reconcile(facts)
    assert result["disclosed_interest_income_ratio"]["ratio"] == "0.01"
    assert result["non_permissible_revenue"] is None and not result["approved"]
    facts[1]["start"] = "2026-01-01"
    assert reconcile(facts)["disclosed_interest_income_ratio"] is None


def test_net_income_and_ambiguous_revenue_are_not_gross_interest_evidence():
    assert (
        reconcile(
            [row("Revenues", 1000, "2026-07-01"), row("InvestmentIncomeNet", 10, "2026-07-01")]
        )["disclosed_interest_income_ratio"]
        is None
    )
    assert (
        reconcile(
            [
                row("Revenues", 1000, "2026-07-01"),
                row("RevenueFromContractWithCustomerExcludingAssessedTax", 1100, "2026-07-01"),
                row("InvestmentIncomeInterest", 10, "2026-07-01"),
            ]
        )["disclosed_interest_income_ratio"]
        is None
    )


def test_components_from_different_dates_or_currencies_are_never_summed():
    facts = [row("LongTermDebtCurrent", 10), row("LongTermDebtNoncurrent", 80)]
    facts[1]["end"] = "2026-06-30"
    assert reconcile(facts)["debt"]["component_sum"] is None
    facts[1]["end"] = "2026-09-30"
    facts[1]["unit"] = "EUR"
    assert reconcile(facts)["debt"]["component_sum"] is None


def test_average_cap_requires_complete_daily_calendar_without_interpolation():
    import pytest

    from scripts.paper_screening_calculations import average_market_cap

    days = ["2026-10-28", "2026-10-29", "2026-10-30"]
    points = [{"date": d, "market_cap_usd": c} for d, c in zip(days, [100, 120, 140], strict=True)]
    assert str(average_market_cap(points, days, days[0], days[-1])) == "120"
    with pytest.raises(ValueError, match="Complete exact"):
        average_market_cap(points[::2], days, days[0], days[-1])
    with pytest.raises(ValueError, match="Duplicate"):
        average_market_cap(points + points[:1], days, days[0], days[-1])
    points[0]["market_cap_usd"] = "NaN"
    with pytest.raises(ValueError, match="invalid"):
        average_market_cap(points, days, days[0], days[-1])


def test_assets_lower_bounds_can_identify_a_breach_but_never_issue_approval():
    from scripts.paper_screening_calculations import assets_core_lower_bounds

    result = assets_core_lower_bounds(assets=100, cash=40)
    assert result["checks"]["cash_interest_items"]["state"] == "KNOWN_COMPONENT_BREACH"
    assert result["checks"]["debt"]["known_component_ratio"] is None
    assert not result["eligible_for_approval"]
    result = assets_core_lower_bounds(
        assets=100, cash=1, receivables=2, debt_components=3, interest_income=1, revenue=100
    )
    assert all(
        c["state"] == "UNKNOWN_FULL_TOTAL_NOT_ESTABLISHED" for c in result["checks"].values()
    )
    assert not result["eligible_for_approval"]
