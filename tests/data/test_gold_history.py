import json

import pytest

from services.market_data.providers.histdata import save_month
from services.market_data.validate_gold_history import audit_history
from tests.data.test_histdata_fomc import NOW, archive


def test_history_accounts_for_missing_months_and_never_certifies_sessions(tmp_path):
    save_month(tmp_path / "2025-09", archive(720), 2025, 9, NOW, "https://www.histdata.com/")
    report = audit_history(tmp_path, 2025)
    assert report["validated_months"] == 1 and len(report["months"]) == 12
    assert report["total_complete_bars"] == {"1h": 12, "4h": 3}
    assert not report["structural_history_pass"]
    assert not report["session_coverage_verified"] and not report["authorized_for_entry"]
    assert sum(row["status"] == "MISSING" for row in report["months"]) == 11


@pytest.mark.parametrize("change", ["csv", "metadata", "manifest", "source"])
def test_history_rejects_tampered_artifacts_and_conflicting_sources(tmp_path, change):
    path = tmp_path / "2025-09"
    save_month(path, archive(720), 2025, 9, NOW, "https://www.histdata.com/")
    if change == "csv":
        p = path / "1h.csv"
        p.write_text(p.read_text().replace("2001.0", "2000.0"))
    elif change == "metadata":
        p = path / "1h.metadata.json"
        data = json.loads(p.read_text())
        data["quote_basis"] = "ask"
        p.write_text(json.dumps(data))
    elif change == "manifest":
        p = path / "manifest.json"
        data = json.loads(p.read_text())
        data["datasets"]["1h"]["audit"]["complete_bars"] = 13
        p.write_text(json.dumps(data))
    else:
        (path / "source.zip").write_bytes(archive(720, duplicate=True))
    report = audit_history(tmp_path, 2025)
    row = report["months"][8]
    assert row["status"] == ("REJECTED_SOURCE" if change == "source" else "REJECTED_ARTIFACT")
    assert report["validated_months"] == 0 and not report["structural_history_pass"]


def test_history_recomputes_normalization_proof(tmp_path):
    path = tmp_path / "2025-09"
    save_month(
        path,
        archive(720, duplicate=True),
        2025,
        9,
        NOW,
        "https://www.histdata.com/",
        normalize_exact_duplicates=True,
    )
    report = audit_history(tmp_path, 2025)
    assert report["validated_months"] == 1
    assert report["months"][8]["normalization"] == "exact-byte-identical-row-deduplication-v1"
    manifest = json.loads((path / "manifest.json").read_bytes())
    manifest["datasets"]["1h"]["audit"]["exact_duplicate_normalization"]["removed_rows"] = 50
    (path / "manifest.json").write_text(json.dumps(manifest))
    assert audit_history(tmp_path, 2025)["months"][8]["status"] == "REJECTED_ARTIFACT"
