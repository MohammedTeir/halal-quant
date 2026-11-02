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
