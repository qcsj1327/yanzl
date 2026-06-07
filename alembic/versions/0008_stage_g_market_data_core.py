"""add stage g market data core facts

Revision ID: 0008_stage_g_market_data_core
Revises: 0007_stage_f_settlement_engine
Create Date: 2026-06-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_stage_g_market_data_core"
down_revision: str | None = "0007_stage_f_settlement_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DECIMAL = sa.Numeric(precision=28, scale=8, asdecimal=True)


def upgrade() -> None:
    op.create_table(
        "market_ticks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("trade_instrument_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", DECIMAL, nullable=False),
        sa.Column("volume", DECIMAL, nullable=False),
        sa.Column("turnover", DECIMAL, nullable=False),
        sa.Column("open_interest", DECIMAL, nullable=False),
        sa.Column("bid_price_1", DECIMAL),
        sa.Column("ask_price_1", DECIMAL),
        sa.Column("bid_volume_1", DECIMAL),
        sa.Column("ask_volume_1", DECIMAL),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", sa.JSON()),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "exchange",
            "instrument_id",
            "ts",
            "source",
            name="uq_market_ticks_identity",
        ),
    )
    op.create_index("ix_market_ticks_exchange", "market_ticks", ["exchange"])
    op.create_index("ix_market_ticks_instrument_id", "market_ticks", ["instrument_id"])
    op.create_index("ix_market_ticks_trading_day", "market_ticks", ["trading_day"])
    op.create_index("ix_market_ticks_ts", "market_ticks", ["ts"])
    op.create_index(
        "ix_market_ticks_exchange_instrument_day",
        "market_ticks",
        ["exchange", "instrument_id", "trading_day"],
    )

    op.create_table(
        "market_bars",
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
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("raw_payload", sa.JSON()),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "exchange",
            "instrument_id",
            "timeframe",
            "bar_ts",
            "source",
            name="uq_market_bars_identity",
        ),
    )
    op.create_index("ix_market_bars_exchange", "market_bars", ["exchange"])
    op.create_index("ix_market_bars_instrument_id", "market_bars", ["instrument_id"])
    op.create_index("ix_market_bars_trading_day", "market_bars", ["trading_day"])
    op.create_index("ix_market_bars_bar_ts", "market_bars", ["bar_ts"])
    op.create_index("ix_market_bars_timeframe", "market_bars", ["timeframe"])
    op.create_index(
        "ix_market_bars_exchange_instrument_day",
        "market_bars",
        ["exchange", "instrument_id", "trading_day"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_bars_exchange_instrument_day", table_name="market_bars")
    op.drop_index("ix_market_bars_timeframe", table_name="market_bars")
    op.drop_index("ix_market_bars_bar_ts", table_name="market_bars")
    op.drop_index("ix_market_bars_trading_day", table_name="market_bars")
    op.drop_index("ix_market_bars_instrument_id", table_name="market_bars")
    op.drop_index("ix_market_bars_exchange", table_name="market_bars")
    op.drop_table("market_bars")
    op.drop_index("ix_market_ticks_exchange_instrument_day", table_name="market_ticks")
    op.drop_index("ix_market_ticks_ts", table_name="market_ticks")
    op.drop_index("ix_market_ticks_trading_day", table_name="market_ticks")
    op.drop_index("ix_market_ticks_instrument_id", table_name="market_ticks")
    op.drop_index("ix_market_ticks_exchange", table_name="market_ticks")
    op.drop_table("market_ticks")
