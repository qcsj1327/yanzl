"""add phase h historical bars

Revision ID: 0017_phase_h_historical_bars
Revises: 0016_stage_n_report_identity
Create Date: 2026-06-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_phase_h_historical_bars"
down_revision: str | None = "0016_stage_n_report_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DECIMAL = sa.Numeric(precision=28, scale=8, asdecimal=True)


def upgrade() -> None:
    op.create_table(
        "historical_bars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("trade_instrument_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("bar_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", DECIMAL, nullable=False),
        sa.Column("high", DECIMAL, nullable=False),
        sa.Column("low", DECIMAL, nullable=False),
        sa.Column("close", DECIMAL, nullable=False),
        sa.Column("volume", DECIMAL, nullable=False),
        sa.Column("turnover", DECIMAL, nullable=False),
        sa.Column("open_interest", DECIMAL, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("resolver_source", sa.String(length=64), nullable=False),
        sa.Column("resolver_confidence", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "instrument_id",
            "trade_instrument_id",
            "exchange",
            "trading_day",
            "timeframe",
            "bar_ts",
            "source",
            name="uq_historical_bars_identity",
        ),
    )
    op.create_index("ix_historical_bars_symbol", "historical_bars", ["symbol"])
    op.create_index("ix_historical_bars_instrument_id", "historical_bars", ["instrument_id"])
    op.create_index("ix_historical_bars_exchange", "historical_bars", ["exchange"])
    op.create_index("ix_historical_bars_trading_day", "historical_bars", ["trading_day"])
    op.create_index("ix_historical_bars_timeframe", "historical_bars", ["timeframe"])
    op.create_index("ix_historical_bars_bar_ts", "historical_bars", ["bar_ts"])
    op.create_index(
        "ix_historical_bars_lookup",
        "historical_bars",
        ["symbol", "trading_day", "timeframe", "source"],
    )
    op.create_index(
        "ix_historical_bars_instrument_day",
        "historical_bars",
        ["exchange", "instrument_id", "trading_day"],
    )


def downgrade() -> None:
    op.drop_index("ix_historical_bars_instrument_day", table_name="historical_bars")
    op.drop_index("ix_historical_bars_lookup", table_name="historical_bars")
    op.drop_index("ix_historical_bars_bar_ts", table_name="historical_bars")
    op.drop_index("ix_historical_bars_timeframe", table_name="historical_bars")
    op.drop_index("ix_historical_bars_trading_day", table_name="historical_bars")
    op.drop_index("ix_historical_bars_exchange", table_name="historical_bars")
    op.drop_index("ix_historical_bars_instrument_id", table_name="historical_bars")
    op.drop_index("ix_historical_bars_symbol", table_name="historical_bars")
    op.drop_table("historical_bars")
