"""Run separately from the web app; never started implicitly during tests."""

import argparse
import time

from apps.api.db import session_factory
from packages.config.settings import get_settings
from services.notifications.delivery import deliver_one
from services.notifications.linking import poll_links
from services.notifications.telegram import Telegram


def main():
    parser = argparse.ArgumentParser(description="Telegram outbox and linking worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    engine, sessions = session_factory(settings.database_url)
    telegram = Telegram(settings.telegram_bot_token.get_secret_value())
    try:
        while True:
            try:
                poll_links(sessions, telegram)
            except ValueError:
                print("Telegram linking unavailable; check server configuration.")
            deliver_one(sessions, telegram)
            if args.once:
                break
            time.sleep(1)
    finally:
        telegram.close()
        engine.dispose()


if __name__ == "__main__":
    main()
