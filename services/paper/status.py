"""Read-only forward evidence export; no leases, provider calls, orders or messages."""

import argparse
import json

from sqlalchemy.exc import SQLAlchemyError

from apps.api.db import session_factory
from packages.config.settings import get_settings
from services.controls.store import lock_controls
from services.paper.forward import report
from services.paper.models import PaperRun


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        engine, sessions = session_factory(get_settings().database_url)
    except (ValueError, SQLAlchemyError, OSError):
        parser.exit(1, "Paper status configuration is invalid; check private settings.\n")
    try:
        with sessions.begin() as db:
            lock_controls(db)
            run = db.get(PaperRun, args.run_id)
            if not run:
                raise ValueError("Unknown paper run")
            print(json.dumps(report(db, run)))
    except (ValueError, SQLAlchemyError):
        parser.exit(
            1, "Forward evidence unavailable; check the run ID and database migration privately.\n"
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
