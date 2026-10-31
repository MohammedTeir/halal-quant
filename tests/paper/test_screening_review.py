from datetime import date

import pytest

from scripts.paper_screening_review import compare_fact, latest_filing, relevant_facts


def test_fact_comparison_requires_exact_accession_period_currency_and_single_value():
    fact = {
        "section": "bs",
        "concept": "us-gaap_LongTermDebtCurrent",
        "unit": "usd",
        "value": "100",
    }
    filing = {"startDate": "2025-01-01", "endDate": "2025-12-31", "accessNumber": "filing-1"}
    rows = [{"accn": "filing-1", "end": "2025-12-31", "val": 100}]
    payload = {"facts": {"us-gaap": {"LongTermDebtCurrent": {"units": {"USD": rows}}}}}
    assert compare_fact(fact, filing, payload) == "EXACT_MATCH"
    rows[0]["accn"] = "other"
    assert compare_fact(fact, filing, payload) == "NOT_COVERED_BY_EXACT_SEC_FACT"
    rows[0]["accn"] = "filing-1"
    rows[0]["val"] = 99
    assert compare_fact(fact, filing, payload) == "MISMATCH"
    rows.append({"accn": "filing-1", "end": "2025-12-31", "val": 100})
    assert compare_fact(fact, filing, payload) == "AMBIGUOUS_SEC_VALUES"


def test_missing_disclosure_is_not_zero_and_income_duration_must_match():
    fact = {"section": "ic", "concept": "us-gaap_InterestIncome", "unit": "usd", "value": 0}
    filing = {"startDate": "2025-01-01", "endDate": "2025-12-31", "accessNumber": "filing-1"}
    payload = {
        "facts": {
            "us-gaap": {
                "InterestIncome": {
                    "units": {
                        "USD": [
                            {
                                "accn": "filing-1",
                                "end": "2025-12-31",
                                "start": "2025-10-01",
                                "val": 0,
                            }
                        ]
                    }
                }
            }
        }
    }
    assert compare_fact(fact, filing, payload) == "NOT_COVERED_BY_EXACT_SEC_FACT"
    assert compare_fact(fact, filing, {}) == "NOT_COVERED_BY_EXACT_SEC_FACT"


def test_future_filing_and_unrelated_forms_are_not_current_financial_evidence():
    payload = {
        "filings": {
            "recent": {
                "form": ["10-K", "10-Q", "10-K", "4"],
                "filingDate": ["2025-01-01", "2026-08-01", "2026-12-01", "2026-10-01"],
                "reportDate": ["2024-12-31", "2026-06-30", "2026-09-30", ""],
                "accessionNumber": ["1", "2", "3", "4"],
                "primaryDocument": ["a", "b", "c", "d"],
            }
        }
    }
    assert latest_filing(payload, date(2026, 10, 31))["accessionNumber"] == "2"
    payload["filings"]["recent"]["form"].pop()
    with pytest.raises(ValueError, match="Misaligned"):
        latest_filing(payload, date(2026, 10, 31))


def test_cash_flow_borrowings_and_noncontrolling_interest_are_not_debt_or_interest_income():
    filing = {
        "report": {
            "bs": [{"concept": "us-gaap_LongTermDebtCurrent", "unit": "usd", "value": 10}],
            "ic": [
                {
                    "concept": "us-gaap_NetIncomeLossAttributableToNoncontrollingInterest",
                    "unit": "usd",
                    "value": 2,
                }
            ],
            "cf": [
                {
                    "concept": "us-gaap_ProceedsFromIssuanceOfLongTermDebt",
                    "unit": "usd",
                    "value": 90,
                }
            ],
        }
    }
    facts = relevant_facts(filing)
    assert len(facts) == 1 and facts[0]["value"] == 10


def test_current_disclosures_keep_debt_components_separate_and_exclude_ytd_income():
    from scripts.paper_screening_review import current_disclosures

    latest = {"form": "10-Q", "accessionNumber": "q", "reportDate": "2026-09-30"}
    row = {"accn": "q", "end": "2026-09-30"}
    payload = {
        "facts": {
            "us-gaap": {
                "LongTermDebt": {"units": {"USD": [row | {"val": 100}]}},
                "LongTermDebtNoncurrent": {"units": {"USD": [row | {"val": 80}]}},
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            row | {"start": "2026-01-01", "val": 300},
                            row | {"start": "2026-07-01", "val": 110},
                        ]
                    }
                },
            }
        }
    }
    values = current_disclosures(payload, latest)
    assert len(values) == 3
    assert [v["value"] for v in values] == ["100", "80", "110"]
    assert not any(v["value"] == "180" for v in values)


def test_full_review_archives_primary_receipts_without_granting_approval(tmp_path):
    import hashlib
    import json

    import httpx

    from scripts.paper_screening_review import review

    filing = {
        "accessNumber": "annual",
        "startDate": "2025-01-01",
        "endDate": "2025-12-31",
        "report": {
            "bs": [{"concept": "us-gaap_LongTermDebtCurrent", "unit": "usd", "value": 100}],
            "ic": [],
        },
    }
    raw = json.dumps({"symbol": "TEST", "cik": "1", "data": [filing]}).encode()
    (tmp_path / "TEST.json").write_bytes(raw)
    evidence = {
        "items": [
            {
                "symbol": "TEST",
                "accession": "annual",
                "filing_date": "2026-01-01",
                "response_sha256": hashlib.sha256(raw).hexdigest(),
            }
        ]
    }
    (tmp_path / "evidence.json").write_text(json.dumps(evidence))
    recent = {
        "form": ["10-K"],
        "filingDate": ["2026-01-01"],
        "reportDate": ["2025-12-31"],
        "accessionNumber": ["annual"],
        "primaryDocument": ["annual.htm"],
    }
    companyfacts = {
        "cik": 1,
        "facts": {
            "us-gaap": {
                "LongTermDebtCurrent": {
                    "units": {"USD": [{"accn": "annual", "end": "2025-12-31", "val": 100}]}
                }
            }
        },
    }

    def handler(request):
        assert request.method == "GET" and request.url.host == "data.sec.gov"
        return httpx.Response(
            200,
            json={"cik": 1, "filings": {"recent": recent}}
            if "/submissions/" in request.url.path
            else companyfacts,
        )

    result = review(
        tmp_path / "evidence.json",
        tmp_path,
        tmp_path / "audit",
        transport=httpx.MockTransport(handler),
    )
    assert result["approved_symbols"] == []
    assert result["items"][0]["facts"][0]["comparison"] == "EXACT_MATCH"
    assert result["items"][0]["status"] == "NOT_APPROVED"
    assert result["items"][0]["aggregation_or_screening_performed"] is False
    assert (
        result["production_database_mutations"]
        == result["orders_submitted"]
        == result["messages_sent"]
        == 0
    )
    assert (tmp_path / "audit" / "TEST-companyfacts.json").exists()
