"""Read-only bounded observation of the deployed worker heartbeat."""

import argparse
import json
import time

from apps.api.db import session_factory
from packages.config.settings import get_settings
from services.notifications.health import view


def observe(sessions, seconds=0):
    deadline = time.monotonic() + seconds
    samples = 0
    while True:
        status = view(sessions)
        samples += 1
        if status["state"] != "RECENT" or status["mode"] != "delivery":
            return {"status": "NOT_CONFIRMED", "samples": samples, "worker": status}
        if time.monotonic() >= deadline:
            return {
                "status": "PASSED",
                "observed_seconds": seconds,
                "samples": samples,
                "worker": status,
                "scope": "Bounded observation only; does not certify future uptime or message arrival",
            }
        time.sleep(min(15, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description="Read-only worker status and bounded observation")
    parser.add_argument("--observe-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.observe_seconds < 0 or args.observe_seconds > 3600:
        parser.error("Observation must be between 0 and 3600 seconds")
    engine, sessions = session_factory(get_settings().database_url)
    try:
        print(json.dumps(observe(sessions, args.observe_seconds)))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
