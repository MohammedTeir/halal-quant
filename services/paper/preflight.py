"""Read-only deployment inventory; no provider calls, leases, orders or messages."""

import json

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from apps.api.db import session_factory, utcnow
from packages.config.settings import get_settings
from services.notifications.models import User
from services.paper.forward import approved_run
from services.paper.models import PaperAccount, PaperRun


def inspect(sessions, settings):
    blockers = []
    enabled = settings.paper_trading_enabled and settings.paper_forward_enabled
    provider_configured = bool(
        settings.alpaca_api_key.get_secret_value() and settings.alpaca_secret_key.get_secret_value()
    )
    if not enabled:
        blockers.append("FORWARD_FLAGS_DISABLED")
    if not provider_configured:
        blockers.append("ALPACA_NOT_CONFIGURED")
    with sessions() as db:
        revision = db.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != "0009_paper_forward":
            return {"status": "BLOCKED", "blockers": ["MIGRATION_REQUIRED"]}
        roles = {
            role: db.scalar(
                select(func.count()).select_from(User).where(User.enabled, User.role == role)
            )
            for role in ("operator", "reviewer")
        }
        for role, count in roles.items():
            if not count:
                blockers.append("ENABLED_" + role.upper() + "_REQUIRED")
        runs = db.scalars(select(PaperRun).order_by(PaperRun.created_at.desc()).limit(20)).all()
        items = []
        for run in runs:
            current = True
            try:
                approved_run(db, db.get(PaperAccount, run.account_id), utcnow())
            except (ValueError, AttributeError):
                current = False
            items.append(
                {"run_id": run.id, "state": run.state["status"], "entry_review_current": current}
            )
        if not any(item["entry_review_current"] for item in items):
            blockers.append("CURRENT_REVIEWED_CAMPAIGN_REQUIRED")
    return {
        "status": "CONFIGURATION_PRESENT" if not blockers else "BLOCKED",
        "migration": revision,
        "forward_flags_enabled": bool(enabled),
        "alpaca_configured": provider_configured,
        "enabled_roles": roles,
        "recent_runs": items,
        "blockers": blockers,
        "scope": "Configuration inventory only; not source coverage, market connectivity or forward acceptance",
        "mutations": 0,
        "provider_calls": 0,
        "messages_sent": 0,
    }


def main():
    engine = None
    try:
        settings = get_settings()
        if "database_url" not in settings.model_fields_set:
            result = {"status": "BLOCKED", "blockers": ["DATABASE_URL_NOT_CONFIGURED"]}
        else:
            engine, sessions = session_factory(settings.database_url)
            result = inspect(sessions, settings)
    except (ValueError, SQLAlchemyError, OSError):
        result = {
            "status": "BLOCKED",
            "blockers": ["PRIVATE_CONFIGURATION_OR_DATABASE_UNAVAILABLE"],
        }
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
