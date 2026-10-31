"""Internal synthetic paper accounts, lifecycle and journal."""

import sqlalchemy as sa
from alembic import op

revision = "0008_paper_simulator"
down_revision = "0007_access_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
    )
    for name, columns in [
        (
            "paper_orders",
            [
                sa.Column("request", sa.JSON(), nullable=False),
                sa.Column("state", sa.JSON(), nullable=False),
            ],
        ),
        (
            "paper_quotes",
            [
                sa.Column("payload", sa.JSON(), nullable=False),
                sa.Column("used_bid", sa.Integer(), nullable=False),
                sa.Column("used_ask", sa.Integer(), nullable=False),
            ],
        ),
    ]:
        op.create_table(
            name,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("account_id", sa.String(200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            *columns,
        )
        op.create_index("ix_" + name + "_account_id", name, ["account_id"])
    op.create_table(
        "paper_journal",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("previous_sha256", sa.String(64), nullable=False),
        sa.Column("entry_sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
    )
    op.create_index("ix_paper_journal_account_id", "paper_journal", ["account_id"])


def downgrade():
    for name in ("paper_journal", "paper_quotes", "paper_orders", "paper_accounts"):
        op.drop_table(name)
