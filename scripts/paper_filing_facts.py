"""Read-only SEC inline-XBRL evidence inventory. Never creates screening approvals."""

import argparse
import hashlib
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from html.parser import HTMLParser
from pathlib import Path

import httpx

from scripts.paper_screening_review import latest_filing

CANDIDATES = {
    "AAPL": "0000320193",
    "NVDA": "0001045810",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "TSLA": "0001318605",
    "META": "0001326801",
    "AVGO": "0001730168",
    "LLY": "0000059478",
    "MU": "0000723125",
}


class FilingParser(HTMLParser):
    """Preserve contexts/units and raw numeric semantics; do not sum overlapping facts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.contexts = {}
        self.units = {}
        self.facts = []
        self.stack = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.stack.append([tag, dict(attrs), []])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        self.text.append(data)
        for node in self.stack:
            node[2].append(data)

    def handle_endtag(self, tag):
        index = next(
            (i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag), None
        )
        if index is None:
            return
        _, attrs, chunks = self.stack[index]
        text = " ".join("".join(chunks).split())
        if tag in {
            "xbrli:identifier",
            "xbrli:instant",
            "xbrli:startdate",
            "xbrli:enddate",
            "xbrldi:explicitmember",
            "xbrldi:typedmember",
        }:
            for parent in self.stack[:index]:
                if parent[0] == "xbrli:context":
                    parent[1].setdefault("fields", []).append(
                        {"tag": tag, "attributes": attrs, "text": text}
                    )
        if tag == "xbrli:context":
            context = {"text": text, "fields": attrs.get("fields", [])}
            key = attrs.get("id")
            if key in self.contexts and self.contexts[key] != context:
                raise ValueError("Conflicting context definitions")
            self.contexts[key] = context
        elif tag == "xbrli:unit":
            key = attrs.get("id")
            if key in self.units and self.units[key] != text:
                raise ValueError("Conflicting unit definitions")
            self.units[key] = text
        elif tag == "ix:nonfraction":
            amount = None
            state = "UNSUPPORTED_OR_INVALID_NUMERIC"
            # Only known dot-decimal formats are accepted. Nil/unknown formats stay unknown.
            fmt = attrs.get("format", "").split(":")[-1].lower()
            if attrs.get("xsi:nil") not in ("true", "1") and fmt in (
                "",
                "num-dot-decimal",
                "numdotdecimal",
            ):
                try:
                    number = Decimal(text.replace(",", "").replace(" ", ""))
                    scale = int(attrs.get("scale", "0"))
                    if not -20 <= scale <= 20 or attrs.get("sign", "") not in ("", "-"):
                        raise ValueError("Unsupported scale/sign")
                    # scaleb with sufficient precision avoids rounding large disclosures.
                    with localcontext() as ctx:
                        ctx.prec = max(60, len(number.as_tuple().digits) + abs(scale))
                        number = number.scaleb(scale)
                        if attrs.get("sign") == "-":
                            number = -number
                    if number.is_finite():
                        amount, state = str(number), "PARSED_NOT_RECONCILED"
                except (InvalidOperation, ValueError):
                    pass
            self.facts.append(
                {
                    "concept": attrs.get("name"),
                    "context_ref": attrs.get("contextref"),
                    "unit_ref": attrs.get("unitref"),
                    "raw_text": text,
                    "value": amount,
                    "state": state,
                    "decimals": attrs.get("decimals"),
                    "format": attrs.get("format"),
                }
            )
        del self.stack[index:]


def extract(raw):
    parser = FilingParser()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    for fact in parser.facts:
        fact["context"] = parser.contexts.get(fact["context_ref"])
        fact["unit"] = parser.units.get(fact["unit_ref"])
        if fact["context"] is None or fact["unit"] is None:
            fact["state"] = "UNRESOLVED_CONTEXT_OR_UNIT"
            fact["value"] = None
    plain = " ".join(" ".join(parser.text).split())
    terms = (
        "interest income",
        "interest-bearing",
        "marketable securities",
        "debt",
        "gaming",
        "advertising",
        "entertainment",
        "insurance",
        "alcohol",
        "revenue",
    )
    excerpts = {}
    for term in terms:
        matches = list(re.finditer(re.escape(term), plain, re.IGNORECASE))
        excerpts[term] = {
            "occurrences": len(matches),
            "samples": [plain[max(0, m.start() - 160) : m.end() + 240] for m in matches[:3]],
        }
    return {
        "facts": parser.facts,
        "business_search_excerpts": excerpts,
        "scope": "Search excerpts are leads, not business classifications. Context text retains dimensions; no consolidation or completeness inferred.",
    }


def select_fact(facts, concept, *, issuer, unit, end, start=None, dimensions=None):
    """Exact-context lookup only; duplicates never add or override unknown/conflicting values.

    This selects an inventory value, not a complete screening input or approval.
    Typed dimensions are unsupported and excluded. Default scope is undimensioned.
    """
    for day in (start, end):
        if day is not None and date.fromisoformat(day).isoformat() != day:
            raise ValueError("Canonical dates required")
    if start is not None and start > end:
        raise ValueError("Reversed period")
    expected_dimensions = dimensions or {}
    matches = []
    for fact in facts:
        if fact.get("concept") != concept or fact.get("unit") != unit:
            continue
        fields = (fact.get("context") or {}).get("fields", [])
        by_tag = {}
        for field in fields:
            by_tag.setdefault(field["tag"], []).append(field)
        if [f["text"] for f in by_tag.get("xbrli:identifier", [])] != [issuer]:
            continue
        if "xbrldi:typedmember" in by_tag:
            continue
        members = by_tag.get("xbrldi:explicitmember", [])
        actual_dimensions = {f["attributes"].get("dimension"): f["text"] for f in members}
        if len(actual_dimensions) != len(members) or actual_dimensions != expected_dimensions:
            continue
        expected_period = (
            {"xbrli:instant": [end]}
            if start is None
            else {"xbrli:startdate": [start], "xbrli:enddate": [end]}
        )
        actual_period = {
            tag: [f["text"] for f in by_tag[tag]]
            for tag in ("xbrli:instant", "xbrli:startdate", "xbrli:enddate")
            if tag in by_tag
        }
        if actual_period == expected_period:
            matches.append(fact)
    result = {
        "status": "INSUFFICIENT_EVIDENCE",
        "value": None,
        "occurrences": len(matches),
        "reason": "NO_EXACT_CONTEXT_MATCH",
    }
    if not matches:
        return result
    values = set()
    for fact in matches:
        try:
            value = Decimal(str(fact.get("value")))
        except InvalidOperation:
            value = Decimal("NaN")
        if fact.get("state") != "PARSED_NOT_RECONCILED" or not value.is_finite():
            return result | {"reason": "MISSING_OR_UNSUPPORTED_DUPLICATE_VALUE"}
        values.add(value)
    if len(values) != 1:
        return result | {"reason": "CONFLICTING_DUPLICATE_VALUES"}
    return result | {
        "status": "EXACT_CONTEXT_VALUE",
        "value": str(values.pop()),
        "reason": "IDENTICAL_DUPLICATES" if len(matches) > 1 else "SINGLE_VALUE",
    }


def acquire(archive, *, cutoff, transport=None):
    archive.mkdir(mode=0o700, parents=True, exist_ok=False)
    items = []
    with httpx.Client(
        timeout=45,
        follow_redirects=False,
        transport=transport,
        headers={"User-Agent": "halal-quant research https://github.com/MohammedTeir/halal-quant"},
    ) as client:
        for symbol, cik in CANDIDATES.items():
            row = {
                "symbol": symbol,
                "cik": cik,
                "status": "NOT_APPROVED",
                "screening_outcome": "INSUFFICIENT_EVIDENCE",
                "receipts": [],
            }

            def get(url, name, row=row):
                response = client.get(url)
                row["receipts"].append(
                    {
                        "url": url,
                        "http_status": response.status_code,
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                    }
                )
                if response.status_code != 200 or len(response.content) > 32 * 1024 * 1024:
                    raise ValueError("Source unavailable or oversized")
                (archive / name).write_bytes(response.content)
                return response.content

            try:
                submissions = json.loads(
                    get(
                        f"https://data.sec.gov/submissions/CIK{cik}.json",
                        f"{symbol}-submissions.json",
                    )
                )
                if int(submissions["cik"]) != int(cik):
                    raise ValueError("Issuer mismatch")
                filing = latest_filing(submissions, cutoff)
                if not filing or filing["reportDate"] > cutoff.isoformat():
                    raise ValueError("No eligible filing")
                accession, document = filing["accessionNumber"], filing["primaryDocument"]
                if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession) or not re.fullmatch(
                    r"[\w.-]+\.html?", document
                ):
                    raise ValueError("Unsafe filing path")
                row["filing"] = filing
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{document}"
                row.update(extract(get(url, f"{symbol}-filing.htm")))
                row["acquisition"] = "OBSERVED"
            except (httpx.HTTPError, ValueError, KeyError, TypeError, UnicodeError):
                row["acquisition"] = "NOT_CONFIRMED"
            row["remaining"] = [
                "Consolidated debt and cash/interest-item mapping",
                "Same-period complete non-compliant income",
                "Business activity and purification review",
                "Instrument evidence and qualified methodology/asset review",
            ]
            items.append(row)
            print(f"{symbol}: {row['acquisition']}; NOT_APPROVED", flush=True)
    result = {
        "observed_at": datetime.now(UTC).isoformat(),
        "cutoff": cutoff.isoformat(),
        "items": items,
        "approved_symbols": [],
        "virtual_entries_authorized": False,
        "scope": "Independent primary-source inventory only; no database, order or messaging calls.",
    }
    (archive / "review.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--cutoff", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    acquire(args.archive, cutoff=args.cutoff)


if __name__ == "__main__":
    main()
