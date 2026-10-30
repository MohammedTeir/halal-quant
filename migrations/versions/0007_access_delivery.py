"""Server sessions, expiring tokens, verified Telegram destinations and outbox."""

import sqlalchemy as sa
from alembic import op

revision = "0007_access_delivery"
down_revision = "0006_controls"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=254), primary_key=False, nullable=False),
        sa.Column("password", sa.String(length=256), primary_key=False, nullable=False),
        sa.Column("role", sa.String(length=24), primary_key=False, nullable=False),
        sa.Column("enabled", sa.Boolean(), primary_key=False, nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "access_sessions",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("csrf", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("expires", sa.Integer(), primary_key=False, nullable=False),
    )
    op.create_index("ix_access_sessions_user_id", "access_sessions", ["user_id"])
    op.create_table(
        "access_tokens",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("kind", sa.String(length=24), primary_key=False, nullable=False),
        sa.Column("expires", sa.Integer(), primary_key=False, nullable=False),
    )
    op.create_table(
        "telegram_destinations",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("chat_id", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("enabled", sa.Boolean(), primary_key=False, nullable=False),
        sa.Column("language", sa.String(length=2), primary_key=False, nullable=False),
        sa.Column("kinds", sa.JSON(), primary_key=False, nullable=False),
        sa.UniqueConstraint("chat_id"),
    )
    op.create_index("ix_telegram_destinations_user_id", "telegram_destinations", ["user_id"])
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("destination_id", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("event_key", sa.String(length=256), primary_key=False, nullable=False),
        sa.Column("kind", sa.String(length=24), primary_key=False, nullable=False),
        sa.Column("text", sa.String(length=4096), primary_key=False, nullable=False),
        sa.Column("status", sa.String(length=24), primary_key=False, nullable=False),
        sa.Column("attempts", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("available", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("error", sa.String(length=100), primary_key=False, nullable=True),
        sa.Column("message_id", sa.String(length=64), primary_key=False, nullable=True),
    )
    op.create_index("ix_notification_outbox_status", "notification_outbox", ["status"])
    op.create_index(
        "ix_notification_outbox_destination_id", "notification_outbox", ["destination_id"]
    )
    op.create_table(
        "access_delivery_state",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("value", sa.Integer(), primary_key=False, nullable=False),
    )
    op.bulk_insert(
        sa.table(
            "access_delivery_state", sa.column("id", sa.String), sa.column("value", sa.Integer)
        ),
        [
            {"id": "access", "value": 0},
            {"id": "delivery", "value": 0},
            {"id": "telegram_offset", "value": 0},
        ],
    )


def downgrade():
    op.drop_table("access_delivery_state")
    op.drop_table("notification_outbox")
    op.drop_table("telegram_destinations")
    op.drop_table("access_tokens")
    op.drop_table("access_sessions")
    op.drop_table("users")
