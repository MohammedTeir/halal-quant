import json
from datetime import date

import httpx
import pytest

from scripts.paper_filing_facts import CANDIDATES, acquire, extract


def filing(value="1,234", extra=""):
    return f"""<html><xbrli:context id="c"><xbrli:entity><xbrli:identifier>123</xbrli:identifier>
    <xbrldi:explicitMember dimension="s:BusinessAxis">s:GamingMember</xbrldi:explicitMember>
    </xbrli:entity><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate>
    <xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:unit id="u"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
    <ix:nonFraction name="custom:InterestIncome" contextRef="c" unitRef="u"
    format="ixt:num-dot-decimal" scale="6" {extra}>{value}</ix:nonFraction>
    <p>Gaming advertising revenue is a business review lead.</p></html>""".encode()


def test_preserves_dimensions_period_custom_concepts_and_scale():
    result = extract(filing(extra='sign="-"'))
    fact = result["facts"][0]
    assert fact["value"] == "-1.234E+9"
    assert fact["concept"] == "custom:InterestIncome"
    assert "s:GamingMember" in fact["context"]["text"]
    assert "2026-01-01" in fact["context"]["text"]
    assert any(
        f["attributes"].get("dimension") == "s:BusinessAxis" for f in fact["context"]["fields"]
    )
    assert fact["unit"] == "iso4217:USD"
    assert result["business_search_excerpts"]["gaming"]["occurrences"] >= 1


@pytest.mark.parametrize(
    "value,extra",
    [
        ("", ""),
        ("3", 'xsi:nil="1"'),
        ("NaN", ""),
        ("INF", ""),
        ("—", ""),
        ("3", 'xsi:nil="true"'),
        ("3", 'sign="+"'),
        ("3", 'scale="999"'),
    ],
)
def test_invalid_or_nil_is_unknown(value, extra):
    assert extract(filing(value, extra))["facts"][0]["value"] is None


def test_unknown_format_missing_unit_and_overlaps_never_become_totals():
    raw = filing().replace(b"ixt:num-dot-decimal", b"ixt:unknown")
    assert extract(raw)["facts"][0]["value"] is None
    raw = filing().replace(b'unitRef="u"', b'unitRef="missing"')
    assert extract(raw)["facts"][0]["state"] == "UNRESOLVED_CONTEXT_OR_UNIT"
    result = extract(filing() + filing())
    assert len(result["facts"]) == 2
    assert "total" not in result


def test_acquisition_all_ten_is_get_only_and_never_approves(tmp_path):
    def handle(request):
        assert request.method == "GET"
        if request.url.host == "data.sec.gov":
            cik = request.url.path.split("CIK")[1].split(".")[0]
            return httpx.Response(
                200,
                json={
                    "cik": int(cik),
                    "filings": {
                        "recent": {
                            "form": ["10-Q"],
                            "filingDate": ["2026-10-30"],
                            "reportDate": ["2026-09-30"],
                            "accessionNumber": [f"{cik}-26-000001"],
                            "primaryDocument": ["report.htm"],
                        }
                    },
                },
            )
        return httpx.Response(200, content=filing())

    result = acquire(
        tmp_path / "archive", cutoff=date(2026, 11, 2), transport=httpx.MockTransport(handle)
    )
    assert len(result["items"]) == len(CANDIDATES) == 10
    assert all(row["acquisition"] == "OBSERVED" for row in result["items"])
    assert result["approved_symbols"] == []
    assert result["virtual_entries_authorized"] is False
    assert json.loads((tmp_path / "archive/review.json").read_text()) == result
    with pytest.raises(FileExistsError):
        acquire(tmp_path / "archive", cutoff=date(2026, 11, 2))


def test_unavailable_sources_remain_unknown(tmp_path):
    result = acquire(
        tmp_path / "archive",
        cutoff=date(2026, 11, 2),
        transport=httpx.MockTransport(lambda request: httpx.Response(403)),
    )
    assert all(row["acquisition"] == "NOT_CONFIRMED" for row in result["items"])
    assert all("facts" not in row for row in result["items"])


def select(facts, **kwargs):
    from scripts.paper_filing_facts import select_fact

    return select_fact(
        facts,
        "custom:InterestIncome",
        issuer="123",
        unit="iso4217:USD",
        start="2026-01-01",
        end="2026-09-30",
        **kwargs,
    )


def undimensioned(raw):
    return raw.replace(
        b'<xbrldi:explicitMember dimension="s:BusinessAxis">s:GamingMember</xbrldi:explicitMember>',
        b"",
    )


def test_periods_units_and_dimensions_cannot_be_substituted():
    correct = undimensioned(filing())
    others = [
        correct.replace(b"2026-01-01", b"2026-07-01"),
        correct.replace(b"2026-09-30", b"2025-09-30"),
        correct.replace(b"iso4217:USD", b"iso4217:EUR"),
        correct.replace(b"iso4217:USD", b"xbrli:shares"),
        filing(),
        correct.replace(b">123<", b">456<"),
    ]
    for raw in others:
        assert select(extract(raw)["facts"])["status"] == "INSUFFICIENT_EVIDENCE"
    assert select(extract(correct)["facts"])["status"] == "EXACT_CONTEXT_VALUE"
    assert (
        select(extract(filing())["facts"], dimensions={"s:BusinessAxis": "s:GamingMember"})[
            "status"
        ]
        == "EXACT_CONTEXT_VALUE"
    )


def test_instant_does_not_substitute_for_duration():
    from scripts.paper_filing_facts import select_fact

    raw = undimensioned(filing()).replace(
        b"<xbrli:startDate>2026-01-01</xbrli:startDate>\n    <xbrli:endDate>2026-09-30</xbrli:endDate>",
        b"<xbrli:instant>2026-09-30</xbrli:instant>",
    )
    facts = extract(raw)["facts"]
    assert select(facts)["status"] == "INSUFFICIENT_EVIDENCE"
    assert (
        select_fact(
            facts, "custom:InterestIncome", issuer="123", unit="iso4217:USD", end="2026-09-30"
        )["status"]
        == "EXACT_CONTEXT_VALUE"
    )


def test_duplicate_facts_identical_conflicting_and_missing():
    facts = extract(undimensioned(filing()))["facts"]
    single = select(facts)
    assert select(facts * 2) == single | {"occurrences": 2, "reason": "IDENTICAL_DUPLICATES"}
    assert select(facts + [facts[0] | {"value": "999"}])["reason"] == "CONFLICTING_DUPLICATE_VALUES"
    assert select(facts + [facts[0] | {"value": None}])["value"] is None
    assert select([])["value"] is None
    assert select(extract(undimensioned(filing("0")))["facts"])["value"] == "0E+6"


def test_conflicting_context_or_unit_ids_rejected():
    for old, new in [(b"2026-09-30", b"2026-06-30"), (b"iso4217:USD", b"iso4217:EUR")]:
        with pytest.raises(ValueError, match="Conflicting"):
            extract(filing() + filing().replace(old, new))


def test_missing_context_and_typed_dimension_are_unknown():
    raw = undimensioned(filing()).replace(b'contextRef="c"', b'contextRef="missing"')
    assert select(extract(raw)["facts"])["value"] is None
    raw = filing().replace(b"explicitMember", b"typedMember")
    assert select(extract(raw)["facts"])["value"] is None
