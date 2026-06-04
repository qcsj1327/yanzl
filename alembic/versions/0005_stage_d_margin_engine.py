"""add stage d margin snapshots

Revision ID: 0005_stage_d_margin_engine
Revises: 0004_stage_c_position_manager
Create Date: 2026-06-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_stage_d_margin_engine"
down_revision: str | None = "0004_stage_c_position_manager"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DECIMAL = sa.Numeric(precision=28, scale=8, asdecimal=True)


def upgrade() -> None:
    op.create_table(
        "margin_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("position_version", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=True),
        sa.Column("rule_version", sa.String(length=128), nullable=True),
        sa.Column("calculation_key", sa.String(length=256), nullable=False),
        sa.Column("long_qty", DECIMAL, nullable=False),
        sa.Column("short_qty", DECIMAL, nullable=False),
        sa.Column("price", DECIMAL, nullable=False),
        sa.Column("contract_multiplier", DECIMAL, nullable=False),
        sa.Column("initial_margin", DECIMAL, nullable=False),
        sa.Column("maintenance_margin", DECIMAL, nullable=False),
        sa.Column("margin_used", DECIMAL, nullable=False),
        sa.Column("available_cash", DECIMAL, nullable=False),
        sa.Column("equity", DECIMAL, nullable=False),
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
            name="uq_margin_snapshots_account_instrument_calculation",
        ),
    )
    op.create_index("ix_margin_snapshots_account_id", "margin_snapshots", ["account_id"])
    op.create_index(
        "ix_margin_snapshots_instrument_id",
        "margin_snapshots",
        ["instrument_id"],
    )
    op.create_index(
        "ix_margin_snapshots_account_instrument",
        "margin_snapshots",
        ["account_id", "instrument_id"],
    )
    op.create_index(
        "ix_margin_snapshots_position_version",
        "margin_snapshots",
        ["position_version"],
    )
    op.create_index(
        "ix_margin_snapshots_account_instrument_position_version",
        "margin_snapshots",
        ["account_id", "instrument_id", "position_version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_margin_snapshots_account_instrument_position_version",
        table_name="margin_snapshots",
    )
    op.drop_index("ix_margin_snapshots_position_version", table_name="margin_snapshots")
    op.drop_index("ix_margin_snapshots_account_instrument", table_name="margin_snapshots")
    op.drop_index("ix_margin_snapshots_instrument_id", table_name="margin_snapshots")
    op.drop_index("ix_margin_snapshots_account_id", table_name="margin_snapshots")
    op.drop_table("margin_snapshots")
