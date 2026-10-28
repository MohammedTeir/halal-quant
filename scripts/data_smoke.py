"""Authenticated local API check; persists clearly labelled synthetic observations."""

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx


def smoke_data():
    now = datetime.now(UTC)
    marker = uuid4().hex
    symbol = f"SMOKE:{marker}"
    provider = "synthetic_smoke"
    common = {
        "provider": provider,
        "synthetic": True,
        "revision": 1,
        "published_at": (now - timedelta(seconds=2)).isoformat(),
    }
    facts = {
        "news": common
        | {
            "kind": "news",
            "item_id": f"news-{marker}",
            "source_name": "Synthetic smoke fixture",
            "url": f"https://news.example/{marker}",
            "headline": "Synthetic test article",
            "symbols": [symbol],
            "asset_classes": ["stock"],
        },
        "calendar": common
        | {
            "kind": "calendar",
            "item_id": f"calendar-{marker}",
            "title": "Synthetic earnings window",
            "event_type": "earnings",
            "scheduled_at": (now + timedelta(days=1)).isoformat(),
            "severity": "high",
            "symbols": [symbol],
            "asset_classes": ["stock"],
        },
        "corporate_actions": common
        | {
            "kind": "corporate_actions",
            "item_id": f"split-{marker}",
            "symbol": symbol,
            "action_type": "split",
            "split_ratio": "2",
            "effective_at": (now + timedelta(days=2)).isoformat(),
        },
    }
    write_headers = {"X-Data-Key": os.environ["DATA_INGESTION_KEY"]}
    read_headers = {"Authorization": f"Bearer {os.environ['DASHBOARD_API_KEY']}"}
    received = []
    with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=15) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get("/api/v1/news").status_code == 401
        for kind, fact in facts.items():
            batch_id = f"smoke-{kind}-{marker}"
            batch = {
                "kind": kind,
                "provider": provider,
                "batch_id": batch_id,
                "synthetic": True,
                "records": [fact],
            }
            first = client.post("/api/v1/data/import", headers=write_headers, json=batch)
            assert first.status_code == 200, first.status_code
            assert first.json()["inserted"] == 1 and not first.json()["duplicate"]
            received.append(first.json()["received_at"])
            replay = client.post("/api/v1/data/import", headers=write_headers, json=batch)
            assert replay.status_code == 200 and replay.json()["duplicate"]
            assert replay.json()["received_at"] == first.json()["received_at"]
            subject = hashlib.sha256(
                json.dumps(
                    [provider, kind, batch_id], sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            audits = client.get("/api/v1/audit", headers=read_headers).json()["items"]
            assert sum(record["subject"] == subject for record in audits) == 1
        for route in ("news", "economic-events", "corporate-actions"):
            response = client.get(
                f"/api/v1/{route}", headers=read_headers, params={"symbol": symbol}
            )
            assert response.status_code == 200 and len(response.json()["items"]) == 1
            past = client.get(
                f"/api/v1/{route}",
                headers=read_headers,
                params={"symbol": symbol, "as_of": (now - timedelta(minutes=1)).isoformat()},
            )
            assert past.status_code == 200 and not past.json()["items"]
        status = client.get(
            "/api/v1/data/status",
            headers=read_headers,
            params={"provider": provider, "kind": "news"},
        ).json()
        assert status["state"] == "FRESH" and status["synthetic"]
        assert not status["required_feed_available"] and not status["authorized_for_entry"]
    return {
        "purpose": "synthetic_data_ingestion_acceptance_only",
        "received_at": received,
        "atomic_imports": 3,
        "replay_single_audit_per_batch": True,
        "point_in_time_exclusion": True,
        "three_fact_routes_checked": True,
        "synthetic_feed_cannot_satisfy_required_feed": True,
        "authorized_for_entry": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Output exists; choose a new path to preserve evidence")
    result = smoke_data()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as target:
            json.dump(result, target, indent=2, sort_keys=True)
            target.write("\n")
    print(
        "PASS: authenticated facts, idempotency, point-in-time reads and synthetic feed fail-closed behavior"
    )


if __name__ == "__main__":
    main()
