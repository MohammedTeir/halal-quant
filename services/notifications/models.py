"""Persistent access and delivery state; opaque credentials are stored as hashes."""

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(24))
    enabled: Mapped[bool] = mapped_column(Boolean)


class AccessSession(Base):
    __tablename__ = "access_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[int] = mapped_column(Integer)


class OneTimeToken(Base):
    __tablename__ = "access_tokens"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))
    expires: Mapped[int] = mapped_column(Integer)


class Destination(Base):
    __tablename__ = "telegram_destinations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    chat_id: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean)
    language: Mapped[str] = mapped_column(String(2))
    kinds: Mapped[list] = mapped_column(JSON)


class Outbox(Base):
    __tablename__ = "notification_outbox"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    destination_id: Mapped[str] = mapped_column(String(64), index=True)
    event_key: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(24))
    text: Mapped[str] = mapped_column(String(4096))
    status: Mapped[str] = mapped_column(String(24), index=True)
    attempts: Mapped[int] = mapped_column(Integer)
    available: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(100))
    message_id: Mapped[str | None] = mapped_column(String(64))


class ServiceState(Base):
    __tablename__ = "access_delivery_state"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int] = mapped_column(Integer)
