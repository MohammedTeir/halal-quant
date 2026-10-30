"""Invitation-only accounts and revocable server-side sessions."""

import hashlib
import hmac
import secrets
import time
from contextlib import contextmanager
from typing import Literal

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update

from apps.api.db import AuditRecord, utcnow
from services.notifications.models import AccessSession, OneTimeToken, ServiceState, User

ROLES = Literal["admin", "viewer", "reviewer", "operator", "broker_reader", "analyst"]
COOKIE = "hq_session"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(value):
    salt = secrets.token_hex(16)
    return salt + ":" + hashlib.scrypt(value.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()


def password_matches(value, stored):
    salt, expected = stored.split(":")
    actual = hashlib.scrypt(value.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)


@contextmanager
def locked(sessions, name="access"):
    # A real write serializes SQLite too; SELECT FOR UPDATE alone does not.
    with sessions.begin() as db:
        result = db.execute(
            update(ServiceState).where(ServiceState.id == name).values(value=ServiceState.value)
        )
        if result.rowcount != 1:
            raise HTTPException(503, "Access/delivery lock migration required")
        yield db


def revoke(db, user_id):
    db.execute(delete(AccessSession).where(AccessSession.user_id == user_id))


def issue(db, user, kind, ttl):
    db.execute(
        delete(OneTimeToken).where(OneTimeToken.user_id == user.id, OneTimeToken.kind == kind)
    )
    raw = secrets.token_urlsafe(32)
    db.add(OneTimeToken(id=digest(raw), user_id=user.id, kind=kind, expires=int(time.time()) + ttl))
    return raw


def user_view(user):
    return {"id": user.id, "email": user.email, "role": user.role, "enabled": user.enabled}


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class Invite(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    role: ROLES = "viewer"


class ChangeUser(BaseModel):
    role: ROLES
    enabled: bool


class Redeem(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    password: str = Field(min_length=12, max_length=256)


class ChangePassword(BaseModel):
    current_password: str = Field(max_length=256)
    password: str = Field(min_length=12, max_length=256)


def mount_accounts(app, sessions, settings):
    dummy_password = password_hash(secrets.token_urlsafe(32))

    def current(request: Request):
        raw = request.cookies.get(COOKIE, "")
        with sessions() as db:
            record = db.get(AccessSession, digest(raw)) if raw else None
            user = db.get(User, record.user_id) if record else None
            if not record or record.expires <= time.time() or not user or not user.enabled:
                raise HTTPException(401, "Sign in required")
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                csrf = request.headers.get("x-csrf-token", "")
                if not hmac.compare_digest(csrf, record.csrf):
                    raise HTTPException(403, "CSRF token required")
            request.state.access_session = record.id
            return user

    current_dependency = Depends(current)

    def role(*allowed):
        def dependency(user=current_dependency):
            if user.role not in allowed:
                raise HTTPException(403, "Role permission required")
            return user

        return dependency

    admin_dependency = Depends(role("admin"))

    @app.post("/api/v1/auth/login")
    def login(body: Login, request: Request, response: Response):
        # Persistent per-client and per-account budgets survive app/worker restarts.
        blocked = False
        with locked(sessions) as db:
            bucket = int(time.time()) // 900
            prefix = f"login:{bucket}:"
            db.execute(
                delete(ServiceState).where(
                    ServiceState.id.like("login:%"), ~ServiceState.id.like(prefix + "%")
                )
            )
            for key in (request.client.host if request.client else "unknown", body.email.lower()):
                identity = prefix + digest(key)[:40]
                counter = db.get(ServiceState, identity)
                if counter is None:
                    counter = ServiceState(id=identity, value=0)
                    db.add(counter)
                counter.value += 1
                blocked |= counter.value > 20
                if blocked:
                    break
        if blocked:
            raise HTTPException(429, "Try again later", headers={"Retry-After": "900"})
        with locked(sessions) as db:
            user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
            stored = user.password if user and user.password else dummy_password
            valid = password_matches(body.password, stored)
            if not user or not user.enabled or not valid or not user.password:
                raise HTTPException(401, "Invalid credentials")
            raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            db.add(
                AccessSession(
                    id=digest(raw),
                    user_id=user.id,
                    csrf=csrf,
                    expires=int(time.time()) + settings.session_hours * 3600,
                )
            )
            response.set_cookie(
                COOKIE,
                raw,
                httponly=True,
                secure=settings.session_cookie_secure,
                samesite="strict",
                max_age=settings.session_hours * 3600,
                path="/",
            )
            return {"user": user_view(user), "csrf": csrf}

    @app.get("/api/v1/auth/me")
    def me(request: Request, user=current_dependency):
        with sessions() as db:
            return {
                "user": user_view(user),
                "csrf": db.get(AccessSession, request.state.access_session).csrf,
            }

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, response: Response, user=current_dependency):
        with locked(sessions) as db:
            db.execute(
                delete(AccessSession).where(AccessSession.id == request.state.access_session)
            )
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/v1/auth/sessions")
    def list_sessions(request: Request, user=current_dependency):
        with sessions() as db:
            return {
                "items": [
                    {
                        "id": s.id,
                        "expires": s.expires,
                        "current": s.id == request.state.access_session,
                    }
                    for s in db.scalars(
                        select(AccessSession).where(
                            AccessSession.user_id == user.id, AccessSession.expires > time.time()
                        )
                    )
                ]
            }

    @app.delete("/api/v1/auth/sessions/{session_id}")
    def delete_session(session_id: str, user=current_dependency):
        with locked(sessions) as db:
            s = db.get(AccessSession, session_id)
            if s and (s.user_id == user.id or user.role == "admin"):
                db.delete(s)
            elif s:
                raise HTTPException(403, "Own sessions only")
        return {"ok": True}

    @app.post("/api/v1/auth/password")
    def change_password(body: ChangePassword, user=current_dependency):
        with locked(sessions) as db:
            target = db.get(User, user.id)
            if not password_matches(body.current_password, target.password):
                raise HTTPException(401, "Invalid credentials")
            target.password = password_hash(body.password)
            revoke(db, user.id)
            db.execute(delete(OneTimeToken).where(OneTimeToken.user_id == user.id))
        return {"ok": True}

    @app.get("/api/v1/admin/users")
    def users(user=admin_dependency):
        with sessions() as db:
            return {"items": [user_view(u) for u in db.scalars(select(User).order_by(User.email))]}

    @app.post("/api/v1/admin/invitations")
    def invite(body: Invite, user=admin_dependency):
        with locked(sessions) as db:
            email = body.email.strip().lower()
            target = db.scalar(select(User).where(User.email == email))
            if target:
                raise HTTPException(409, "Account already exists")
            target = User(
                id=secrets.token_hex(16), email=email, password="", role=body.role, enabled=True
            )
            db.add(target)
            return {"token": issue(db, target, "invite", 86400), "expires_in": 86400}

    @app.patch("/api/v1/admin/users/{user_id}")
    def edit_user(user_id: str, body: ChangeUser, user=admin_dependency):
        with locked(sessions) as db:
            target = db.get(User, user_id)
            if not target:
                raise HTTPException(404, "Unknown user")
            if (
                target.password
                and target.role == "admin"
                and target.enabled
                and (body.role != "admin" or not body.enabled)
            ):
                admins = db.scalars(
                    select(User).where(
                        User.role == "admin", User.enabled.is_(True), User.password != ""
                    )
                ).all()
                if len(admins) == 1:
                    raise HTTPException(409, "Keep at least one enabled administrator")
            if not body.enabled:
                from services.notifications.models import Destination, Outbox

                destinations = select(Destination.id).where(Destination.user_id == user_id)
                db.execute(
                    update(Outbox)
                    .where(
                        Outbox.destination_id.in_(destinations),
                        Outbox.status.in_(["QUEUED", "RETRY"]),
                    )
                    .values(status="CANCELLED", error="ACCOUNT_DISABLED")
                )
            target.role, target.enabled = body.role, body.enabled
            revoke(db, user_id)
            db.execute(delete(OneTimeToken).where(OneTimeToken.user_id == user_id))
            return user_view(target)

    @app.delete("/api/v1/admin/users/{user_id}/sessions")
    def revoke_all(user_id: str, user=admin_dependency):
        with locked(sessions) as db:
            revoke(db, user_id)
        return {"ok": True}

    @app.post("/api/v1/admin/users/{user_id}/recovery")
    def recovery(user_id: str, user=admin_dependency):
        with locked(sessions) as db:
            target = db.get(User, user_id)
            if not target or not target.enabled:
                raise HTTPException(404, "Unknown enabled user")
            return {"token": issue(db, target, "recovery", 1800), "expires_in": 1800}

    @app.post("/api/v1/auth/recover")
    def redeem(body: Redeem):
        with locked(sessions) as db:
            token = db.get(OneTimeToken, digest(body.token))
            if (
                not token
                or token.kind not in ("invite", "recovery")
                or token.expires <= time.time()
            ):
                raise HTTPException(400, "Invalid or expired link")
            user = db.get(User, token.user_id)
            if not user or not user.enabled:
                raise HTTPException(400, "Invalid or expired link")
            user.password = password_hash(body.password)
            revoke(db, user.id)
            db.execute(delete(OneTimeToken).where(OneTimeToken.user_id == user.id))
            db.add(AuditRecord(action="account.password_set", subject=user.id, created_at=utcnow()))
        return {"ok": True}

    return current, role
