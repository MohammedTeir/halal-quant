"""Same-origin read-only dashboard; credentials stay out of assets and URLs."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from apps.api.db import AuditRecord, BrokerCapture, DecisionRecord, SignalRecord, utcnow
from services.market_data.event_store import aware
from services.notifications.preview import signal_preview

ROOT = Path(__file__).resolve().parents[2]
REPORTS = {
    "portfolio": "milestone6-portfolio-acceptance-2026-10-30.json",
    "validation": "milestone6-multiwindow-acceptance-2026-10-30.json",
    "gold": "milestone6-real-gold-diagnostic-2026-10-30.json",
}


def mount_dashboard(app, sessions, authenticate):
    static = Path(__file__).parent / "static"
    app.mount("/dashboard/assets", StaticFiles(directory=static), name="dashboard-assets")

    @app.middleware("http")
    async def dashboard_security(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(
            ("/dashboard", "/api/v1/dashboard", "/api/v1/portfolio", "/api/v1/notifications")
        ):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            )
        return response

    @app.get("/dashboard", include_in_schema=False)
    def dashboard_page():
        return FileResponse(static / "index.html")

    router = APIRouter(dependencies=[Depends(authenticate)])

    @router.get("/api/v1/dashboard/overview")
    def overview():
        with sessions() as session:
            return {
                "as_of": utcnow().isoformat(),
                "mode": "research",
                "authorized": False,
                "live_execution": False,
                "telegram_delivery": "SERVER_OUTBOX_REQUIRES_CONFIGURED_WORKER",
                "counts": {
                    name: session.scalar(select(func.count()).select_from(model))
                    for name, model in [
                        ("signals", SignalRecord),
                        ("decisions", DecisionRecord),
                        ("audit", AuditRecord),
                    ]
                },
                "milestones": {
                    "current": 8,
                    "dashboard": "BILINGUAL_ACCOUNTS_AND_DELIVERY",
                    "paper_trading": "INTERNAL_FORWARD_ACCEPTANCE_PENDING",
                    "research_performance_accepted": False,
                    "qualified_operational_signoff": False,
                },
            }

    @router.get("/api/v1/portfolio")
    def portfolio():
        now = utcnow()
        with sessions() as session:
            row = session.scalar(
                select(BrokerCapture)
                .where(BrokerCapture.kind == "account")
                .order_by(BrokerCapture.sequence.desc())
                .limit(1)
            )
            if row is None or row.status != "SUCCEEDED" or not row.payload or not row.completed_at:
                return {
                    "status": "UNAVAILABLE",
                    "authorized": False,
                    "positions": [],
                    "reason": "NO_SUCCESSFUL_LATEST_ACCOUNT_CAPTURE",
                }
            facts = row.payload
            observed = aware(datetime.fromisoformat(facts["observed_at"]))
            fresh = observed <= aware(row.completed_at) <= now and now - observed <= timedelta(
                seconds=30
            )
            return {
                "status": "CURRENT_OBSERVATION" if fresh else "STALE_OBSERVATION",
                "authorized": False,
                "observed_at": observed.isoformat(),
                "provider": facts["provider"],
                "reported_cash": facts.get("reported_cash"),
                "equity": facts.get("equity"),
                "settled_cash": facts.get("settled_cash")
                if facts.get("settled_cash_verified") is True
                else None,
                "proofs": {
                    k: facts.get(k) is True
                    for k in (
                        "cash_account_verified",
                        "settled_cash_verified",
                        "lending_disabled_verified",
                        "borrowing_disabled_verified",
                        "positions_complete",
                        "orders_complete",
                    )
                },
                "positions": [
                    {
                        "symbol": p.get("symbol"),
                        "quantity": p.get("quantity"),
                        "sellable_quantity": p.get("available_quantity"),
                        "market_value": p.get("market_value"),
                    }
                    for p in facts.get("positions", [])
                ],
                "open_order_count": len(facts.get("orders", [])),
                "freshness_policy": "30-second display window; not control authorization",
            }

    @router.get("/api/v1/dashboard/research")
    def research():
        items = []
        for label, filename in REPORTS.items():
            path = ROOT / "reports" / filename
            try:
                if path.stat().st_size > 1_000_000:
                    raise ValueError("Report too large")
                payload = json.loads(path.read_text())
                if not isinstance(payload, dict):
                    raise TypeError("Invalid report")
                items.append(
                    {
                        "label": label,
                        "filename": filename,
                        "available": True,
                        "status": payload.get("status", payload.get("purpose")),
                        "tests_passed": payload.get("tests_passed"),
                        "performance_accepted": False,
                        "source_sha256": payload.get("source_sha256"),
                        "gates": payload.get("research_gates"),
                        "runs": payload.get("runs"),
                        "authorized": False,
                    }
                )
            except (OSError, ValueError, TypeError):
                items.append(
                    {"label": label, "filename": filename, "available": False, "authorized": False}
                )
        return {"items": items, "performance_accepted": False, "authorized": False}

    @router.get("/api/v1/notifications/preview")
    def notifications(language: Literal["en", "ar"] = "en"):
        with sessions() as session:
            rows = session.scalars(
                select(SignalRecord)
                .order_by(SignalRecord.received_at.desc(), SignalRecord.event_id)
                .limit(30)
            )
            return {
                "delivery_enabled": False,
                "items": [signal_preview(row.payload, language) for row in rows],
            }

    app.include_router(router)
