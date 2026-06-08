"""stage k execution gateway core

Revision ID: 0012_stage_k_execution_gateway
Revises: 0011_stage_j_trading_workflow
Create Date: 2026-06-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_stage_k_execution_gateway"
down_revision: str | None = "0011_stage_j_trading_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("command_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("client_order_id", sa.String(length=128), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("trade_instrument_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("offset", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("tif", sa.String(length=16), nullable=False),
        sa.Column("command_type", sa.String(length=32), nullable=False),
        sa.Column("execution_target", sa.String(length=32), nullable=False),
        sa.Column("command_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("command_id", name="uq_execution_commands_command_id"),
    )
    op.create_index("ix_execution_commands_order_id", "execution_commands", ["order_id"])
    op.create_index(
        "ix_execution_commands_client_order_id",
        "execution_commands",
        ["client_order_id"],
    )
    op.create_index(
        "ix_execution_commands_execution_target",
        "execution_commands",
        ["execution_target"],
    )
    op.create_index("ix_execution_commands_created_at", "execution_commands", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_execution_commands_created_at", table_name="execution_commands")
    op.drop_index("ix_execution_commands_execution_target", table_name="execution_commands")
    op.drop_index("ix_execution_commands_client_order_id", table_name="execution_commands")
    op.drop_index("ix_execution_commands_order_id", table_name="execution_commands")
    op.drop_table("execution_commands")
