from sqlalchemy import DateTime, Integer, UniqueConstraint

from futures_mvp.db.models import Base, Order, OrderEvent, Position, Trade


def _unique_constraint_columns(model: type[object], name: str) -> tuple[str, ...]:
    for constraint in model.__table__.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"missing unique constraint {name}")


def test_required_tables_are_declared() -> None:
    assert {
        "instruments",
        "trading_calendars",
        "trading_sessions",
        "orders",
        "order_events",
        "trades",
        "positions",
        "account_snapshots",
        "settlement_snapshots",
        "risk_events",
    }.issubset(Base.metadata.tables)


def test_order_events_match_current_schema_idempotency() -> None:
    assert _unique_constraint_columns(OrderEvent, "uq_order_events_source_external") == (
        "event_source",
        "external_event_id",
    )
    assert "raw_payload" in OrderEvent.__table__.columns


def test_order_events_have_business_occurred_at() -> None:
    occurred_at = OrderEvent.__table__.columns["occurred_at"]

    assert isinstance(occurred_at.type, DateTime)
    assert occurred_at.type.timezone is True
    assert occurred_at.nullable is False


def test_orders_have_repository_version_column() -> None:
    version = Order.__table__.columns["version"]

    assert isinstance(version.type, Integer)
    assert version.nullable is False
    assert version.default is not None


def test_trades_unique_constraint_matches_exchange_trade_identity() -> None:
    assert _unique_constraint_columns(Trade, "uq_trades_account_exchange_trade") == (
        "account_id",
        "exchange",
        "exchange_trade_id",
    )


def test_trades_have_stage_b_typed_fact_fields() -> None:
    for column_name in [
        "fee_amount",
        "fee_currency",
        "fee_source",
        "trading_day",
        "source_exchange_report_id",
        "raw_payload",
    ]:
        assert column_name in Trade.__table__.columns


def test_positions_are_single_row_per_account_and_instrument() -> None:
    assert _unique_constraint_columns(Position, "uq_positions_account_inst") == (
        "account_id",
        "instrument_id",
    )
    for column_name in [
        "long_today_qty",
        "long_yesterday_qty",
        "short_today_qty",
        "short_yesterday_qty",
        "frozen_long_qty",
        "frozen_short_qty",
        "long_avg_price",
        "short_avg_price",
        "settlement_price",
        "last_price",
        "realized_pnl",
        "unrealized_pnl",
        "margin_used",
    ]:
        assert column_name in Position.__table__.columns
