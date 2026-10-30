from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class SignalRecord(Base):
    __tablename__ = "signals"
    event_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditRecord(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(80))
    subject: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def utcnow():
    return datetime.now(UTC)


def session_factory(url):
    engine = create_engine(url, pool_pre_ping=True)
    return engine, sessionmaker(engine, expire_on_commit=False)


class DataImport(Base):
    __tablename__ = "data_imports"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    batch_id: Mapped[str] = mapped_column(String(200))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    inserted: Mapped[int] = mapped_column(Integer)
    duplicates: Mapped[int] = mapped_column(Integer)


class ImportedEvent:
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    item_id: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(Integer)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class NewsRecord(ImportedEvent, Base):
    __tablename__ = "news_events"
    story_key: Mapped[str] = mapped_column(String(64), index=True)


class EconomicRecord(ImportedEvent, Base):
    __tablename__ = "economic_events"


class CorporateActionRecord(ImportedEvent, Base):
    __tablename__ = "corporate_actions"


class ClassificationRecord(Base):
    __tablename__ = "news_classifications"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class DecisionRecord(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    signal_id: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    response: Mapped[dict] = mapped_column(JSON)


class GenerationJob(Base):
    __tablename__ = "classification_jobs"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    owner: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    result_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class FeedCoverageRecord(Base):
    __tablename__ = "feed_coverage"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    import_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(64), index=True)
    asset_class: Mapped[str] = mapped_column(String(16))
    purpose: Mapped[str] = mapped_column(String(32))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ControlLock(Base):
    __tablename__ = "control_lock"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)


class ControlRevision(Base):
    __tablename__ = "control_revisions"
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    scope: Mapped[str] = mapped_column(String(200), index=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(200))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)


class BrokerCapture(Base):
    __tablename__ = "broker_captures"
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(200), unique=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16), index=True)
    scope: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ControlCheckRecord(Base):
    __tablename__ = "control_checks"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    account_id: Mapped[str] = mapped_column(String(200), index=True)
    signal_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ControlReservation(Base):
    __tablename__ = "control_reservations"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(200), index=True)
    signal_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
