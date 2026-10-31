"""Cross-check collected annual disclosures against SEC facts; never approve stocks."""

import argparse
import hashlib
import json
import os
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import httpx

from apps.api.db import utcnow

SEC = "https://data.sec.gov"


def load_json(raw):
    return json.loads(
        raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON"))
    )


def latest_filing(payload, cutoff):
    recent = payload["filings"]["recent"]
    fields = ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument")
    if len({len(recent[k]) for k in fields}) != 1:
        raise ValueError("Misaligned SEC submission columns")
    eligible = [
        {k: recent[k][i] for k in fields}
        for i, form in enumerate(recent["form"])
        if form in ("10-K", "10-Q", "10-K/A", "10-Q/A")
        and recent["filingDate"][i] <= cutoff.isoformat()
    ]
    return max(eligible, key=lambda row: (row["filingDate"], row["accessionNumber"]), default=None)


def compare_fact(fact, filing, companyfacts):
    """Exact accession, period and units; no estimates or synthetic zeroes."""
    namespace, concept = fact["concept"].split("_", 1)
    units = companyfacts.get("facts", {}).get(namespace, {}).get(concept, {}).get("units", {})
    end, start = filing["endDate"][:10], filing["startDate"][:10]
    candidates = [
        row
        for unit, rows in units.items()
        if unit.lower() == fact.get("unit", "").lower()
        for row in rows
        if row.get("accn") == filing["accessNumber"]
        and row.get("end") == end
        and (
            (fact["section"] == "bs" and "start" not in row)
            or (fact["section"] == "ic" and row.get("start") == start)
        )
    ]
    values = {Decimal(str(row["val"])) for row in candidates}
    expected = Decimal(str(fact["value"]))
    if not expected.is_finite() or any(not v.is_finite() for v in values):
        raise ValueError("Nonfinite financial value")
    if not values:
        return "NOT_COVERED_BY_EXACT_SEC_FACT"
    if len(values) != 1:
        return "AMBIGUOUS_SEC_VALUES"
    return "EXACT_MATCH" if values == {expected} else "MISMATCH"


def relevant_facts(filing):
    result = []
    for section in ("bs", "ic"):
        for fact in filing.get("report", {}).get(section, []):
            name = fact.get("concept", "")
            if section == "bs":
                include = any(
                    k in name
                    for k in (
                        "Debt",
                        "Borrowing",
                        "CommercialPaper",
                        "CashAndCash",
                        "MarketableSecurities",
                        "ShortTermInvestments",
                    )
                )
            else:
                include = any(
                    k in name
                    for k in (
                        "RevenueFromContract",
                        "SalesRevenue",
                        "Revenues",
                        "InterestIncome",
                        "InvestmentIncome",
                    )
                )
            if include:
                result.append(
                    {
                        "section": section,
                        "concept": name,
                        "unit": fact["unit"],
                        "value": fact["value"],
                    }
                )
    return result


BALANCE_CONCEPTS = {
    "DebtInstrumentCarryingAmount",
    "LongTermDebt",
    "LongTermDebtCurrent",
    "LongTermDebtNoncurrent",
    "ShortTermBorrowings",
    "ShortTermDebtCurrent",
    "CommercialPaper",
    "LongTermDebtAndCapitalLeaseObligations",
    "LongTermDebtAndCapitalLeaseObligationsCurrent",
    "LongTermDebtAndCapitalLeaseObligationsNoncurrent",
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsAndShortTermInvestments",
    "MarketableSecuritiesCurrent",
    "MarketableSecuritiesNoncurrent",
    "ShortTermInvestments",
    "LongTermInvestments",
    "AvailableForSaleSecuritiesDebtSecurities",
}
INCOME_CONCEPTS = {
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "InvestmentIncomeInterest",
    "InvestmentIncomeNet",
    "InterestIncomeOperating",
    "InterestAndDividendIncomeOperating",
    "InterestIncomeExpenseNonoperatingNet",
    "InvestmentIncomeNonoperating",
    "NonoperatingIncomeExpense",
}


def current_disclosures(companyfacts, latest):
    """Separate overlapping line items and period lengths; do not construct a screen."""
    if not latest or not latest.get("reportDate"):
        return []
    output = []
    for concept, facts in companyfacts.get("facts", {}).get("us-gaap", {}).items():
        if concept not in BALANCE_CONCEPTS | INCOME_CONCEPTS:
            continue
        for row in facts.get("units", {}).get("USD", []):
            if (
                row.get("accn") != latest["accessionNumber"]
                or row.get("end") != latest["reportDate"]
            ):
                continue
            start = row.get("start")
            if concept in BALANCE_CONCEPTS:
                if start:
                    continue
            else:
                if not start:
                    continue
                days = (date.fromisoformat(row["end"]) - date.fromisoformat(start)).days + 1
                low, high = (330, 400) if latest["form"].startswith("10-K") else (75, 105)
                if not low <= days <= high:
                    continue
            value = Decimal(str(row["val"]))
            if not value.is_finite():
                raise ValueError("Nonfinite SEC disclosure")
            entry = {
                "concept": concept,
                "value": str(value),
                "unit": "USD",
                "start": start,
                "end": row["end"],
            }
            if entry not in output:
                output.append(entry)
    return output


