"""Temporary local API/database smoke with an HTTP-mocked Gemini; never a real key/call."""

import argparse
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.config.settings import Settings, get_settings
from services.news_intelligence.providers.gemini import GeminiAdapter


def smoke():
    calls = []

    def handler(request):
        calls.append(request)
        document = json.loads(json.loads(request.content)["contents"][0]["parts"][0]["text"])
        target, source = document["target"], document["sources"][0]
        assessment = target | {
            "schema_version": "1.0",
            "event_type": "company",
            "sentiment": "positive",
            "sentiment_score": 0.6,
            "relevance": 1.0,
            "severity": "low",
            "confidence": 0.9,
            "evidence": [{"source_id": target["event_id"], "quote": source["headline"]}],
            "market_impact": "positive",
            "recommended_policy": "ALLOW",
            "requires_human_review": False,
        }
        return httpx.Response(
            200,
            json={
                "modelVersion": "gemini-mock-001",
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"role": "model", "parts": [{"text": json.dumps(assessment)}]},
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 20,
                    "candidatesTokenCount": 30,
                    "totalTokenCount": 50,
                },
            },
        )

    original_url = os.environ.get("DATABASE_URL")
    try:
        with TemporaryDirectory(prefix="halal-gemini-smoke-") as temporary:
            url = f"sqlite:///{Path(temporary) / 'smoke.db'}"
            os.environ["DATABASE_URL"] = url
            get_settings.cache_clear()
            command.upgrade(Config("alembic.ini"), "head")
            keys = {
                name: secrets.token_hex(16)
                for name in (
                    "dashboard_api_key",
                    "tradingview_webhook_key",
                    "data_ingestion_key",
                    "analysis_api_key",
                )
            }
            config = Settings(
                database_url=url,
                **keys,
                gemini_enabled=True,
                gemini_api_key="nonfunctional-mock-key",
                gemini_model="gemini-mock",
                news_provider="synthetic_mock",
                calendar_provider="synthetic_mock",
                _env_file=None,
            )
            app = create_app(config)
            app.state.gemini_adapter_factory = lambda cfg: GeminiAdapter(
                cfg, transport=httpx.MockTransport(handler), sleep=lambda _: None
            )
            with TestClient(app) as client:
                now = datetime.now(UTC).isoformat()
                record = {
                    "kind": "news",
                    "provider": "synthetic_mock",
                    "synthetic": True,
                    "item_id": "news-1",
                    "published_at": now,
                    "source_name": "Mock fixture",
                    "url": "https://news.example/mock",
                    "headline": "Synthetic result available",
                    "symbols": ["EXAMPLE"],
                    "asset_classes": ["stock"],
                }
                batch = {
                    "provider": "synthetic_mock",
                    "kind": "news",
                    "batch_id": "batch-1",
                    "synthetic": True,
                    "records": [record],
                }
                assert (
                    client.post(
                        "/api/v1/data/import",
                        headers={"X-Data-Key": keys["data_ingestion_key"]},
                        json=batch,
                    ).status_code
                    == 200
                )
                read = {"Authorization": f"Bearer {keys['dashboard_api_key']}"}
                analysis = {"X-Analysis-Key": keys["analysis_api_key"]}
                source_id = client.get("/api/v1/news", headers=read).json()["items"][0][
                    "observations"
                ][0]["source_id"]
                request = {
                    "classification_id": "mock-generation-1",
                    "source_id": source_id,
                    "symbol": "EXAMPLE",
                    "asset_class": "stock",
                }
                response = client.post(
                    "/api/v1/news/classifications/generate", headers=analysis, json=request
                )
                assert response.status_code == 200, response.json()
                assert response.json()["model_version"] == "gemini-mock-001"
                assert response.json()["advisory_only"] and response.json()["synthetic"]
                assert client.post(
                    "/api/v1/news/classifications/generate", headers=analysis, json=request
                ).json()["duplicate"]
                job = client.get(
                    "/api/v1/news/classification-jobs/mock-generation-1", headers=read
                ).json()
                assert job["status"] == "SUCCEEDED" and len(calls) == 1
                assert "nonfunctional-mock-key" not in json.dumps(job)
                signal = {
                    "schema_version": "1.0",
                    "strategy": "adaptive_pullback",
                    "strategy_version": "1.0.0",
                    "asset_class": "stock",
                    "symbol": "EXAMPLE",
                    "timeframe": "240",
                    "action": "ENTRY_CANDIDATE",
                    "event_id": "mock-signal-1",
                    "bar_time": now,
                    "price": "100",
                }
                assert (
                    client.post(
                        "/api/v1/webhooks/tradingview",
                        headers={"X-Webhook-Key": keys["tradingview_webhook_key"]},
                        json=signal,
                    ).status_code
                    == 200
                )
                decision = client.post(
                    "/api/v1/decisions/evaluate",
                    headers=analysis,
                    json={
                        "evaluation_id": "mock-evaluation-1",
                        "signal_id": "mock-signal-1",
                        "score": 1.0,
                    },
                ).json()
                assert decision["status"] == "WAIT_DATA" and not decision["authorized"]
                summary = {
                    "purpose": "gemini_http_mock_acceptance_only",
                    "real_provider_calls": 0,
                    "temporary_database": True,
                    "mock_provider_requests": len(calls),
                    "job_status": job["status"],
                    "reported_mock_model_version": response.json()["model_version"],
                    "usage_fixture": job["result_metadata"]["usage"],
                    "replay_avoided_second_provider_request": True,
                    "key_absent_from_job_response": True,
                    "decision_status": decision["status"],
                    "authorized": False,
                }
            app.state.engine.dispose()
            return summary
    finally:
        if original_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_url
        get_settings.cache_clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Output exists; choose a new evidence path")
    result = smoke()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as target:
            json.dump(result, target, indent=2, sort_keys=True)
            target.write("\n")
    print(
        "PASS: mocked Gemini → grounded assessment → durable job/replay → blocked research decision; zero real provider calls"
    )


if __name__ == "__main__":
    main()
