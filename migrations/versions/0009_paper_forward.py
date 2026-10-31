"""Persistent reviewed forward protocols and fenced worker observations."""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0009_paper_forward"
down_revision = "0008_paper_simulator"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("paper_quotes", sa.Column("symbol", sa.String(64), nullable=True))
    op.add_column(
        "paper_quotes", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True)
    )
    quotes = sa.table(
        "paper_quotes",
        sa.column("id", sa.String(64)),
        sa.column("payload", sa.JSON()),
        sa.column("symbol", sa.String(64)),
        sa.column("observed_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    for row in bind.execute(sa.select(quotes.c.id, quotes.c.payload)):
        bind.execute(
            quotes.update()
            .where(quotes.c.id == row.id)
            .values(
                symbol=row.payload["symbol"],
                observed_at=datetime.fromisoformat(row.payload["observed_at"]),
            )
        )
    with op.batch_alter_table("paper_quotes") as batch:
        batch.alter_column("symbol", existing_type=sa.String(64), nullable=False)
        batch.alter_column("observed_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.create_index(
        "ix_paper_quotes_lookup", "paper_quotes", ["account_id", "symbol", "observed_at"]
    )
    op.create_table(
        "paper_runs",
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("account_id", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("protocol", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
    )
    op.create_index("ix_paper_runs_account_id", "paper_runs", ["account_id"])
    op.create_table(
        "paper_cycles",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(64), nullable=False, unique=True),
        sa.Column("run_id", sa.String(200), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("previous_sha256", sa.String(64), nullable=False),
        sa.Column("entry_sha256", sa.String(64), nullable=False),
    )
    op.create_index("ix_paper_cycles_run_id", "paper_cycles", ["run_id"])


def downgrade():
    op.drop_index("ix_paper_quotes_lookup", table_name="paper_quotes")
    with op.batch_alter_table("paper_quotes") as batch:
        batch.drop_column("observed_at")
        batch.drop_column("symbol")
    op.drop_table("paper_cycles")
    op.drop_table("paper_runs")
