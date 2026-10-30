"""Opt-in live account checks using disposable users, never the owner's password."""

import argparse
import json
import secrets
from contextlib import ExitStack
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from apps.api.db import AuditRecord, session_factory, utcnow
from packages.config.settings import get_settings
from services.accounts.access import digest, locked, password_hash
from services.notifications.models import AccessSession, Destination, OneTimeToken, Outbox, User


class AcceptanceFailure(RuntimeError):
    pass


def run_checks(sessions, origin, client_factory=None):
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use only the HTTPS application origin")
    origin = origin.rstrip("/")
    if client_factory is None and origin != "https://halal-quant.vercel.app":
        raise ValueError(
            "Live fixture credentials may only be sent to the configured Vercel origin"
        )
    client_factory = client_factory or (
        lambda: httpx.Client(base_url=origin, timeout=90, follow_redirects=False)
    )
    run_id = secrets.token_hex(12)
    emails = {
        name: f"m7-{run_id}-{name}@acceptance.invalid"
        for name in ("admin", "viewer", "expired", "forbidden")
    }
    admin_id = "m7-accept-" + secrets.token_hex(16)
    secret = secrets.token_urlsafe(32)
    results = {
        "run_id": run_id,
        "origin": origin,
        "checks": {},
        "temporary_accounts_removed": False,
        "real_emails_sent": 0,
        "real_telegram_messages_sent": 0,
    }
    created = False

    def mark(name, condition):
        results["checks"][name] = bool(condition)
        if not condition:
            raise AcceptanceFailure("Acceptance check failed: " + name)

    def request(client, method, path, status=200, csrf=None, body=None):
        headers = {"X-CSRF-Token": csrf} if csrf else {}
        response = client.request(method, path, headers=headers, json=body)
        mark(f"{method} {path.split('/')[-1]} expected {status}", response.status_code == status)
        return response

    def login(client, email, password):
        response = request(
            client, "POST", "/api/v1/auth/login", body={"email": email, "password": password}
        )
        cookie = response.headers.get("set-cookie", "").lower()
        mark(
            "secure_cookie_flags",
            all(flag in cookie for flag in ("httponly", "secure", "samesite=strict")),
        )
        return response.json()["csrf"]

    def token_expire(token, user_id):
        with locked(sessions) as db:
            user = db.get(User, user_id)
            if user is None or user.email not in emails.values():
                raise AcceptanceFailure("Refusing to modify a non-fixture account")
            stored = db.get(OneTimeToken, digest(token))
            if stored is None or stored.user_id != user_id:
                raise AcceptanceFailure("Fixture token binding failed")
            stored.expires = 0

    try:
        with locked(sessions) as db:
            if (
                db.scalar(
                    select(User.id)
                    .where(User.role == "admin", User.enabled.is_(True), User.password != "")
                    .limit(1)
                )
                is None
            ):
                raise AcceptanceFailure("An existing active owner administrator is required")
            db.add(
                User(
                    id=admin_id,
                    email=emails["admin"],
                    password=password_hash(secret),
                    role="admin",
                    enabled=True,
                )
            )
            created = True
        with ExitStack() as stack:
            fresh = lambda: stack.enter_context(client_factory())
            admin, viewer, anonymous = fresh(), fresh(), fresh()
            request(anonymous, "GET", "/health/ready")
            request(anonymous, "POST", "/api/v1/auth/register", 404, body={})
            acsrf = login(admin, emails["admin"], secret)
            invite = request(
                admin,
                "POST",
                "/api/v1/admin/invitations",
                csrf=acsrf,
                body={"email": emails["viewer"], "role": "viewer"},
            ).json()["token"]
            users = request(admin, "GET", "/api/v1/admin/users").json()["items"]
            viewer_id = next(u["id"] for u in users if u["email"] == emails["viewer"])
            password = secrets.token_urlsafe(32)
            redeem = {"token": invite, "password": password}
            request(anonymous, "POST", "/api/v1/auth/recover", body=redeem)
            request(anonymous, "POST", "/api/v1/auth/recover", 400, body=redeem)
            mark("invitation_single_use", True)
            vcsrf = login(viewer, emails["viewer"], password)
            request(viewer, "POST", "/api/v1/telegram/link-code", 403)
            mark("csrf_enforced", True)
            request(
                viewer,
                "POST",
                "/api/v1/admin/invitations",
                403,
                csrf=vcsrf,
                body={"email": emails["forbidden"], "role": "admin"},
            )
            second = fresh()
            login(second, emails["viewer"], password)
            session_id = next(
                s["id"]
                for s in request(second, "GET", "/api/v1/auth/sessions").json()["items"]
                if s["current"]
            )
            request(viewer, "DELETE", "/api/v1/auth/sessions/" + session_id, csrf=vcsrf)
            request(second, "GET", "/api/v1/auth/me", 401)
            mark("explicit_session_revocation", True)
            new_password = secrets.token_urlsafe(32)
            request(
                viewer,
                "POST",
                "/api/v1/auth/password",
                csrf=vcsrf,
                body={"current_password": password, "password": new_password},
            )
            request(viewer, "GET", "/api/v1/auth/me", 401)
            mark("password_change_revokes_sessions", True)
            vcsrf = login(viewer, emails["viewer"], new_password)
            recovery = request(
                admin, "POST", f"/api/v1/admin/users/{viewer_id}/recovery", csrf=acsrf
            ).json()["token"]
            token_expire(recovery, viewer_id)
            request(
                anonymous,
                "POST",
                "/api/v1/auth/recover",
                400,
                body={"token": recovery, "password": password},
            )
            mark("recovery_expiry", True)
            recovery = request(
                admin, "POST", f"/api/v1/admin/users/{viewer_id}/recovery", csrf=acsrf
            ).json()["token"]
            request(
                anonymous,
                "POST",
                "/api/v1/auth/recover",
                body={"token": recovery, "password": password},
            )
            request(
                anonymous,
                "POST",
                "/api/v1/auth/recover",
                400,
                body={"token": recovery, "password": password},
            )
            request(viewer, "GET", "/api/v1/auth/me", 401)
            mark("recovery_single_use_and_revocation", True)
            vcsrf = login(viewer, emails["viewer"], password)
            request(
                admin,
                "PATCH",
                f"/api/v1/admin/users/{viewer_id}",
                csrf=acsrf,
                body={"role": "viewer", "enabled": False},
            )
            request(viewer, "GET", "/api/v1/auth/me", 401)
            request(
                viewer,
                "POST",
                "/api/v1/auth/login",
                401,
                body={"email": emails["viewer"], "password": password},
            )
            mark("disabled_user_and_session_revocation", True)
            routes = {
                "analyst": "/api/v1/decisions/evaluate",
                "reviewer": "/api/v1/controls/reviews/methodologies",
                "operator": "/api/v1/controls/kill-switch/engage",
                "broker_reader": "/api/v1/controls/broker/refresh",
            }
            for role in ("viewer", "analyst", "reviewer", "operator", "broker_reader", "admin"):
                request(
                    admin,
                    "PATCH",
                    f"/api/v1/admin/users/{viewer_id}",
                    csrf=acsrf,
                    body={"role": role, "enabled": True},
                )
                actor = fresh()
                csrf = login(actor, emails["viewer"], password)
                for allowed, path in routes.items():
                    # Invalid bodies cannot create control/broker/decision records.
                    request(
                        actor, "POST", path, 422 if role == allowed else 403, csrf=csrf, body={}
                    )
                request(actor, "GET", "/api/v1/admin/users", 200 if role == "admin" else 403)
                request(actor, "POST", "/api/v1/auth/logout", csrf=csrf)
                request(actor, "GET", "/api/v1/auth/me", 401)
                mark("role_" + role, True)
            invite = request(
                admin,
                "POST",
                "/api/v1/admin/invitations",
                csrf=acsrf,
                body={"email": emails["expired"], "role": "viewer"},
            ).json()["token"]
            users = request(admin, "GET", "/api/v1/admin/users").json()["items"]
            expired_id = next(u["id"] for u in users if u["email"] == emails["expired"])
            token_expire(invite, expired_id)
            request(
                anonymous,
                "POST",
                "/api/v1/auth/recover",
                400,
                body={"token": invite, "password": password},
            )
            mark("invitation_expiry", True)
    finally:
        if created:
            with locked(sessions) as db:
                fixtures = db.scalars(
                    select(User).where(User.email.in_(list(emails.values())))
                ).all()
                ids = [u.id for u in fixtures]
                real_admin = db.scalar(
                    select(User.id)
                    .where(
                        User.role == "admin",
                        User.enabled.is_(True),
                        User.password != "",
                        User.id.not_in(ids),
                    )
                    .limit(1)
                )
                if real_admin is None:
                    raise AcceptanceFailure(
                        "Owner administrator changed during checks; fixture cleanup requires operator review"
                    )
                dests = list(db.scalars(select(Destination.id).where(Destination.user_id.in_(ids))))
                db.execute(delete(Outbox).where(Outbox.destination_id.in_(dests)))
                db.execute(delete(Destination).where(Destination.user_id.in_(ids)))
                db.execute(delete(AccessSession).where(AccessSession.user_id.in_(ids)))
                db.execute(delete(OneTimeToken).where(OneTimeToken.user_id.in_(ids)))
                db.execute(delete(User).where(User.id.in_(ids)))
                db.add(
                    AuditRecord(
                        action="acceptance.accounts_cleanup", subject=run_id, created_at=utcnow()
                    )
                )
            results["temporary_accounts_removed"] = True
    results["status"] = "PASSED"
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Live deployed-account acceptance; creates and cleans disposable accounts only"
    )
    parser.add_argument("--origin", default="https://halal-quant.vercel.app")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Explicitly allow temporary account fixtures and HTTP checks",
    )
    args = parser.parse_args()
    if not args.run:
        parser.error(
            "Use --run to create temporary fixture accounts; real owner credentials are never requested"
        )
    engine, sessions = session_factory(get_settings().database_url)
    try:
        print(json.dumps(run_checks(sessions, args.origin)))
    except AcceptanceFailure as error:
        parser.exit(1, str(error) + "\n")
    except (httpx.HTTPError, SQLAlchemyError, ValueError, KeyError, StopIteration):
        parser.exit(
            1,
            "Live account acceptance did not complete. No credentials are printed; review connectivity and fixture cleanup before rerunning.\n",
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
