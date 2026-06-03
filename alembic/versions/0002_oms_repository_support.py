"""add oms repository support columns

Revision ID: 0002_oms_repository_support
Revises: 0001_initial_schema
Create Date: 2026-06-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_oms_repository_support"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "order_events",
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.alter_column("order_events", "occurred_at", server_default=None)


def downgrade() -> None:
    op.drop_column("order_events", "occurred_at")
    op.drop_column("orders", "version")
