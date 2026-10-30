"""Local-server bootstrap/recovery, never a public registration endpoint."""

import argparse
import secrets

from sqlalchemy import select

from apps.api.db import session_factory
from packages.config.settings import get_settings
from services.accounts.access import issue, locked
from services.notifications.models import User


def main():
    parser = argparse.ArgumentParser(
        description="Issue a private administrator setup/recovery link"
    )
    parser.add_argument("email")
    parser.add_argument("--recover", action="store_true", help="Recover an existing enabled admin")
    args = parser.parse_args()
    settings = get_settings()
    engine, sessions = session_factory(settings.database_url)
    try:
        with locked(sessions) as db:
            if args.recover:
                user = db.scalar(
                    select(User).where(
                        User.email == args.email.lower(),
                        User.role == "admin",
                        User.enabled.is_(True),
                    )
                )
                if not user:
                    parser.error("No enabled administrator with that email")
            else:
                if db.scalar(select(User.id).limit(1)):
                    parser.error(
                        "Bootstrap only works on an empty user table; use admin invitations"
                    )
                if "@" not in args.email or len(args.email) > 254:
                    parser.error("Valid email required")
                user = User(
                    id=secrets.token_hex(16),
                    email=args.email.lower(),
                    password="",
                    role="admin",
                    enabled=True,
                )
                db.add(user)
            token = issue(db, user, "recovery" if args.recover else "invite", 1800)
        print(settings.public_base_url.rstrip("/") + "/dashboard#recover=" + token)
        print("Expires in 30 minutes. Share privately; this is a one-time credential.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
