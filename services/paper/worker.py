"""Explicit opt-in internal forward worker: read-only market data, virtual orders."""

import argparse
import json
import secrets
import signal
import threading
import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from apps.api.db import session_factory, utcnow
from packages.config.settings import get_settings
from services.controls.broker import BrokerError
from services.paper.forward import approved_run, protocol_hash
from services.paper.models import PaperAccount, PaperRun
from services.paper.provider import AlpacaPaperData
from services.paper.runner import CriticalCycle, LeaseLost, claim, problem, process, release
from services.paper.schemas import OpenAccount


def check(sessions, settings, run_id):
    with sessions() as db:
        if db.scalar(text("SELECT version_num FROM alembic_version")) != "0009_paper_forward":
            raise ValueError("Paper forward migration required")
        run = db.get(PaperRun, run_id)
        if not run:
            raise ValueError("Create a paper forward protocol first")
        account = db.get(PaperAccount, run.account_id)
        approved_run(db, account, utcnow(), current_entry_review=False)
        try:
            approved_run(db, account, utcnow())
            entry_review_current = True
        except ValueError:
            entry_review_current = False
        config = OpenAccount.model_validate(account.config)
        return {
            "database": "ready",
            "run_id": run.id,
            "protocol_sha256": protocol_hash(run),
            "entry_review_current": entry_review_current,
            "account_id": account.id,
            "mode": "internal_forward",
            "enabled": bool(settings.paper_trading_enabled and settings.paper_forward_enabled),
            "provider_configured": bool(
                settings.alpaca_api_key.get_secret_value()
                and settings.alpaca_secret_key.get_secret_value()
            ),
            "cadence_seconds": run.protocol["cadence_seconds"],
            "tickers": [config.provider_symbols.get(s, s) for s in config.universe],
            "settlement_days": config.settlement_days,
            "real_orders_submitted": 0,
            "messages_sent": 0,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Read-only local configuration check; no provider calls or worker lease",
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        settings = get_settings()
        engine, sessions = session_factory(settings.database_url)
    except (ValueError, SQLAlchemyError, OSError):
        parser.exit(
            1,
            "Paper worker configuration is invalid; review private settings without sharing credentials.\n",
        )
    owner = secrets.token_hex(24)
    stop = threading.Event()
    previous_handlers = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[sig] = signal.getsignal(sig)
        signal.signal(sig, lambda *_: stop.set())
    acquired = False
    try:
        ready = check(sessions, settings, args.run_id)
        print(json.dumps(ready), flush=True)
        if args.check:
            return
        if not ready["enabled"] or not ready["provider_configured"]:
            raise ValueError(
                "Enable paper simulation/forward mode and configure read-only Alpaca credentials privately"
            )
        provider = AlpacaPaperData(settings)
        failures = 0
        while not stop.is_set():
            started = time.monotonic()
            held = claim(sessions, args.run_id, owner)
            acquired = True
            try:
                bundle = provider.snapshot(ready["tickers"], ready["settlement_days"])
                result = process(sessions, args.run_id, owner, held, bundle)
                failures = 0
            except CriticalCycle:
                result = problem(
                    sessions,
                    args.run_id,
                    owner,
                    held,
                    "POST_CYCLE_RECONCILIATION_MISMATCH",
                    critical=True,
                )
            except BrokerError:
                failures += 1
                result = problem(sessions, args.run_id, owner, held, "MARKET_DATA_UNAVAILABLE")
            except LeaseLost:
                raise
            except ValueError:
                failures += 1
                result = problem(
                    sessions, args.run_id, owner, held, "MARKET_RECEIPT_OR_CURRENT_REVIEW_INVALID"
                )
            print(json.dumps(result), flush=True)
            if args.once or result["status"] == "CRITICAL":
                break
            delay = (
                max(ready["cadence_seconds"], min(900, 60 * 2 ** min(failures, 4)))
                if failures
                else ready["cadence_seconds"]
            )
            stop.wait(max(0, delay - (time.monotonic() - started)))
    except LeaseLost:
        parser.exit(
            1, "Paper worker lease is held by another process or expired; no matching performed.\n"
        )
    except (ValueError, SQLAlchemyError, OSError):
        parser.exit(
            1,
            "Paper worker stopped safely; check private configuration, review expiry, database and logs. No external order transport exists.\n",
        )
    finally:
        try:
            if acquired:
                try:
                    release(sessions, args.run_id, owner)
                except SQLAlchemyError:
                    pass
        finally:
            engine.dispose()
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)


if __name__ == "__main__":
    main()
