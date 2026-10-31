"""Durable simulator state and append-only command journal."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db import Base


class PaperAccount(Base):
    __tablename__ = "paper_accounts"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict] = mapped_column(JSON)
    state: Mapped[dict] = mapped_column(JSON)


class PaperOrder(Base):
    __tablename__ = "paper_orders"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request: Mapped[dict] = mapped_column(JSON)
    state: Mapped[dict] = mapped_column(JSON)


class PaperQuote(Base):
    __tablename__ = "paper_quotes"
    __table_args__ = (Index("ix_paper_quotes_lookup", "account_id", "symbol", "observed_at"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)
    symbol: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_bid: Mapped[int] = mapped_column(Integer)
    used_ask: Mapped[int] = mapped_column(Integer)


class PaperJournal(Base):
    __tablename__ = "paper_journal"
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(64), unique=True)
    account_id: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_sha256: Mapped[str] = mapped_column(String(64))
    previous_sha256: Mapped[str] = mapped_column(String(64))
    entry_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)


class PaperRun(Base):
    __tablename__ = "paper_runs"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    protocol: Mapped[dict] = mapped_column(JSON)
    state: Mapped[dict] = mapped_column(JSON)


class PaperCycle(Base):
    __tablename__ = "paper_cycles"
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(64), unique=True)
    run_id: Mapped[str] = mapped_column(String(200), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)
    previous_sha256: Mapped[str] = mapped_column(String(64))
    entry_sha256: Mapped[str] = mapped_column(String(64))
