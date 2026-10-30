"""Consume codes only from Telegram-originated updates fetched by the worker."""

import secrets
import time

from sqlalchemy import select

from services.accounts.access import digest, locked
from services.notifications.models import Destination, OneTimeToken, ServiceState, User


def process_update(sessions, telegram, update):
    message = update.get("message", {})
    words = message.get("text", "").split()
    if len(words) != 2 or words[0].split("@")[0] not in ("/link", "/start"):
        return False
    code = words[1]
    chat, sender = message.get("chat", {}), message.get("from", {})
    chat_id, sender_id = chat.get("id"), sender.get("id")
    if not isinstance(chat_id, int) or not isinstance(sender_id, int) or sender.get("is_bot"):
        return False
    # Check validity before making verification requests, then recheck atomically.
    with sessions() as db:
        token = db.get(OneTimeToken, digest(code))
        if not token or token.kind != "telegram" or token.expires <= time.time():
            return False
    if chat.get("type") == "private":
        if chat_id != sender_id:
            return False
    elif chat.get("type") in ("group", "supergroup"):
        try:
            actor = telegram.verified("getChatMember", {"chat_id": chat_id, "user_id": sender_id})
            bot = telegram.verified("getMe", {})
            membership = telegram.verified(
                "getChatMember", {"chat_id": chat_id, "user_id": bot["id"]}
            )
            if actor.get("status") not in ("creator", "administrator") or membership.get(
                "status"
            ) not in ("creator", "administrator"):
                return False
        except (ValueError, KeyError, TypeError):
            return False
    else:
        return False
    with locked(sessions) as db:
        token = db.get(OneTimeToken, digest(code))
        if not token or token.kind != "telegram" or token.expires <= time.time():
            return False
        user = db.get(User, token.user_id)
        if not user or not user.enabled:
            return False
        dest = db.scalar(select(Destination).where(Destination.chat_id == str(chat_id)))
        if dest:
            # An existing destination cannot be reassigned by another account's code.
            return False
        db.add(
            Destination(
                id=secrets.token_hex(16),
                user_id=user.id,
                chat_id=str(chat_id),
                enabled=False,
                language="en",
                kinds=["signal", "decision", "risk_stop"],
            )
        )
        db.delete(token)
    return True


def poll_links(sessions, telegram):
    with sessions() as db:
        offset = db.get(ServiceState, "telegram_offset").value
    updates = telegram.verified(
        "getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": ["message"], "limit": 100}
    )
    for update in updates:
        process_update(sessions, telegram, update)
        # A crash before checkpoint is harmless: codes are atomically single-use.
        with locked(sessions) as db:
            state = db.get(ServiceState, "telegram_offset")
            state.value = max(state.value, update["update_id"] + 1)
