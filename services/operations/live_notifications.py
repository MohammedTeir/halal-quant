"""Explicit finite transport checks; no trading/control records or arbitrary recipients."""

import argparse
import json
import time

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from apps.api.db import session_factory
from packages.config.settings import get_settings
from services.accounts.access import digest, locked
from services.notifications.delivery import deliver_one
from services.notifications.models import Destination, Outbox, User
from services.notifications.setup_check import send_once
from services.notifications.telegram import Telegram
from services.notifications.worker import check_configuration

CASES = (
    (
        "signal-en",
        "signal",
        "HALAL QUANT [ACCEPTANCE TEST]: Trading-signal notification delivery. No trading signal or order was created.",
    ),
    (
        "decision-en",
        "decision",
        "HALAL QUANT [ACCEPTANCE TEST]: Research-decision notification delivery. No decision or order was created.",
    ),
    (
        "risk-stop-en",
        "risk_stop",
        "HALAL QUANT [ACCEPTANCE TEST]: Risk-stop notification delivery. No risk state was changed.",
    ),
    (
        "signal-ar",
        "signal",
        "HALAL QUANT [اختبار قبول]: تم فحص تسليم التنبيه بالعربية. لم تُنشأ إشارة تداول أو أوامر أو تغييرات مخاطر.",
    ),
)


def run_suite(sessions, telegram, chat_id, *, send=False, wait_seconds=90):
    with sessions() as db:
        dest = db.scalar(select(Destination).where(Destination.chat_id == chat_id))
        owner = db.get(User, dest.user_id) if dest else None
        if not dest or not owner or not owner.enabled:
            raise ValueError("Select a verified destination with an enabled owner")
        destination_id = dest.id
        if send and (
            not dest.enabled or not {"signal", "decision", "risk_stop"}.issubset(dest.kinds)
        ):
            raise ValueError("Enable this destination and all three notification types, then save")
    results = []
    if not send:
        return {
            "mode": "preview",
            "messages_sent": 0,
            "messages": [
                {"case": case, "kind": kind, "text": message} for case, kind, message in CASES
            ],
        }
    for case, kind, message in CASES:
        identity = digest("live-acceptance-v1:" + destination_id + ":" + case)
        with locked(sessions, "delivery") as db:
            current = db.get(Destination, destination_id)
            if not current or not current.enabled or kind not in current.kinds:
                raise ValueError("Destination preferences changed; acceptance stopped")
            if db.get(Outbox, identity) is None:
                db.add(
                    Outbox(
                        id=identity,
                        destination_id=destination_id,
                        event_key="acceptance-v1:" + case,
                        kind=kind,
                        text=message,
                        status="QUEUED",
                        attempts=0,
                        available=int(time.time()),
                        error=None,
                        message_id=None,
                    )
                )
        deadline = time.monotonic() + wait_seconds
        while True:
            deliver_one(sessions, telegram, only_id=identity)
            with sessions() as db:
                record = db.get(Outbox, identity)
                result = {
                    "case": case,
                    "status": record.status,
                    "message_id": record.message_id,
                    "error": record.error,
                    "attempts": record.attempts,
                }
            if (
                result["status"] not in ("QUEUED", "RETRY", "SENDING")
                or time.monotonic() >= deadline
            ):
                break
            time.sleep(1)
        results.append(result)
        if result["status"] != "SENT":
            return {
                "status": "INCOMPLETE",
                "results": results,
                "note": "Do not reset uncertain/failed records; same command never creates a second case record",
            }
    return {"status": "PASSED", "results": results, "source_trading_or_risk_records_created": 0}


def main():
    parser = argparse.ArgumentParser(
        description="Preview or send four approved, labelled tests to one verified chat"
    )
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--expected-bot", default="halalquant_bot")
    parser.add_argument(
        "--group-chat-id",
        help="Optional separately confirmed and enabled group: one setup message only",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Explicit consent to four messages to --chat-id and one to the optional group",
    )
    args = parser.parse_args()
    if args.group_chat_id and (
        not args.group_chat_id.startswith("-") or args.group_chat_id == args.chat_id
    ):
        parser.error("Group must be a separate verified negative chat ID")
    engine, sessions = session_factory(get_settings().database_url)
    telegram = None
    try:
        if args.send:
            telegram = Telegram(get_settings().telegram_bot_token.get_secret_value())
            check_configuration(sessions, telegram, args.expected_bot)
        result = run_suite(sessions, telegram, args.chat_id, send=args.send)
        if args.group_chat_id and args.send and result.get("status") == "PASSED":
            result["group_setup"] = send_once(sessions, telegram, args.group_chat_id)
            if result["group_setup"]["status"] != "SENT":
                result["status"] = "INCOMPLETE"
        print(json.dumps(result, ensure_ascii=False))
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    except SQLAlchemyError:
        parser.exit(
            1,
            "Notification acceptance database operation did not complete; do not reset uncertain records\n",
        )
    finally:
        if telegram:
            telegram.close()
        engine.dispose()


if __name__ == "__main__":
    main()
