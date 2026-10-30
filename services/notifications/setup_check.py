"""An explicit, one-destination setup message; never creates trading records."""

import argparse
import json
import time

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from apps.api.db import session_factory
from packages.config.settings import get_settings
from services.accounts.access import digest, locked
from services.notifications.delivery import KINDS, deliver_one
from services.notifications.models import Destination, Outbox, User
from services.notifications.telegram import Telegram
from services.notifications.worker import check_configuration

TEXTS = {
    "en": "HALAL QUANT: This is a one-time notification setup check. Not a trading signal or order.",
    "ar": "HALAL QUANT: هذه رسالة واحدة لفحص إعداد التنبيهات. ليست إشارة تداول أو أمرًا.",
}


def destination(db, chat_id):
    dest = db.scalar(select(Destination).where(Destination.chat_id == chat_id))
    if not dest:
        raise ValueError("Chat is not linked; verify the destination in the dashboard first")
    user = db.get(User, dest.user_id)
    if not user or not user.enabled:
        raise ValueError("Destination owner is disabled")
    identity = digest("notification-setup-v1:" + dest.id)
    return dest, identity


def preview(sessions, chat_id):
    with sessions() as db:
        dest, identity = destination(db, chat_id)
        record = db.get(Outbox, identity)
        return {
            "mode": "preview",
            "chat_id": chat_id,
            "enabled": dest.enabled,
            "text": TEXTS[dest.language],
            "status": record.status if record else "NOT_QUEUED",
            "messages_sent": 0,
        }


def send_once(sessions, telegram, chat_id):
    with locked(sessions, "delivery") as db:
        dest, identity = destination(db, chat_id)
        if not dest.enabled:
            raise ValueError("Enable this verified destination and save before sending")
        kind = next((kind for kind in KINDS if kind in dest.kinds), None)
        if kind is None:
            raise ValueError("Select at least one notification type and save")
        if db.get(Outbox, identity) is None:
            db.add(
                Outbox(
                    id=identity,
                    destination_id=dest.id,
                    event_key="notification-setup-v1",
                    kind=kind,
                    text=TEXTS[dest.language],
                    status="QUEUED",
                    attempts=0,
                    available=int(time.time()),
                    error=None,
                    message_id=None,
                )
            )
    # Only this ID can be claimed, regardless of other queued messages or destinations.
    deliver_one(sessions, telegram, only_id=identity)
    with sessions() as db:
        record = db.get(Outbox, identity)
        return {
            "chat_id": chat_id,
            "status": record.status,
            "error": record.error,
            "message_id": record.message_id,
            "attempts": record.attempts,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Preview or explicitly send one persistent setup check"
    )
    parser.add_argument("--chat-id", required=True, help="Already verified Telegram destination ID")
    parser.add_argument("--expected-bot", required=True)
    parser.add_argument(
        "--send",
        action="store_true",
        help="Consent to one real setup message; otherwise preview only",
    )
    args = parser.parse_args()
    settings = get_settings()
    engine, sessions = session_factory(settings.database_url)
    telegram = None
    try:
        if args.send:
            telegram = Telegram(settings.telegram_bot_token.get_secret_value())
            check_configuration(sessions, telegram, args.expected_bot)
            result = send_once(sessions, telegram, args.chat_id)
        else:
            result = preview(sessions, args.chat_id)
        print(json.dumps(result, ensure_ascii=False))
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    except SQLAlchemyError:
        parser.exit(1, "Setup check database operation failed; no automatic resend was requested\n")
    finally:
        if telegram is not None:
            telegram.close()
        engine.dispose()


if __name__ == "__main__":
    main()
