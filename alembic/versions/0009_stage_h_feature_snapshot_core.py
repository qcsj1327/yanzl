"""stage h feature snapshot core

Revision ID: 0009_stage_h_feature_core
Revises: 0008_stage_g_market_data_core
Create Date: 2026-06-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_stage_h_feature_core"
down_revision: str | None = "0008_stage_g_market_data_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("trade_instrument_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("bar_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_version", sa.String(length=128), nullable=False),
        sa.Column("feature_config_hash", sa.String(length=64), nullable=False),
        sa.Column("source_bar_keys", sa.JSON(), nullable=False),
        sa.Column("returns", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("bar_return", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("price_range", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("range", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("atr", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("volume_ratio", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("moving_average", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("bias", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("breakout_level", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("volatility", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("momentum", sa.Numeric(precision=28, scale=8), nullable=True),
        sa.Column("source_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("warmup_complete", sa.Boolean(), nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("missing_bar_count", sa.Integer(), nullable=False),
        sa.Column("gap_count", sa.Integer(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "exchange",
            "instrument_id",
            "timeframe",
            "bar_ts",
            "feature_version",
            "feature_config_hash",
            name="uq_feature_snapshots_identity",
        ),
    )
    op.create_index("ix_feature_snapshots_exchange", "feature_snapshots", ["exchange"])
    op.create_index(
        "ix_feature_snapshots_instrument_id",
        "feature_snapshots",
        ["instrument_id"],
    )
    op.create_index(
        "ix_feature_snapshots_trading_day",
        "feature_snapshots",
        ["trading_day"],
    )
    op.create_index("ix_feature_snapshots_timeframe", "feature_snapshots", ["timeframe"])
    op.create_index("ix_feature_snapshots_bar_ts", "feature_snapshots", ["bar_ts"])
    op.create_index(
        "ix_feature_snapshots_feature_version",
        "feature_snapshots",
        ["feature_version"],
    )
    op.create_index(
        "ix_feature_snapshots_feature_config_hash",
        "feature_snapshots",
        ["feature_config_hash"],
    )
    op.create_index(
        "ix_feature_snapshots_exchange_instrument_day",
        "feature_snapshots",
        ["exchange", "instrument_id", "trading_day"],
    )


def downgrade() -> None:
    op.drop_index("ix_feature_snapshots_exchange_instrument_day", table_name="feature_snapshots")
    op.drop_index("ix_feature_snapshots_feature_config_hash", table_name="feature_snapshots")
    op.drop_index("ix_feature_snapshots_feature_version", table_name="feature_snapshots")
    op.drop_index("ix_feature_snapshots_bar_ts", table_name="feature_snapshots")
    op.drop_index("ix_feature_snapshots_timeframe", table_name="feature_snapshots")
    op.drop_index("ix_feature_snapshots_trading_day", table_name="feature_snapshots")
    op.drop_index("ix_feature_snapshots_instrument_id", table_name="feature_snapshots")
    op.drop_index("ix_feature_snapshots_exchange", table_name="feature_snapshots")
    op.drop_table("feature_snapshots")
