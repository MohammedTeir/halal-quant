"""Durable generation claims; no database transaction spans a model call."""

import sqlalchemy as sa
from alembic import op

revision = "0004_gemini_jobs"
down_revision = "0003_intelligence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "classification_jobs",
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result_metadata", sa.JSON(), nullable=True),
    )
    op.create_index("ix_classification_jobs_created_at", "classification_jobs", ["created_at"])


def downgrade():
    op.drop_table("classification_jobs")
