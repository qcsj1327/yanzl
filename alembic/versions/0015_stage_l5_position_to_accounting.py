"""add stage l5 accounting lineage fields

Revision ID: 0015_stage_l5_accounting
Revises: 0014_stage_l3_oms_to_trade_bridge
Create Date: 2026-06-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_stage_l5_accounting"
down_revision: str | None = "0014_stage_l3_oms_trade_bridge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "margin_snapshots",
        sa.Column("trading_day", sa.Date(), nullable=False, server_default="1970-01-01"),
    )
    op.add_column(
        "margin_snapshots",
        sa.Column("config_hash", sa.String(length=128), nullable=False, server_default="legacy"),
    )
    op.alter_column("margin_snapshots", "trading_day", server_default=None)
    op.alter_column("margin_snapshots", "config_hash", server_default=None)
    op.create_index(
        "ix_margin_snapshots_l5_accounting_identity",
        "margin_snapshots",
        ["account_id", "instrument_id", "position_version", "trading_day", "config_hash"],
    )

    op.add_column(
        "pnl_snapshots",
        sa.Column("trading_day", sa.Date(), nullable=False, server_default="1970-01-01"),
    )
    op.add_column(
        "pnl_snapshots",
        sa.Column("config_hash", sa.String(length=128), nullable=False, server_default="legacy"),
    )
    op.alter_column("pnl_snapshots", "trading_day", server_default=None)
    op.alter_column("pnl_snapshots", "config_hash", server_default=None)
    op.create_index(
        "ix_pnl_snapshots_l5_accounting_identity",
        "pnl_snapshots",
        ["account_id", "instrument_id", "position_version", "trading_day", "config_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_pnl_snapshots_l5_accounting_identity", table_name="pnl_snapshots")
    op.drop_column("pnl_snapshots", "config_hash")
    op.drop_column("pnl_snapshots", "trading_day")

    op.drop_index("ix_margin_snapshots_l5_accounting_identity", table_name="margin_snapshots")
    op.drop_column("margin_snapshots", "config_hash")
    op.drop_column("margin_snapshots", "trading_day")
