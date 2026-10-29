"""Recompute a complete year's gold artifacts from retained source archives.

Every month must be accounted for. Rejected/missing months fail the structural
history gate. This does not certify provider sessions, price accuracy or liquidity.
"""

import argparse
import hashlib
import json
from pathlib import Path

from services.market_data.csv_data import load_csv
from services.market_data.providers.histdata import HistDataError, convert_archive


def audit_history(root: Path, year: int):
    if not 2000 <= year <= 9999:
        raise ValueError("Invalid historical year")
    rows = []
    for month in range(1, 13):
        path = root / f"{year}-{month:02}"
        row = {"month": f"{year}-{month:02}", "status": "MISSING"}
        rows.append(row)
        archive = path / "source.zip"
        if not archive.exists():
            continue
        raw = archive.read_bytes()
        row["source_sha256"] = hashlib.sha256(raw).hexdigest()
        try:
            # A missing manifest still permits strict source rejection diagnosis.
            manifest = (
                json.loads((path / "manifest.json").read_bytes())
                if (path / "manifest.json").exists()
                else {}
            )
            if not isinstance(manifest, dict):
                raise TypeError("Invalid manifest")
            mode = manifest.get("normalization")
            if mode not in (None, "exact-byte-identical-row-deduplication-v1"):
                raise ValueError("Unknown normalization")
            converted = {
                label: convert_archive(
                    raw, year, month, seconds, normalize_exact_duplicates=mode is not None
                )
                for label, seconds in (("1h", 3600), ("4h", 14400))
            }
        except HistDataError as error:
            row.update(status="REJECTED_SOURCE", code=str(error))
            continue
        except (ValueError, OSError, TypeError):
            row.update(status="REJECTED_ARTIFACT", code="GOLD_ARTIFACT_MISMATCH")
            continue
        try:
            manifest = json.loads((path / "manifest.json").read_bytes())
            if manifest["source_sha256"] != row["source_sha256"]:
                raise ValueError("Source archive hash mismatch")
            audits = {}
            for label, (expected_csv, expected_audit) in converted.items():
                csv_path, metadata_path = path / f"{label}.csv", path / f"{label}.metadata.json"
                if csv_path.read_bytes() != expected_csv.encode():
                    raise ValueError("Derived candle bytes differ from source")
                dataset = load_csv(csv_path, metadata_path)
                spec = dataset.spec
                if (
                    spec.source != "histdata_xauusd_bid"
                    or spec.symbol != "XAUUSD"
                    or spec.asset_class != "gold"
                    or spec.quote_basis != "bid"
                    or spec.volume_semantics != "unavailable_zero_placeholder"
                    or spec.timeframe_seconds != (3600 if label == "1h" else 14400)
                    or spec.price_basis != "unadjusted"
                    or spec.synthetic
                    or spec.retrieved_at.isoformat() != manifest["received_at"]
                    or dataset.manifest() != manifest["datasets"][label]["dataset"]
                    or expected_audit != manifest["datasets"][label]["audit"]
                ):
                    raise ValueError("Artifact provenance mismatch")
                # Summarize counts; full partial-bucket details remain in each manifest.
                audits[label] = {
                    key: value
                    for key, value in expected_audit.items()
                    if key != "incomplete_buckets"
                } | {
                    "incomplete_bucket_count": len(expected_audit["incomplete_buckets"]),
                    "csv_sha256": dataset.csv_sha256,
                    "metadata_sha256": dataset.metadata_sha256,
                    "first_bar_close": dataset.manifest()["first_bar_close"],
                    "last_bar_close": dataset.manifest()["last_bar_close"],
                }
            row.update(status="VALIDATED", normalization=mode, datasets=audits)
        except (ValueError, OSError, KeyError, TypeError):
            row.update(status="REJECTED_ARTIFACT", code="GOLD_ARTIFACT_MISMATCH")
    valid = [row for row in rows if row["status"] == "VALIDATED"]
    return {
        "year": year,
        "expected_months": 12,
        "validated_months": len(valid),
        "structural_history_pass": len(valid) == 12,
        "total_complete_bars": {
            label: sum(row["datasets"][label]["complete_bars"] for row in valid)
            for label in ("1h", "4h")
        },
        "months": rows,
        "session_coverage_verified": False,
        "provider_independently_verified": False,
        "continuous_history_approved": False,
        "authorized_for_entry": False,
        "limitations": [
            "No independently verified spot-gold session schedule was supplied",
            "Observed gaps are not classified as market closure versus missing data",
            "Bid quotes and unavailable volume do not establish executable prices or liquidity",
            "Rejected months are retained and never repaired or omitted from the gate",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_history(args.root, args.year)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as output:
            json.dump(result, output, sort_keys=True, indent=2, allow_nan=False)
            output.write("\n")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    parser.exit(0 if result["structural_history_pass"] else 1)


if __name__ == "__main__":
    main()
