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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

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
    position_events: Mapped[list["PositionEvent"]] = relationship(back_populates="trade")


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
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    events: Mapped[list["PositionEvent"]] = relationship(back_populates="position")


class PositionEvent(Base):
    __tablename__ = "position_events"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "exchange",
            "exchange_trade_id",
            name="uq_position_events_account_exchange_trade",
        ),
        Index("ix_position_events_account_instrument", "account_id", "instrument_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange_trade_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"), nullable=False, index=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    offset: Mapped[str] = mapped_column(String(32), nullable=False)
    price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    before_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    after_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)

    trade: Mapped[Trade] = relationship(back_populates="position_events")
    position: Mapped[Position] = relationship(back_populates="events")


class MarginSnapshot(Base):
    __tablename__ = "margin_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "instrument_id",
            "calculation_key",
            name="uq_margin_snapshots_account_instrument_calculation",
        ),
        Index("ix_margin_snapshots_account_instrument", "account_id", "instrument_id"),
        Index(
            "ix_margin_snapshots_account_instrument_position_version",
            "account_id",
            "instrument_id",
            "position_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    position_version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    rule_id: Mapped[str | None] = mapped_column(String(128))
    rule_version: Mapped[str | None] = mapped_column(String(128))
    calculation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    long_qty: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    short_qty: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    contract_multiplier: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    initial_margin: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    maintenance_margin: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    margin_used: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    available_cash: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    equity: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PnLSnapshot(Base):
    __tablename__ = "pnl_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "instrument_id",
            "calculation_key",
            name="uq_pnl_snapshots_account_instrument_calculation",
        ),
        Index("ix_pnl_snapshots_account_instrument", "account_id", "instrument_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    position_version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    trade_id: Mapped[str | None] = mapped_column(String(128), index=True)
    margin_snapshot_id: Mapped[str | None] = mapped_column(String(128))
    calculation_key: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    price_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    mark_price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    contract_multiplier: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    total_pnl: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    fee_amount: Mapped[Decimal | None] = mapped_column(DECIMAL)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    __table_args__ = (
        UniqueConstraint("account_id", "trading_day", name="uq_settlement_account_day"),
        Index("ix_settlement_snapshots_account_day", "account_id", "trading_day"),
        Index("ix_settlement_snapshots_calculation_key", "calculation_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    calculation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512))
    cash_before: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    cash_after: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    margin_used: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    positions_before: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    positions_after: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    settlement_prices: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    pnl_snapshot_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    margin_snapshot_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    account_snapshot_before_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_snapshots.id")
    )
    account_snapshot_after_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_snapshots.id")
    )
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketTick(Base):
    __tablename__ = "market_ticks"
    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "instrument_id",
            "ts",
            "source",
            name="uq_market_ticks_identity",
        ),
        Index(
            "ix_market_ticks_exchange_instrument_day",
            "exchange",
            "instrument_id",
            "trading_day",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trade_instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    volume: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    turnover: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    open_interest: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    bid_price_1: Mapped[Decimal | None] = mapped_column(DECIMAL)
    ask_price_1: Mapped[Decimal | None] = mapped_column(DECIMAL)
    bid_volume_1: Mapped[Decimal | None] = mapped_column(DECIMAL)
    ask_volume_1: Mapped[Decimal | None] = mapped_column(DECIMAL)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MarketBar(Base):
    __tablename__ = "market_bars"
    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "instrument_id",
            "timeframe",
            "bar_ts",
            "source",
            name="uq_market_bars_identity",
        ),
        Index("ix_market_bars_exchange_instrument_day", "exchange", "instrument_id", "trading_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trade_instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    bar_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    high: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    low: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    close: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    volume: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    turnover: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    open_interest: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "instrument_id",
            "timeframe",
            "bar_ts",
            "feature_version",
            "feature_config_hash",
            name="uq_feature_snapshots_identity",
        ),
        Index(
            "ix_feature_snapshots_exchange_instrument_day",
            "exchange",
            "instrument_id",
            "trading_day",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trade_instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    bar_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    feature_version: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    feature_config_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_bar_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    returns: Mapped[Decimal | None] = mapped_column(DECIMAL)
    bar_return: Mapped[Decimal | None] = mapped_column(DECIMAL)
    price_range: Mapped[Decimal | None] = mapped_column(DECIMAL)
    range: Mapped[Decimal | None] = mapped_column(DECIMAL)
    atr: Mapped[Decimal | None] = mapped_column(DECIMAL)
    volume_ratio: Mapped[Decimal | None] = mapped_column(DECIMAL)
    moving_average: Mapped[Decimal | None] = mapped_column(DECIMAL)
    bias: Mapped[Decimal | None] = mapped_column(DECIMAL)
    breakout_level: Mapped[Decimal | None] = mapped_column(DECIMAL)
    volatility: Mapped[Decimal | None] = mapped_column(DECIMAL)
    momentum: Mapped[Decimal | None] = mapped_column(DECIMAL)
    source_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    warmup_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    missing_bar_count: Mapped[int] = mapped_column(Integer, nullable=False)
    gap_count: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SignalCandidate(Base):
    __tablename__ = "signal_candidates"
    __table_args__ = (
        UniqueConstraint("signal_id", name="uq_signal_candidates_signal_id"),
        UniqueConstraint(
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
        Index(
            "ix_signal_candidates_strategy_version",
            "strategy_name",
            "strategy_version",
        ),
        Index(
            "ix_signal_candidates_exchange_instrument_day",
            "exchange",
            "instrument_id",
            "trading_day",
        ),
        Index("ix_signal_candidates_timeframe_bar_ts", "timeframe", "bar_ts"),
        Index("ix_signal_candidates_signal_id", "signal_id"),
    )

    signal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trade_instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    bar_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    position_side: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    strength: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512))
    expected_price: Mapped[Decimal | None] = mapped_column(DECIMAL)
    stop_loss: Mapped[Decimal | None] = mapped_column(DECIMAL)
    take_profit: Mapped[Decimal | None] = mapped_column(DECIMAL)
    holding_period_hint: Mapped[str | None] = mapped_column(String(128))
    tags: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    features_ref: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SignalEvent(Base):
    __tablename__ = "signal_events"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_signal_events_event_key"),
        Index("ix_signal_events_signal_id", "signal_id"),
        Index("ix_signal_events_signal_created", "signal_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False)
    event_reason: Mapped[str | None] = mapped_column(String(512))
    event_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TradingRiskResult(Base):
    __tablename__ = "risk_results"
    __table_args__ = (
        UniqueConstraint("risk_result_id", name="uq_risk_results_risk_result_id"),
        Index("ix_risk_results_signal_id", "signal_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    risk_result_id: Mapped[str] = mapped_column(String(128), nullable=False)
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluation_context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_status: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_reason: Mapped[str | None] = mapped_column(String(512))
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_quantity: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    approved_quantity: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    max_quantity: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    expected_margin: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    expected_notional: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrderIntent(Base):
    __tablename__ = "order_intents"
    __table_args__ = (
        UniqueConstraint("intent_id", name="uq_order_intents_intent_id"),
        Index("ix_order_intents_signal_id", "signal_id"),
        Index("ix_order_intents_risk_result_id", "risk_result_id"),
        Index("ix_order_intents_instrument_id", "instrument_id"),
        Index("ix_order_intents_trading_day", "trading_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    risk_result_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trade_instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    bar_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    offset: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    tif: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_margin: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    expected_notional: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    intent_reason: Mapped[str | None] = mapped_column(String(512))
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExecutionCommand(Base):
    __tablename__ = "execution_commands"
    __table_args__ = (
        UniqueConstraint("command_id", name="uq_execution_commands_command_id"),
        Index("ix_execution_commands_order_id", "order_id"),
        Index("ix_execution_commands_client_order_id", "client_order_id"),
        Index("ix_execution_commands_execution_target", "execution_target"),
        Index("ix_execution_commands_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    command_id: Mapped[str] = mapped_column(String(128), nullable=False)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    client_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trade_instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    offset: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    price: Mapped[Decimal] = mapped_column(DECIMAL, nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    tif: Mapped[str] = mapped_column(String(16), nullable=False)
    command_type: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_target: Mapped[str] = mapped_column(String(32), nullable=False)
    command_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
