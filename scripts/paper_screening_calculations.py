"""Partial accounting reconciliations only. No stock or campaign approval authority."""

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext


def value(facts, concept, *, instantaneous=False):
    rows = [
        f
        for f in facts
        if f["concept"] == concept and (not instantaneous or f.get("start") is None)
    ]
    if not rows:
        return None
    if len({(r.get("start"), r["end"], r["unit"]) for r in rows}) != 1:
        return None
    values = {Decimal(str(r["value"])) for r in rows}
    if len(values) != 1 or any(not v.is_finite() for v in values):
        return None
    return values.pop()


def reconcile(facts):
    current = value(facts, "LongTermDebtCurrent", instantaneous=True)
    noncurrent = value(facts, "LongTermDebtNoncurrent", instantaneous=True)
    reported = value(facts, "LongTermDebt", instantaneous=True)
    carrying = value(facts, "DebtInstrumentCarryingAmount", instantaneous=True)
    debt_contexts = {
        (r["end"], r["unit"])
        for r in facts
        if r["concept"]
        in {
            "LongTermDebtCurrent",
            "LongTermDebtNoncurrent",
            "LongTermDebt",
            "DebtInstrumentCarryingAmount",
        }
        and r.get("start") is None
    }
    consistent = len(debt_contexts) <= 1
    with localcontext() as context:
        context.prec = 60
        parts = (
            current + noncurrent
            if consistent and current is not None and noncurrent is not None
            else None
        )
        debt = {
            "contexts_consistent": consistent,
            "current": str(current) if current is not None else None,
            "noncurrent": str(noncurrent) if noncurrent is not None else None,
            "component_sum": str(parts) if parts is not None else None,
            "reported_long_term_total": str(reported) if reported is not None else None,
            "reported_carrying_amount": str(carrying) if carrying is not None else None,
            "total_minus_components": str(reported - parts)
            if reported is not None and parts is not None
            else None,
            "carrying_minus_components": str(carrying - parts)
            if carrying is not None and parts is not None
            else None,
            "component_reconciliation": "EXACT"
            if reported is not None and parts is not None and reported == parts
            else "DIFFERENCE"
            if reported is not None and parts is not None
            else "INSUFFICIENT_DISCLOSURES",
            "consolidated_screening_debt": None,
            "scope": "Totals/components are not added together. Short-term borrowing, lease scope, carrying/face adjustments and complete instrument coverage still require mapping.",
        }
        revenue_rows = [
            r
            for r in facts
            if r["concept"]
            in {
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "Revenues",
                "SalesRevenueNet",
            }
            and r.get("start")
        ]
        revenue = None
        if (
            revenue_rows
            and len(
                {(r["start"], r["end"], r["unit"], Decimal(str(r["value"]))) for r in revenue_rows}
            )
            == 1
        ):
            revenue = revenue_rows[0]
        interest_rows = [
            r
            for r in facts
            if r["concept"] in {"InvestmentIncomeInterest", "InterestIncomeOperating"}
        ]
        partial = None
        if revenue and len(interest_rows) == 1:
            interest = interest_rows[0]
            amount, denominator = Decimal(str(interest["value"])), Decimal(str(revenue["value"]))
            if (
                (interest.get("start"), interest["end"], interest["unit"])
                == (revenue["start"], revenue["end"], revenue["unit"])
                and amount.is_finite()
                and denominator.is_finite()
                and amount >= 0
                and denominator > 0
            ):
                partial = {
                    "interest_income": str(amount),
                    "revenue": str(denominator),
                    "ratio": str(amount / denominator),
                    "start": revenue["start"],
                    "end": revenue["end"],
                    "scope": "Disclosed gross interest-income component only; not a complete non-permissible revenue numerator or a passing screen.",
                }
    return {
        "debt": debt,
        "disclosed_interest_income_ratio": partial,
        "non_permissible_revenue": None,
        "approved": False,
    }


def average_market_cap(observations, expected_sessions, start, end):
    """Mean of supplied USD daily caps against a separately verified calendar.

    This checks arithmetic/coverage, not calendar truth, share-count methodology,
    provider entitlement or screening approval. No interpolation is performed.
    """
    for day in (start, end, *expected_sessions):
        if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
            raise ValueError("Canonical calendar dates required")
    if (
        start > end
        or not expected_sessions
        or len(set(expected_sessions)) != len(expected_sessions)
    ):
        raise ValueError("A unique verified session calendar is required")
    if any(not start <= day <= end for day in expected_sessions):
        raise ValueError("Calendar date outside the declared window")
    by_date = {}
    for point in observations:
        day = point["date"]
        try:
            amount = Decimal(str(point["market_cap_usd"]))
        except InvalidOperation:
            raise ValueError("Invalid market capitalization") from None
        if day in by_date or not amount.is_finite() or amount <= 0:
            raise ValueError("Duplicate or invalid market capitalization")
        by_date[day] = amount
    if set(by_date) != set(expected_sessions):
        raise ValueError("Complete exact daily session coverage required")
    with localcontext() as context:
        context.prec = 60
        return sum(by_date.values(), Decimal(0)) / Decimal(len(by_date))
