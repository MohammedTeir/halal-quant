"""Explicit local-admin read-only capture; sanitized reports, no order capability."""

import argparse
import json
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from apps.api.db import session_factory
from packages.config.settings import get_settings
from services.controls.broker import AlpacaControls, BrokerError
from services.controls.capture import refresh
from services.controls.store import get_capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("account", "quote"), required=True)
    parser.add_argument("--symbol")
    parser.add_argument("--refresh-id", required=True)
    parser.add_argument("--report-output", required=True, type=Path)
    args = parser.parse_args()
    if args.report_output.exists():
        parser.error("Report exists; retain prior observations")
    if args.kind == "quote" and not args.symbol:
        parser.error("A quote symbol is required")
    engine = None
    try:
        settings = get_settings()
        engine, sessions = session_factory(settings.database_url)
        result = refresh(
            sessions, args.refresh_id, args.kind, args.symbol, lambda: AlpacaControls(settings)
        )
        report = {key: value for key, value in result.items() if key != "scope"}
        with sessions() as session:
            record = get_capture(session, args.refresh_id)
            if record.payload and args.kind == "account":
                report["capabilities"] = {
                    key: record.payload[key]
                    for key in [
                        "provider",
                        "positions_complete",
                        "orders_complete",
                        "activity_complete",
                        "cash_account_verified",
                        "settled_cash_verified",
                        "lending_disabled_verified",
                        "borrowing_disabled_verified",
                    ]
                }
                report["position_count"] = len(record.payload["positions"])
                report["open_order_count"] = len(record.payload["orders"])
            if record.payload:
                report["raw_response_sha256"] = record.payload["raw_response_sha256"]
        report["read_only"] = True
        report["authorized_for_entry"] = False
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        with args.report_output.open("x") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
        print(
            "Read-only broker capture:",
            report["status"],
            "; no balances, identity or credentials printed",
        )
    except (SQLAlchemyError, ValueError, OSError, BrokerError):
        parser.exit(
            2,
            "Broker acquisition/store failure; preserve the private run for operator investigation\n",
        )
    finally:
        if engine is not None:
            engine.dispose()
    parser.exit(0 if report["status"] == "SUCCEEDED" else 1)


if __name__ == "__main__":
    main()
