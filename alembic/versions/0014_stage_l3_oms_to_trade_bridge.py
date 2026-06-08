"""add stage l3 oms to trade bridge fields

Revision ID: 0014_stage_l3_oms_trade_bridge
Revises: 0013_stage_l_execution_reports
Create Date: 2026-06-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_stage_l3_oms_trade_bridge"
down_revision: str | None = "0013_stage_l_execution_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DECIMAL = sa.Numeric(precision=28, scale=8, asdecimal=True)


def upgrade() -> None:
    op.add_column("trades", sa.Column("identity_source", sa.String(length=32), nullable=True))
    op.add_column("trades", sa.Column("client_order_id", sa.String(length=128), nullable=True))
    op.add_column(
        "trades",
        sa.Column("trade_instrument_id", sa.String(length=64), nullable=True),
    )
    op.add_column("trades", sa.Column("symbol", sa.String(length=64), nullable=True))
    op.add_column("trades", sa.Column("source_report_id", sa.String(length=128), nullable=True))
    op.add_column(
        "trades",
        sa.Column("source_order_event_id", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_trades_order_id", "trades", ["order_id"])

    op.add_column(
        "normalized_execution_reports",
        sa.Column("exchange_trade_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "normalized_execution_reports",
        sa.Column("fill_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "normalized_execution_reports",
        sa.Column("fee_amount", DECIMAL, nullable=True),
    )
    op.add_column(
        "normalized_execution_reports",
        sa.Column("fee_currency", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "normalized_execution_reports",
        sa.Column("fee_source", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("normalized_execution_reports", "fee_source")
    op.drop_column("normalized_execution_reports", "fee_currency")
    op.drop_column("normalized_execution_reports", "fee_amount")
    op.drop_column("normalized_execution_reports", "fill_id")
    op.drop_column("normalized_execution_reports", "exchange_trade_id")

    op.drop_index("ix_trades_order_id", table_name="trades")
    op.drop_column("trades", "source_order_event_id")
    op.drop_column("trades", "source_report_id")
    op.drop_column("trades", "symbol")
    op.drop_column("trades", "trade_instrument_id")
    op.drop_column("trades", "client_order_id")
    op.drop_column("trades", "identity_source")
