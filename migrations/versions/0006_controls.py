"""Versioned controls, machine broker captures and serialized research reservations."""

import sqlalchemy as sa
from alembic import op

revision = "0006_controls"
down_revision = "0005_feed_coverage"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "control_lock",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
    )
    op.create_table(
        "control_revisions",
        sa.Column("sequence", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("record_id", sa.String(200), primary_key=False, nullable=False, unique=True),
        sa.Column("kind", sa.String(32), primary_key=False, nullable=False),
        sa.Column("scope", sa.String(200), primary_key=False, nullable=False),
        sa.Column("request_sha256", sa.String(64), primary_key=False, nullable=False),
        sa.Column("actor", sa.String(200), primary_key=False, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), primary_key=False, nullable=True),
        sa.Column("payload", sa.JSON(), primary_key=False, nullable=False),
    )
    op.create_index("ix_control_revisions_kind", "control_revisions", ["kind"])
    op.create_index("ix_control_revisions_received_at", "control_revisions", ["received_at"])
    op.create_index("ix_control_revisions_scope", "control_revisions", ["scope"])
    op.create_table(
        "broker_captures",
        sa.Column("sequence", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("id", sa.String(200), primary_key=False, nullable=False, unique=True),
        sa.Column("request_sha256", sa.String(64), primary_key=False, nullable=False),
        sa.Column("kind", sa.String(16), primary_key=False, nullable=False),
        sa.Column("scope", sa.String(200), primary_key=False, nullable=True),
        sa.Column("status", sa.String(16), primary_key=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), primary_key=False, nullable=True),
        sa.Column("error_code", sa.String(64), primary_key=False, nullable=True),
        sa.Column("payload", sa.JSON(), primary_key=False, nullable=True),
    )
    op.create_index("ix_broker_captures_created_at", "broker_captures", ["created_at"])
    op.create_index("ix_broker_captures_kind", "broker_captures", ["kind"])
    op.create_index("ix_broker_captures_scope", "broker_captures", ["scope"])
    op.create_table(
        "control_checks",
        sa.Column("id", sa.String(200), primary_key=True, nullable=False),
        sa.Column("request_sha256", sa.String(64), primary_key=False, nullable=False),
        sa.Column("account_id", sa.String(200), primary_key=False, nullable=False),
        sa.Column("signal_id", sa.String(200), primary_key=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.Column("payload", sa.JSON(), primary_key=False, nullable=False),
    )
    op.create_index("ix_control_checks_account_id", "control_checks", ["account_id"])
    op.create_index("ix_control_checks_created_at", "control_checks", ["created_at"])
    op.create_table(
        "control_reservations",
        sa.Column("id", sa.String(200), primary_key=True, nullable=False),
        sa.Column("account_id", sa.String(200), primary_key=False, nullable=False),
        sa.Column("signal_id", sa.String(200), primary_key=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), primary_key=False, nullable=False),
        sa.Column("payload", sa.JSON(), primary_key=False, nullable=False),
    )
    op.create_index("ix_control_reservations_account_id", "control_reservations", ["account_id"])
    op.create_index("ix_control_reservations_expires_at", "control_reservations", ["expires_at"])
    op.bulk_insert(
        sa.table("control_lock", sa.column("id", sa.String(64))), [{"id": "controls-v1"}]
    )


def downgrade():
    op.drop_table("control_reservations")
    op.drop_table("control_checks")
    op.drop_table("broker_captures")
    op.drop_table("control_revisions")
    op.drop_table("control_lock")
