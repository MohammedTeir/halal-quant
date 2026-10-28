"""Immutable source revisions and successful data-feed observations."""

import sqlalchemy as sa
from alembic import op

revision = "0002_data_events"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "data_imports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("batch_id", sa.String(200), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inserted", sa.Integer(), nullable=False),
        sa.Column("duplicates", sa.Integer(), nullable=False),
    )
    op.create_index("ix_data_imports_provider", "data_imports", ["provider"])
    op.create_index("ix_data_imports_received_at", "data_imports", ["received_at"])
    for table in ("news_events", "economic_events", "corporate_actions"):
        columns = [
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("provider", sa.String(64), nullable=False),
            sa.Column("item_id", sa.String(200), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
        ]
        if table == "news_events":
            columns.append(sa.Column("story_key", sa.String(64), nullable=False))
        op.create_table(table, *columns)
        for name in ("provider", "published_at", "received_at"):
            op.create_index(f"ix_{table}_{name}", table, [name])
        if table == "news_events":
            op.create_index("ix_news_events_story_key", table, ["story_key"])


def downgrade():
    for table in ("corporate_actions", "economic_events", "news_events", "data_imports"):
        op.drop_table(table)
