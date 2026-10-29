"""Explicit target/purpose/window coverage for successful source polls."""

import sqlalchemy as sa
from alembic import op

revision = "0005_feed_coverage"
down_revision = "0004_gemini_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "feed_coverage",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("import_id", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("asset_class", sa.String(16), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name in ("import_id", "symbol"):
        op.create_index(f"ix_feed_coverage_{name}", "feed_coverage", [name])


def downgrade():
    op.drop_table("feed_coverage")
