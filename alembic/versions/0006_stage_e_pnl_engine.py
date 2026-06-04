"""add stage e pnl snapshots

Revision ID: 0006_stage_e_pnl_engine
Revises: 0005_stage_d_margin_engine
Create Date: 2026-06-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_stage_e_pnl_engine"
down_revision: str | None = "0005_stage_d_margin_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DECIMAL = sa.Numeric(precision=28, scale=8, asdecimal=True)


def upgrade() -> None:
    op.create_table(
        "pnl_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("position_version", sa.Integer(), nullable=False),
        sa.Column("trade_id", sa.String(length=128), nullable=True),
        sa.Column("margin_snapshot_id", sa.String(length=128), nullable=True),
        sa.Column("calculation_key", sa.String(length=256), nullable=False),
        sa.Column("price_basis", sa.String(length=32), nullable=False),
        sa.Column("mark_price", DECIMAL, nullable=False),
        sa.Column("contract_multiplier", DECIMAL, nullable=False),
        sa.Column("realized_pnl", DECIMAL, nullable=False),
        sa.Column("unrealized_pnl", DECIMAL, nullable=False),
        sa.Column("total_pnl", DECIMAL, nullable=False),
        sa.Column("fee_amount", DECIMAL, nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "instrument_id",
            "calculation_key",
            name="uq_pnl_snapshots_account_instrument_calculation",
        ),
    )
    op.create_index("ix_pnl_snapshots_account_id", "pnl_snapshots", ["account_id"])
    op.create_index("ix_pnl_snapshots_instrument_id", "pnl_snapshots", ["instrument_id"])
    op.create_index(
        "ix_pnl_snapshots_account_instrument",
        "pnl_snapshots",
        ["account_id", "instrument_id"],
    )
    op.create_index(
        "ix_pnl_snapshots_position_version",
        "pnl_snapshots",
        ["position_version"],
    )
    op.create_index("ix_pnl_snapshots_trade_id", "pnl_snapshots", ["trade_id"])
    op.create_index(
        "ix_pnl_snapshots_calculation_key",
        "pnl_snapshots",
        ["calculation_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_pnl_snapshots_calculation_key", table_name="pnl_snapshots")
    op.drop_index("ix_pnl_snapshots_trade_id", table_name="pnl_snapshots")
    op.drop_index("ix_pnl_snapshots_position_version", table_name="pnl_snapshots")
    op.drop_index("ix_pnl_snapshots_account_instrument", table_name="pnl_snapshots")
    op.drop_index("ix_pnl_snapshots_instrument_id", table_name="pnl_snapshots")
    op.drop_index("ix_pnl_snapshots_account_id", table_name="pnl_snapshots")
    op.drop_table("pnl_snapshots")
