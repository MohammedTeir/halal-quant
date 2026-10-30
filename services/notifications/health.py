"""Persistent polling heartbeat; activity is not a guarantee of message arrival."""

import time

from sqlalchemy import select

from services.accounts.access import locked
from services.notifications.models import ServiceState

KEYS = ("worker_last_seen", "worker_started_at", "worker_starts", "worker_mode")


def heartbeat(sessions, *, mode, started=False, now=None):
    now = int(time.time()) if now is None else now
    with locked(sessions, "delivery") as db:
        records = {k: db.get(ServiceState, k) for k in KEYS}
        for k, record in records.items():
            if record is None:
                records[k] = ServiceState(id=k, value=0)
                db.add(records[k])
        records["worker_last_seen"].value = now
        records["worker_mode"].value = 1 if mode == "link-only" else 0
        if started:
            records["worker_started_at"].value = now
            records["worker_starts"].value += 1


def view(sessions, now=None):
    now = int(time.time()) if now is None else now
    with sessions() as db:
        values = {
            s.id: s.value for s in db.scalars(select(ServiceState).where(ServiceState.id.in_(KEYS)))
        }
    last = values.get("worker_last_seen")
    age = now - last if last is not None else None
    state = (
        "UNKNOWN"
        if age is None
        else "CLOCK_ERROR"
        if age < -5
        else "RECENT"
        if age <= 90
        else "STALE"
    )
    return {
        "state": state,
        "mode": ("link-only" if values.get("worker_mode") == 1 else "delivery") if last else None,
        "last_seen": last,
        "age_seconds": age,
        "started_at": values.get("worker_started_at"),
        "successful_starts": values.get("worker_starts", 0),
        "restart_observed": values.get("worker_starts", 0) > 1,
        "scope": "Successful poll/worker loop activity only; not a delivery or uptime guarantee",
    }
