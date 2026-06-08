"""stage l execution report normalization

Revision ID: 0013_stage_l_execution_reports
Revises: 0012_stage_k_execution_gateway
Create Date: 2026-06-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_stage_l_execution_reports"
down_revision: str | None = "0012_stage_k_execution_gateway"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "normalized_execution_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.String(length=128), nullable=False),
        sa.Column("raw_report_id", sa.String(length=128), nullable=False),
        sa.Column("adapter_name", sa.String(length=128), nullable=False),
        sa.Column("execution_target", sa.String(length=32), nullable=False),
        sa.Column("command_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("client_order_id", sa.String(length=128), nullable=False),
        sa.Column("adapter_order_ref", sa.String(length=128), nullable=False),
        sa.Column("exchange_order_id", sa.String(length=128), nullable=True),
        sa.Column("execution_status", sa.String(length=32), nullable=False),
        sa.Column("filled_qty", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("fill_price", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("cumulative_filled_qty", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("remaining_qty", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("report_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_report_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "report_id",
            name="uq_normalized_execution_reports_report_id",
        ),
    )
    op.create_index(
        "ix_normalized_execution_reports_order_id",
        "normalized_execution_reports",
        ["order_id"],
    )
    op.create_index(
        "ix_normalized_execution_reports_command_id",
        "normalized_execution_reports",
        ["command_id"],
    )
    op.create_index(
        "ix_normalized_execution_reports_client_order_id",
        "normalized_execution_reports",
        ["client_order_id"],
    )
    op.create_index(
        "ix_normalized_execution_reports_execution_status",
        "normalized_execution_reports",
        ["execution_status"],
    )
    op.create_index(
        "ix_normalized_execution_reports_report_ts",
        "normalized_execution_reports",
        ["report_ts"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_normalized_execution_reports_report_ts",
        table_name="normalized_execution_reports",
    )
    op.drop_index(
        "ix_normalized_execution_reports_execution_status",
        table_name="normalized_execution_reports",
    )
    op.drop_index(
        "ix_normalized_execution_reports_client_order_id",
        table_name="normalized_execution_reports",
    )
    op.drop_index(
        "ix_normalized_execution_reports_command_id",
        table_name="normalized_execution_reports",
    )
    op.drop_index(
        "ix_normalized_execution_reports_order_id",
        table_name="normalized_execution_reports",
    )
    op.drop_table("normalized_execution_reports")
