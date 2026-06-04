from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

DECIMAL = Numeric(precision=28, scale=8, asdecimal=True)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Instrument(Base, TimestampMixin):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    multiplier: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    price_tick: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    upper_limit_price: Mapped[Decimal | None] = mapped_column(DECIMAL)
    lower_limit_price: Mapped[Decimal | None] = mapped_column(DECIMAL)
    margin_rate: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    delivery_month: Mapped[str | None] = mapped_column(String(16))
    is_disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TradingCalendar(Base):
    __tablename__ = "trading_calendars"
    __table_args__ = (UniqueConstraint("exchange", "trading_day", name="uq_calendar_exchange_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    is_trading_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    night_session_trading_day: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(255))


class TradingSession(Base):
    __tablename__ = "trading_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    product_id: Mapped[str | None] = mapped_column(String(32), index=True)
    instrument_id: Mapped[str | None] = mapped_column(String(64), index=True)
    session_name: Mapped[str] = mapped_column(String(64), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_night: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    offset: Mapped[str] = mapped_column(String(32), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    limit_price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    filled_quantity: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(String(512))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order")
    trades: Mapped[list["Trade"]] = relationship(back_populates="order")


class OrderEvent(Base):
    __tablename__ = "order_events"
    __table_args__ = (
        UniqueConstraint(
            "event_source",
            "external_event_id",
            name="uq_order_events_source_external",
        ),
        Index("ix_order_events_order_id_created_at", "order_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    event_source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="events")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "exchange", "exchange_trade_id", name="uq_trades_account_exchange_trade"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange_trade_id: Mapped[str] = mapped_column(String(128), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    offset: Mapped[str] = mapped_column(String(32), nullable=False)
    price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    fee_amount: Mapped[Decimal | None] = mapped_column(DECIMAL)
    fee_currency: Mapped[str | None] = mapped_column(String(16))
    fee_source: Mapped[str | None] = mapped_column(String(32))
    trade_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trading_day: Mapped[date | None] = mapped_column(Date)
    source_exchange_report_id: Mapped[str | None] = mapped_column(String(128))
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="trades")


class Position(Base, TimestampMixin):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "instrument_id",
            name="uq_positions_account_inst",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    long_today_qty: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))
    long_yesterday_qty: Mapped[Decimal] = mapped_column(
        DECIMAL,
        nullable=False,
        default=Decimal("0"),
    )
    short_today_qty: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))
    short_yesterday_qty: Mapped[Decimal] = mapped_column(
        DECIMAL,
        nullable=False,
        default=Decimal("0"),
    )
    frozen_long_qty: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))
    frozen_short_qty: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))
    long_avg_price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))
    short_avg_price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))
    settlement_price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))
    last_price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))
    margin_used: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False, default=Decimal("0"))


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    equity: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    available_cash: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    margin_used: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    frozen_margin: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SettlementSnapshot(Base):
    __tablename__ = "settlement_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cash_before: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    cash_after: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    positions_before: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    positions_after: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    settlement_prices: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512))
    signal_id: Mapped[str | None] = mapped_column(String(128), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
