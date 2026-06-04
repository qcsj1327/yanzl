"""add stage c position manager facts

Revision ID: 0004_stage_c_position_manager
Revises: 0003_stage_b_trade_facts
Create Date: 2026-06-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_stage_c_position_manager"
down_revision: str | None = "0003_stage_b_trade_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DECIMAL = sa.Numeric(precision=28, scale=8, asdecimal=True)


def upgrade() -> None:
    op.add_column(
        "positions",
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "position_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("exchange_trade_id", sa.String(length=128), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("offset", sa.String(length=32), nullable=False),
        sa.Column("price", DECIMAL, nullable=False),
        sa.Column("quantity", DECIMAL, nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=False),
        sa.Column("after_snapshot", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"]),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "exchange",
            "exchange_trade_id",
            name="uq_position_events_account_exchange_trade",
        ),
    )
    op.create_index("ix_position_events_account_id", "position_events", ["account_id"])
    op.create_index("ix_position_events_instrument_id", "position_events", ["instrument_id"])
    op.create_index(
        "ix_position_events_account_instrument",
        "position_events",
        ["account_id", "instrument_id"],
    )
    op.create_index("ix_position_events_trade_id", "position_events", ["trade_id"])
    op.create_index(
        "ix_position_events_exchange_trade_id",
        "position_events",
        ["exchange_trade_id"],
    )
    op.create_index("ix_position_events_position_id", "position_events", ["position_id"])


def downgrade() -> None:
    op.drop_index("ix_position_events_position_id", table_name="position_events")
    op.drop_index("ix_position_events_exchange_trade_id", table_name="position_events")
    op.drop_index("ix_position_events_trade_id", table_name="position_events")
    op.drop_index("ix_position_events_account_instrument", table_name="position_events")
    op.drop_index("ix_position_events_instrument_id", table_name="position_events")
    op.drop_index("ix_position_events_account_id", table_name="position_events")
    op.drop_table("position_events")
    op.drop_column("positions", "version")
