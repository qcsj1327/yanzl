"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DECIMAL = sa.Numeric(precision=28, scale=8, asdecimal=True)


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=32), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("multiplier", DECIMAL, nullable=False),
        sa.Column("price_tick", DECIMAL, nullable=False),
        sa.Column("upper_limit_price", DECIMAL),
        sa.Column("lower_limit_price", DECIMAL),
        sa.Column("margin_rate", DECIMAL, nullable=False),
        sa.Column("delivery_month", sa.String(length=16)),
        sa.Column("is_disabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("instrument_id"),
    )
    op.create_index("ix_instruments_product_id", "instruments", ["product_id"])
    op.create_index("ix_instruments_exchange", "instruments", ["exchange"])

    op.create_table(
        "trading_calendars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("is_trading_day", sa.Boolean(), nullable=False),
        sa.Column("night_session_trading_day", sa.Date()),
        sa.Column("note", sa.String(length=255)),
        sa.UniqueConstraint("exchange", "trading_day", name="uq_calendar_exchange_day"),
    )

    op.create_table(
        "trading_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("product_id", sa.String(length=32)),
        sa.Column("instrument_id", sa.String(length=64)),
        sa.Column("session_name", sa.String(length=64), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_night", sa.Boolean(), nullable=False),
        sa.Column("effective_from", sa.Date()),
        sa.Column("effective_to", sa.Date()),
    )
    op.create_index("ix_trading_sessions_exchange", "trading_sessions", ["exchange"])
    op.create_index("ix_trading_sessions_product_id", "trading_sessions", ["product_id"])
    op.create_index("ix_trading_sessions_instrument_id", "trading_sessions", ["instrument_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_order_id", sa.String(length=128), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("offset", sa.String(length=32), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("limit_price", DECIMAL, nullable=False),
        sa.Column("quantity", DECIMAL, nullable=False),
        sa.Column("filled_quantity", DECIMAL, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reject_reason", sa.String(length=512)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_order_id"),
    )
    op.create_index("ix_orders_account_id", "orders", ["account_id"])
    op.create_index("ix_orders_instrument_id", "orders", ["instrument_id"])
    op.create_index("ix_orders_exchange", "orders", ["exchange"])

    op.create_table(
        "order_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("previous_status", sa.String(length=32)),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("event_source", sa.String(length=32), nullable=False),
        sa.Column("external_event_id", sa.String(length=128), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "event_source", "external_event_id", name="uq_order_events_source_external"
        ),
    )
    op.create_index(
        "ix_order_events_order_id_created_at", "order_events", ["order_id", "created_at"]
    )

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("exchange_trade_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("offset", sa.String(length=32), nullable=False),
        sa.Column("price", DECIMAL, nullable=False),
        sa.Column("quantity", DECIMAL, nullable=False),
        sa.Column("trade_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "account_id", "exchange", "exchange_trade_id", name="uq_trades_account_exchange_trade"
        ),
    )
    op.create_index("ix_trades_account_id", "trades", ["account_id"])
    op.create_index("ix_trades_instrument_id", "trades", ["instrument_id"])

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("long_today_qty", DECIMAL, nullable=False),
        sa.Column("long_yesterday_qty", DECIMAL, nullable=False),
        sa.Column("short_today_qty", DECIMAL, nullable=False),
        sa.Column("short_yesterday_qty", DECIMAL, nullable=False),
        sa.Column("frozen_long_qty", DECIMAL, nullable=False),
        sa.Column("frozen_short_qty", DECIMAL, nullable=False),
        sa.Column("long_avg_price", DECIMAL, nullable=False),
        sa.Column("short_avg_price", DECIMAL, nullable=False),
        sa.Column("settlement_price", DECIMAL, nullable=False),
        sa.Column("last_price", DECIMAL, nullable=False),
        sa.Column("realized_pnl", DECIMAL, nullable=False),
        sa.Column("unrealized_pnl", DECIMAL, nullable=False),
        sa.Column("margin_used", DECIMAL, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("account_id", "instrument_id", name="uq_positions_account_inst"),
    )
    op.create_index("ix_positions_account_id", "positions", ["account_id"])
    op.create_index("ix_positions_instrument_id", "positions", ["instrument_id"])

    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("equity", DECIMAL, nullable=False),
        sa.Column("available_cash", DECIMAL, nullable=False),
        sa.Column("margin_used", DECIMAL, nullable=False),
        sa.Column("frozen_margin", DECIMAL, nullable=False),
        sa.Column("realized_pnl", DECIMAL, nullable=False),
        sa.Column("unrealized_pnl", DECIMAL, nullable=False),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_account_snapshots_account_id", "account_snapshots", ["account_id"])

    op.create_table(
        "settlement_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("cash_before", DECIMAL, nullable=False),
        sa.Column("cash_after", DECIMAL, nullable=False),
        sa.Column("positions_before", sa.JSON(), nullable=False),
        sa.Column("positions_after", sa.JSON(), nullable=False),
        sa.Column("settlement_prices", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_settlement_snapshots_trading_day", "settlement_snapshots", ["trading_day"])
    op.create_index("ix_settlement_snapshots_account_id", "settlement_snapshots", ["account_id"])

    op.create_table(
        "risk_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_name", sa.String(length=128), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=512)),
        sa.Column("signal_id", sa.String(length=128)),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id")),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_risk_events_rule_name", "risk_events", ["rule_name"])
    op.create_index("ix_risk_events_signal_id", "risk_events", ["signal_id"])


def downgrade() -> None:
    op.drop_table("risk_events")
    op.drop_table("settlement_snapshots")
    op.drop_table("account_snapshots")
    op.drop_table("positions")
    op.drop_table("trades")
    op.drop_table("order_events")
    op.drop_table("orders")
    op.drop_table("trading_sessions")
    op.drop_table("trading_calendars")
    op.drop_table("instruments")
