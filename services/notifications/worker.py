"""Run separately from the web app; never started implicitly during tests."""

import argparse
import json
import time

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from apps.api.db import session_factory
from packages.config.settings import get_settings
from services.notifications.delivery import deliver_one
from services.notifications.linking import poll_links
from services.notifications.models import Outbox, ServiceState
from services.notifications.telegram import Telegram


def check_configuration(sessions, telegram, expected_bot=None):
    """Read-only checks: never consume updates, claim outbox rows or send a message."""
    try:
        with sessions() as db:
            revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
            states = set(
                db.scalars(
                    select(ServiceState.id).where(
                        ServiceState.id.in_(["access", "delivery", "telegram_offset"])
                    )
                )
            )
            if revision != "0007_access_delivery" or states != {
                "access",
                "delivery",
                "telegram_offset",
            }:
                raise ValueError("Database migration or worker state is missing")
            pending = db.scalar(
                select(func.count())
                .select_from(Outbox)
                .where(Outbox.status.in_(["QUEUED", "RETRY"]))
            )
    except SQLAlchemyError:
        raise ValueError("Database check failed; verify DATABASE_URL and migrations") from None
    bot = telegram.verified("getMe", {})
    if not isinstance(bot, dict) or bot.get("is_bot") is not True or not bot.get("username"):
        raise ValueError("Telegram did not confirm a bot identity")
    if expected_bot and bot["username"].lower() != expected_bot.lstrip("@").lower():
        raise ValueError("Configured token belongs to a different bot")
    webhook = telegram.verified("getWebhookInfo", {})
    valid_webhook = isinstance(webhook, dict) and isinstance(webhook.get("url"), str)
    if not valid_webhook:
        raise ValueError("Telegram webhook check was not confirmed")
    if webhook["url"]:
        raise ValueError("A webhook is configured; resolve it before starting polling")
    return {
        "database": "ready",
        "bot": "@" + bot["username"],
        "pending_messages": pending,
        "webhook": False,
        "messages_sent": 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Telegram outbox and linking worker")
    parser.add_argument("--once", action="store_true")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check",
        action="store_true",
        help="Read-only database/bot/webhook checks; no polling or delivery",
    )
    modes.add_argument(
        "--link-only",
        action="store_true",
        help="Verify linking codes without delivering any outbox messages",
    )
    parser.add_argument("--expected-bot", help="Require this bot username (with or without @)")
    args = parser.parse_args()
    settings = get_settings()
    engine, sessions = session_factory(settings.database_url)
    telegram = None
    try:
        telegram = Telegram(settings.telegram_bot_token.get_secret_value())
        if args.check or args.expected_bot:
            result = check_configuration(sessions, telegram, args.expected_bot)
            print(json.dumps(result))
        if args.check:
            return
        while True:
            try:
                poll_links(sessions, telegram)
            except ValueError:
                print("Telegram linking unavailable; check server configuration.")
            if not args.link_only:
                deliver_one(sessions, telegram)
            if args.once:
                break
            time.sleep(1)
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    finally:
        if telegram is not None:
            telegram.close()
        engine.dispose()


if __name__ == "__main__":
    main()
