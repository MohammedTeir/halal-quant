"""Accelerated synthetic simulator acceptance, never real forward performance.

Creates its own temporary database; ignores production DATABASE_URL and credentials.
"""

import argparse
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config

from apps.api.db import session_factory
from packages.config.settings import get_settings
from packages.schemas.controls import ControlPolicy
from services.paper.engine import mutate, open_account, snapshot
from services.paper.models import PaperAccount
from services.paper.schemas import Command, FillRequest, OpenAccount, OrderRequest, QuoteRequest


def exercise(sessions, days=20):
    start = datetime(2026, 1, 5, 14, tzinfo=UTC)
    account_id = "synthetic-acceptance"
    with sessions.begin() as db:
        open_account(
            db,
            OpenAccount(
                account_id=account_id,
                universe={"SYNTH": "technology"},
                policy=ControlPolicy(fee_per_order="0.25", fee_per_share="0.10", slippage_bps="5"),
            ),
            "synthetic-runner",
            start,
        )

    def run(kind, body, at):
        with sessions.begin() as db:
            return mutate(db, account_id, kind, body, "synthetic-runner", at)

    checks = []
    for day in range(days):
        at = start + timedelta(days=day)
        run("tick", Command(command_id=f"settle:{day}"), at)
        for suffix, seconds, bid, ask, size in [
            ("entry", 0, "99.90", "100", 100),
            ("partial", 1, "99.90", "100", 4),
            ("rest", 2, "99.90", "100", 100),
            ("exit", 4, "100.50", "100.60", 100),
        ]:
            when = at + timedelta(seconds=seconds)
            q = run(
                "quote",
                QuoteRequest(
                    command_id=f"q:{day}:{suffix}",
                    symbol="SYNTH",
                    observed_at=when,
                    bid=bid,
                    ask=ask,
                    bid_size=size,
                    ask_size=size,
                ),
                when,
            )["quote_id"]
            if suffix == "entry":
                order = run(
                    "order",
                    OrderRequest(
                        command_id=f"buy:{day}",
                        symbol="SYNTH",
                        side="BUY",
                        quantity=10,
                        stop_price="95",
                    ),
                    when,
                )["order_id"]
            elif suffix in ("partial", "rest"):
                result = run(
                    "fill",
                    FillRequest(command_id=f"fill:{day}:{suffix}", order_id=order, quote_id=q),
                    when,
                )
                assert result["status"] == (
                    "PARTIALLY_FILLED" if suffix == "partial" else "FILLED"
                ), result
                if suffix == "rest":
                    exit_order = run(
                        "order",
                        OrderRequest(
                            command_id=f"sell:{day}", symbol="SYNTH", side="SELL", quantity=10
                        ),
                        when,
                    )["order_id"]
            else:
                body = FillRequest(command_id=f"sold:{day}", order_id=exit_order, quote_id=q)
                assert run("fill", body, when)["status"] == "FILLED"
                assert run("fill", body, when)["duplicate"]
        with sessions() as db:
            checks.append(
                snapshot(db, db.get(PaperAccount, account_id))["reconciliation"]["status"]
            )
    run("tick", Command(command_id="final-settlement"), start + timedelta(days=days + 3))
    with sessions() as db:
        final = snapshot(db, db.get(PaperAccount, account_id))
    assert all(c == "MATCH" for c in checks) and final["reconciliation"]["status"] == "MATCH"
    assert final["state"]["positions"] == {} and final["state"]["unsettled"] == {}
    return {
        "status": "PASSED",
        "mode": "accelerated_synthetic_acceptance",
        "simulated_days": days,
        "simulated_round_trips": days,
        "daily_reconciliations": checks,
        "final_state": final["state"],
        "final_reconciliation": final["reconciliation"],
        "real_broker_calls": 0,
        "real_telegram_messages": 0,
        "forward_acceptance": "NOT_ESTABLISHED",
        "note": "Injected synthetic time and prices; not elapsed forward testing, representative market history, compliance approval or profitability evidence.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/generated/paper-simulator-smoke.json")
    args = parser.parse_args()
    old_url = os.environ.get("DATABASE_URL")
    try:
        with tempfile.TemporaryDirectory(prefix="hq-paper-") as folder:
            url = "sqlite:///" + str(Path(folder) / "paper.db")
            os.environ["DATABASE_URL"] = url
            get_settings.cache_clear()
            command.upgrade(Config("alembic.ini"), "head")
            engine, sessions = session_factory(url)
            try:
                result = exercise(sessions)
            finally:
                engine.dispose()
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url
        get_settings.cache_clear()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
