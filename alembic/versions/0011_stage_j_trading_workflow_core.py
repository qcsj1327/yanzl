"""stage j trading workflow core

Revision ID: 0011_stage_j_trading_workflow
Revises: 0010_stage_i_signal_lifecycle
Create Date: 2026-06-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_stage_j_trading_workflow"
down_revision: str | None = "0010_stage_i_signal_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("risk_result_id", sa.String(length=128), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("evaluation_context_hash", sa.String(length=64), nullable=False),
        sa.Column("risk_status", sa.String(length=32), nullable=False),
        sa.Column("risk_reason", sa.String(length=512), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("max_quantity", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("expected_margin", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("expected_notional", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("evaluation_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("risk_result_id", name="uq_risk_results_risk_result_id"),
    )
    op.create_index("ix_risk_results_signal_id", "risk_results", ["signal_id"])

    op.create_table(
        "order_intents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("intent_id", sa.String(length=128), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("risk_result_id", sa.String(length=128), nullable=False),
        sa.Column("strategy_name", sa.String(length=128), nullable=False),
        sa.Column("strategy_version", sa.String(length=128), nullable=False),
        sa.Column("strategy_config_hash", sa.String(length=64), nullable=False),
        sa.Column("runtime_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("trade_instrument_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("bar_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_version", sa.String(length=128), nullable=False),
        sa.Column("feature_config_hash", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("offset", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("tif", sa.String(length=16), nullable=False),
        sa.Column("expected_margin", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("expected_notional", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("intent_reason", sa.String(length=512), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("intent_id", name="uq_order_intents_intent_id"),
    )
    op.create_index("ix_order_intents_signal_id", "order_intents", ["signal_id"])
    op.create_index("ix_order_intents_risk_result_id", "order_intents", ["risk_result_id"])
    op.create_index("ix_order_intents_instrument_id", "order_intents", ["instrument_id"])
    op.create_index("ix_order_intents_trading_day", "order_intents", ["trading_day"])


def downgrade() -> None:
    op.drop_index("ix_order_intents_trading_day", table_name="order_intents")
    op.drop_index("ix_order_intents_instrument_id", table_name="order_intents")
    op.drop_index("ix_order_intents_risk_result_id", table_name="order_intents")
    op.drop_index("ix_order_intents_signal_id", table_name="order_intents")
    op.drop_table("order_intents")
    op.drop_index("ix_risk_results_signal_id", table_name="risk_results")
    op.drop_table("risk_results")
