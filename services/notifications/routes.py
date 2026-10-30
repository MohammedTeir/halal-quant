import time
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from services.accounts.access import issue, locked
from services.notifications.models import Destination, Outbox, User


class Preferences(BaseModel):
    enabled: bool
    language: Literal["en", "ar"] = "en"
    kinds: list[Literal["signal", "decision", "risk_stop"]] = Field(max_length=3)


def mount_notifications(app, sessions, current):
    current_dependency = Depends(current)

    @app.post("/api/v1/telegram/link-code")
    def link_code(user=current_dependency):
        with locked(sessions) as db:
            return {"code": issue(db, db.get(User, user.id), "telegram", 600), "expires_in": 600}

    @app.get("/api/v1/telegram/destinations")
    def destinations(user=current_dependency):
        with sessions() as db:
            return {
                "items": [
                    {
                        "id": d.id,
                        "chat_id": d.chat_id,
                        "enabled": d.enabled,
                        "language": d.language,
                        "kinds": d.kinds,
                    }
                    for d in db.scalars(select(Destination).where(Destination.user_id == user.id))
                ]
            }

    @app.patch("/api/v1/telegram/destinations/{destination_id}")
    def preferences(destination_id: str, body: Preferences, user=current_dependency):
        with locked(sessions, "delivery") as db:
            d = db.get(Destination, destination_id)
            if not d or d.user_id != user.id:
                raise HTTPException(404, "Unknown destination")
            d.enabled, d.language, d.kinds = body.enabled, body.language, sorted(set(body.kinds))
            # Cancel queued work now so re-enabling cannot release an old backlog.
            query = update(Outbox).where(
                Outbox.destination_id == d.id, Outbox.status.in_(["QUEUED", "RETRY"])
            )
            if body.enabled:
                query = query.where(Outbox.kind.not_in(body.kinds))
            db.execute(query.values(status="CANCELLED", error="NOTIFICATIONS_DISABLED"))
        return {"ok": True}

    @app.delete("/api/v1/telegram/destinations/{destination_id}")
    def unlink(destination_id: str, user=current_dependency):
        with locked(sessions, "delivery") as db:
            d = db.get(Destination, destination_id)
            if not d or d.user_id != user.id:
                raise HTTPException(404, "Unknown destination")
            db.execute(
                update(Outbox)
                .where(Outbox.destination_id == d.id, Outbox.status.in_(["QUEUED", "RETRY"]))
                .values(status="CANCELLED", error="UNLINKED")
            )
            db.delete(d)
        return {"ok": True}

    @app.get("/api/v1/telegram/deliveries")
    def deliveries(user=current_dependency):
        with sessions() as db:
            records = db.scalars(
                select(Outbox)
                .join(Destination, Outbox.destination_id == Destination.id)
                .where(Destination.user_id == user.id)
                .order_by(Outbox.available.desc())
                .limit(100)
            )
            return {
                "items": [
                    {
                        "id": r.id,
                        "kind": r.kind,
                        "event_key": r.event_key,
                        "status": r.status,
                        "error": r.error,
                        "attempts": r.attempts,
                        "message_id": r.message_id,
                        "next_attempt": r.available,
                    }
                    for r in records
                ],
                "as_of": int(time.time()),
            }
