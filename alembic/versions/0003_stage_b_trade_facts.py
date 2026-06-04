"""add stage b trade fact fields

Revision ID: 0003_stage_b_trade_facts
Revises: 0002_oms_repository_support
Create Date: 2026-06-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_stage_b_trade_facts"
down_revision: str | None = "0002_oms_repository_support"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DECIMAL = sa.Numeric(precision=28, scale=8, asdecimal=True)


def upgrade() -> None:
    op.add_column("trades", sa.Column("fee_amount", DECIMAL, nullable=True))
    op.add_column("trades", sa.Column("fee_currency", sa.String(length=16), nullable=True))
    op.add_column("trades", sa.Column("fee_source", sa.String(length=32), nullable=True))
    op.add_column("trades", sa.Column("trading_day", sa.Date(), nullable=True))
    op.add_column(
        "trades",
        sa.Column("source_exchange_report_id", sa.String(length=128), nullable=True),
    )
    op.add_column("trades", sa.Column("raw_payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "raw_payload")
    op.drop_column("trades", "source_exchange_report_id")
    op.drop_column("trades", "trading_day")
    op.drop_column("trades", "fee_source")
    op.drop_column("trades", "fee_currency")
    op.drop_column("trades", "fee_amount")