def fetch(client, path, destination):
    with client.stream("GET", SEC + path) as response:
        if response.status_code != 200:
            raise ValueError("SEC source unavailable")
        raw = bytearray()
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw) > 32 * 1024 * 1024:
                raise ValueError("SEC response exceeds archive limit")
    value = load_json(raw)
    destination.write_bytes(raw)
    return value, hashlib.sha256(raw).hexdigest()


def review(evidence_path, financial_archive, archive, *, transport=None):
    now = utcnow()
    evidence = load_json(evidence_path.read_bytes())
    archive.mkdir(parents=True, mode=0o700, exist_ok=False)
    items = []
    with httpx.Client(
        timeout=25,
        follow_redirects=False,
        transport=transport,
        headers={
            "User-Agent": "halal-quant research (https://github.com/MohammedTeir/halal-quant)",
        },
    ) as client:
        for item in evidence["items"]:
            symbol = item["symbol"]
            if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,31}", symbol):
                raise ValueError("Invalid archive symbol")
            row = {
                "symbol": symbol,
                "status": "NOT_APPROVED",
                "source_sha256": item["response_sha256"],
            }
            raw = (financial_archive / (symbol + ".json")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != item["response_sha256"]:
                raise ValueError("Collected financial source changed")
            payload = load_json(raw)
            filings = [d for d in payload["data"] if d["accessNumber"] == item["accession"]]
            if len(filings) != 1 or payload.get("symbol") != symbol:
                raise ValueError("Financial filing/symbol mismatch")
            filing = filings[0]
            cik = str(payload["cik"])
            if not cik.isdigit() or not 1 <= len(cik) <= 10:
                raise ValueError("Invalid SEC CIK")
            cik = cik.zfill(10)
            row["cik"] = cik
            row["reviewed_filing"] = item["accession"]
            try:
                submissions, sub_hash = fetch(
                    client, f"/submissions/CIK{cik}.json", archive / (symbol + "-submissions.json")
                )
                companyfacts, fact_hash = fetch(
                    client,
                    f"/api/xbrl/companyfacts/CIK{cik}.json",
                    archive / (symbol + "-companyfacts.json"),
                )
                if int(companyfacts["cik"]) != int(cik) or int(submissions["cik"]) != int(cik):
                    raise ValueError("SEC company scope mismatch")
                latest = latest_filing(submissions, now.date())
                facts = relevant_facts(filing)
                row.update(
                    sec_status="OBSERVED",
                    submissions_sha256=sub_hash,
                    companyfacts_sha256=fact_hash,
                    latest_sec_filing=latest,
                    latest_primary_disclosures=current_disclosures(companyfacts, latest),
                    aggregation_or_screening_performed=False,
                    newer_financial_filing_available=bool(
                        latest and latest["filingDate"] > item["filing_date"][:10]
                    ),
                    facts=[
                        f | {"comparison": compare_fact(f, filing, companyfacts)} for f in facts
                    ],
                )
            except (httpx.HTTPError, ValueError, KeyError, TypeError, ArithmeticError):
                row["sec_status"] = "NOT_CONFIRMED"
            row["unresolved"] = [
                "Historical average market-cap denominator",
                "Reviewed consolidated debt/investment mappings",
                "Non-permissible revenue calculation",
                "Business activity, purification and instrument evidence",
                "Current reviewed approvals",
            ]
            items.append(row)
            print(f"{symbol}: SEC {row['sec_status']}; screening NOT_APPROVED", flush=True)
    end = now.date() - timedelta(days=1)
    result = {
        "observed_at": now.isoformat(),
        "status": "TECHNICAL_EVIDENCE_REVIEW_ONLY",
        "items": items,
        "approved_symbols": [],
        "averaging_window_proposal": {
            "status": "PROPOSED_NOT_APPROVED",
            "calendar_days": 365,
            "starts": (end - timedelta(days=364)).isoformat(),
            "ends": end.isoformat(),
            "definition": "Equal-weight mean of actual closing market capitalizations for verified regular sessions in the interval. Historical share counts and corporate actions required; no fixed-current-share or current-cap proxy.",
            "historical_values_collected": False,
            "scope": "Research proposal, not an assertion that AAOIFI mandates this window. No existing immutable account/protocol/review changed.",
        },
        "scope": "Exact SEC fact matches verify selected historical values only, not completeness, current ratios, business permissibility, source independence or qualified approval.",
        "production_database_mutations": 0,
        "orders_submitted": 0,
        "messages_sent": 0,
    }
    (archive / "review.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("reports/milestone8-screening-evidence-2026-10-31.json"),
    )
    parser.add_argument("--financial-archive", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        review(args.evidence, args.financial_archive, args.archive)
    except (ValueError, OSError, KeyError, TypeError):
        parser.exit(
            1,
            "Review unavailable; preserve source archives and check the declared filing inputs. No approval was created.\n",
        )


if __name__ == "__main__":
    main()
