"""Transactional outbox. An uncertain attempt is terminal until investigated."""

import time

import httpx
from sqlalchemy import select, update

from services.accounts.access import digest, locked
from services.notifications.models import Destination, Outbox, ServiceState, User
from services.notifications.preview import signal_preview

KINDS = ("signal", "decision", "risk_stop")


def enqueue(db, kind, event_key, payload):
    for destination in db.scalars(select(Destination).where(Destination.enabled.is_(True))):
        user = db.get(User, destination.user_id)
        if kind not in destination.kinds or not user or not user.enabled:
            continue
        identity = digest(destination.id + ":" + kind + ":" + event_key)
        if db.get(Outbox, identity):
            continue
        ar = destination.language == "ar"
        if kind == "signal":
            text = signal_preview(payload, destination.language)["text"]
        else:
            title = {
                "decision": ("Research decision", "قرار بحثي"),
                "risk_stop": ("Risk stop alert", "تنبيه إيقاف المخاطر"),
            }[kind][ar]
            # Only curated, non-secret identifiers/status; never arbitrary control payloads.
            status = str(payload.get("status", "ENGAGED"))
            text = f"HALAL QUANT · {title}\n{event_key}\n{status}\n" + (
                "ليست إذن تداول." if ar else "Not trading authorization."
            )
        db.add(
            Outbox(
                id=identity,
                destination_id=destination.id,
                event_key=event_key,
                kind=kind,
                text=text[:4096],
                status="QUEUED",
                attempts=0,
                available=int(time.time()),
                error=None,
                message_id=None,
            )
        )


def deliver_one(sessions, telegram, now=None, *, only_id=None):
    now = int(time.time()) if now is None else now
    with locked(sessions, "delivery") as db:
        # Stale claims may already have reached Telegram. Never retry them.
        stale = update(Outbox).where(Outbox.status == "SENDING", Outbox.available <= now - 120)
        if only_id is not None:
            stale = stale.where(Outbox.id == only_id)
        db.execute(stale.values(status="UNCERTAIN", error="WORKER_INTERRUPTED"))
        gate = db.get(ServiceState, "delivery")
        if gate.value > now:
            return False
        query = select(Outbox).where(
            Outbox.status.in_(["QUEUED", "RETRY"]), Outbox.available <= now
        )
        if only_id is not None:
            query = query.where(Outbox.id == only_id)
        record = db.scalar(query.order_by(Outbox.available, Outbox.id).limit(1))
        if record is None:
            return False
        dest = db.get(Destination, record.destination_id)
        user = db.get(User, dest.user_id) if dest else None
        if (
            not dest
            or not dest.enabled
            or not user
            or not user.enabled
            or record.kind not in dest.kinds
        ):
            record.status, record.error = "CANCELLED", "NOTIFICATIONS_DISABLED"
            return True
        # Pace each chat too, including groups (conservative 3 seconds per chat).
        chat_gate_id = "chat:" + digest(dest.chat_id)[:59]
        chat_gate = db.get(ServiceState, chat_gate_id)
        if chat_gate and chat_gate.value > now:
            record.available = chat_gate.value
            return True
        if chat_gate is None:
            chat_gate = ServiceState(id=chat_gate_id, value=0)
            db.add(chat_gate)
        chat_gate.value = now + 3
        record.status, record.available = "SENDING", now
        record.attempts += 1
        gate.value = now + 1
        identity, chat_id, text = record.id, dest.chat_id, record.text
    # The claim is committed BEFORE crossing the network boundary.
    status, error, retry, message_id = "UNCERTAIN", "UNCONFIRMED_RESPONSE", None, None
    try:
        response = telegram.call("sendMessage", {"chat_id": chat_id, "text": text})
        try:
            data = response.json()
            if not isinstance(data, dict):
                data = {}
        except ValueError:
            data = {}
        if (
            response.status_code == 200
            and data.get("ok") is True
            and isinstance(data.get("result"), dict)
            and type(data["result"].get("message_id")) is int
        ):
            status, error, message_id = "SENT", None, str(data["result"]["message_id"])
        elif data.get("ok") is False and data.get("error_code") == 429:
            parameters = data.get("parameters")
            delay = parameters.get("retry_after") if isinstance(parameters, dict) else None
            if isinstance(delay, int) and 0 < delay <= 86400:
                status, error, retry = "RETRY", "TELEGRAM_RATE_LIMIT", now + delay + 1
        elif data.get("ok") is False and data.get("error_code") in (400, 401, 403, 404):
            status, error = "FAILED", "TELEGRAM_REJECTED_" + str(data["error_code"])
        # 5xx, malformed replies and timeouts can occur after accepting the message.
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
        status, error, retry = "RETRY", "CONNECT_FAILED", now + 30
    except httpx.HTTPError:
        status, error = "UNCERTAIN", "TRANSPORT_UNCERTAIN"
    with locked(sessions, "delivery") as db:
        record = db.get(Outbox, identity)
        if record.status != "SENDING":
            return True
        # The provider-wide pause still applies when this message exhausts its budget.
        if retry and error == "TELEGRAM_RATE_LIMIT":
            db.get(ServiceState, "delivery").value = retry
        if status == "RETRY" and record.attempts >= 5:
            status, error, retry = "FAILED", "SAFE_RETRIES_EXHAUSTED", None
        record.status, record.error, record.message_id = status, error, message_id
        if retry:
            record.available = retry
    return True
