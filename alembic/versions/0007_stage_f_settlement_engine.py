"""extend settlement snapshots for stage f

Revision ID: 0007_stage_f_settlement_engine
Revises: 0006_stage_e_pnl_engine
Create Date: 2026-06-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_stage_f_settlement_engine"
down_revision: str | None = "0006_stage_e_pnl_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DECIMAL = sa.Numeric(precision=28, scale=8, asdecimal=True)


def upgrade() -> None:
    op.add_column(
        "settlement_snapshots",
        sa.Column("calculation_key", sa.String(length=256), nullable=False, server_default=""),
    )
    _backfill_legacy_calculation_keys(op.get_bind())
    op.alter_column(
        "settlement_snapshots",
        "calculation_key",
        existing_type=sa.String(length=256),
        server_default=None,
    )
    op.add_column(
        "settlement_snapshots",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="SETTLED"),
    )
    op.add_column("settlement_snapshots", sa.Column("reason", sa.String(length=512)))
    op.add_column(
        "settlement_snapshots",
        sa.Column("realized_pnl", DECIMAL, nullable=False, server_default="0"),
    )
    op.add_column(
        "settlement_snapshots",
        sa.Column("unrealized_pnl", DECIMAL, nullable=False, server_default="0"),
    )
    op.add_column(
        "settlement_snapshots",
        sa.Column("margin_used", DECIMAL, nullable=False, server_default="0"),
    )
    op.add_column(
        "settlement_snapshots",
        sa.Column("pnl_snapshot_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "settlement_snapshots",
        sa.Column("margin_snapshot_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "settlement_snapshots",
        sa.Column("account_snapshot_before_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "settlement_snapshots",
        sa.Column("account_snapshot_after_id", sa.Integer(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_settlement_account_day",
        "settlement_snapshots",
        ["account_id", "trading_day"],
    )
    op.create_index(
        "ix_settlement_snapshots_account_day",
        "settlement_snapshots",
        ["account_id", "trading_day"],
    )
    op.create_index(
        "ix_settlement_snapshots_calculation_key",
        "settlement_snapshots",
        ["calculation_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_settlement_snapshots_calculation_key", table_name="settlement_snapshots")
    op.drop_index("ix_settlement_snapshots_account_day", table_name="settlement_snapshots")
    op.drop_constraint("uq_settlement_account_day", "settlement_snapshots", type_="unique")
    op.drop_column("settlement_snapshots", "account_snapshot_after_id")
    op.drop_column("settlement_snapshots", "account_snapshot_before_id")
    op.drop_column("settlement_snapshots", "margin_snapshot_ids")
    op.drop_column("settlement_snapshots", "pnl_snapshot_ids")
    op.drop_column("settlement_snapshots", "margin_used")
    op.drop_column("settlement_snapshots", "unrealized_pnl")
    op.drop_column("settlement_snapshots", "realized_pnl")
    op.drop_column("settlement_snapshots", "reason")
    op.drop_column("settlement_snapshots", "status")
    op.drop_column("settlement_snapshots", "calculation_key")


def _backfill_legacy_calculation_keys(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            """
            UPDATE settlement_snapshots
            SET calculation_key = CASE
                WHEN account_id IS NOT NULL AND trading_day IS NOT NULL
                    THEN 'legacy:' || account_id || ':' || CAST(trading_day AS VARCHAR)
                        || ':' || CAST(id AS VARCHAR)
                ELSE 'settlement-legacy-' || CAST(id AS VARCHAR)
            END
            WHERE calculation_key IS NULL OR calculation_key = ''
            """
        )
    )
