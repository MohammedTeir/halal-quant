"""Versioned model assessments and immutable explainable research decisions."""

import sqlalchemy as sa
from alembic import op

revision = "0003_intelligence"
down_revision = "0002_data_events"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "news_classifications",
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_news_classifications_created_at", "news_classifications", ["created_at"])
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("signal_id", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
    )
    op.create_index("ix_decisions_signal_id", "decisions", ["signal_id"])
    op.create_index("ix_decisions_created_at", "decisions", ["created_at"])


def downgrade():
    op.drop_table("decisions")
    op.drop_table("news_classifications")
