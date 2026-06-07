"""stage i strategy signal lifecycle

Revision ID: 0010_stage_i_signal_lifecycle
Revises: 0009_stage_h_feature_core
Create Date: 2026-06-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_stage_i_signal_lifecycle"
down_revision: str | None = "0009_stage_h_feature_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signal_candidates",
        sa.Column("signal_id", sa.String(length=128), primary_key=True),
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
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("position_side", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("strength", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("expected_price", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("stop_loss", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("take_profit", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("holding_period_hint", sa.String(length=128), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("features_ref", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("signal_id", name="uq_signal_candidates_signal_id"),
        sa.UniqueConstraint(
            "strategy_name",
            "strategy_version",
            "strategy_config_hash",
            "instrument_id",
            "timeframe",
            "bar_ts",
            "feature_version",
            "feature_config_hash",
            name="uq_signal_candidates_strategy_feature_identity",
        ),
    )
    op.create_index(
        "ix_signal_candidates_strategy_version",
        "signal_candidates",
        ["strategy_name", "strategy_version"],
    )
    op.create_index(
        "ix_signal_candidates_exchange_instrument_day",
        "signal_candidates",
        ["exchange", "instrument_id", "trading_day"],
    )
    op.create_index(
        "ix_signal_candidates_timeframe_bar_ts",
        "signal_candidates",
        ["timeframe", "bar_ts"],
    )
    op.create_index("ix_signal_candidates_signal_id", "signal_candidates", ["signal_id"])

    op.create_table(
        "signal_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(length=64), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("event_reason", sa.String(length=512), nullable=True),
        sa.Column("event_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("event_key", name="uq_signal_events_event_key"),
    )
    op.create_index("ix_signal_events_signal_id", "signal_events", ["signal_id"])
    op.create_index(
        "ix_signal_events_signal_created",
        "signal_events",
        ["signal_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_signal_events_signal_created", table_name="signal_events")
    op.drop_index("ix_signal_events_signal_id", table_name="signal_events")
    op.drop_table("signal_events")
    op.drop_index("ix_signal_candidates_signal_id", table_name="signal_candidates")
    op.drop_index("ix_signal_candidates_timeframe_bar_ts", table_name="signal_candidates")
    op.drop_index(
        "ix_signal_candidates_exchange_instrument_day",
        table_name="signal_candidates",
    )
    op.drop_index("ix_signal_candidates_strategy_version", table_name="signal_candidates")
    op.drop_table("signal_candidates")
