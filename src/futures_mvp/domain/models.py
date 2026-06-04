from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from futures_mvp.domain.decimal import require_decimal
from futures_mvp.domain.enums import (
    Direction,
    EventApplicationStatus,
    EventSource,
    Offset,
    OrderStatus,
    OrderType,
    PositionManagerResultStatus,
    RiskDecision,
)


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def require_positive_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return value


class Signal(DomainModel):
    signal_id: str
    account_id: str
    instrument_id: str
    exchange: str
    direction: Direction
    offset: Offset
    limit_price: Decimal
    quantity: Decimal
    created_at: datetime

    @field_validator("limit_price", "quantity", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)


class OrderRequest(DomainModel):
    client_order_id: str
    account_id: str
    instrument_id: str
    exchange: str
    direction: Direction
    offset: Offset
    order_type: OrderType = OrderType.LIMIT
    limit_price: Decimal
    quantity: Decimal

    @field_validator("limit_price", "quantity", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)


class OrderState(DomainModel):
    order_id: str
    request: OrderRequest
    status: OrderStatus = OrderStatus.CREATED
    filled_quantity: Decimal = Field(default=Decimal("0"))
    reject_reason: str | None = None
    version: int = 0

    @field_validator("filled_quantity", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)


class RiskResult(DomainModel):
    decision: RiskDecision
    rule_name: str
    reason: str | None = None


class OrderEvent(DomainModel):
    order_id: str
    previous_status: OrderStatus | None
    new_status: OrderStatus
    event_source: EventSource
    external_event_id: str
    raw_payload: dict[str, Any]
    occurred_at: datetime


class OrderEventApplicationResult(DomainModel):
    status: EventApplicationStatus
    order: OrderState
    reason: str | None = None


class FillEvent(DomainModel):
    id: str | None = None
    order_id: str
    account_id: str
    exchange: str
    instrument_id: str
    exchange_report_id: str
    exchange_trade_id: str
    fill_id: str | None = None
    direction: Direction
    offset: Offset
    price: Decimal
    quantity: Decimal
    fee_amount: Decimal | None = None
    fee_currency: str | None = None
    fee_source: str | None = None
    traded_at: datetime
    trading_day: date | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("price", "quantity", "fee_amount", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="quantity")

    @model_validator(mode="after")
    def _fee_currency_required_when_fee_known(self) -> "FillEvent":
        if self.fee_amount is not None and self.fee_currency is None:
            raise ValueError("fee_currency is required when fee_amount is not None")
        if self.fee_amount is None and self.fee_currency is not None:
            raise ValueError("fee_currency requires fee_amount")
        return self


class Trade(DomainModel):
    id: str | None = None
    account_id: str
    exchange: str
    exchange_trade_id: str
    order_id: str
    instrument_id: str
    direction: Direction
    offset: Offset
    price: Decimal
    quantity: Decimal
    fee_amount: Decimal | None = None
    fee_currency: str | None = None
    fee_source: str | None = None
    trade_time: datetime
    trading_day: date | None = None
    source_exchange_report_id: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("price", "quantity", "fee_amount", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="quantity")

    @model_validator(mode="after")
    def _fee_currency_required_when_fee_known(self) -> "Trade":
        if self.fee_amount is not None and self.fee_currency is None:
            raise ValueError("fee_currency is required when fee_amount is not None")
        if self.fee_amount is None and self.fee_currency is not None:
            raise ValueError("fee_currency requires fee_amount")
        return self


class Position(DomainModel):
    id: str | None = None
    account_id: str
    instrument_id: str
    long_today_qty: Decimal = Decimal("0")
    long_yesterday_qty: Decimal = Decimal("0")
    short_today_qty: Decimal = Decimal("0")
    short_yesterday_qty: Decimal = Decimal("0")
    frozen_long_qty: Decimal = Decimal("0")
    frozen_short_qty: Decimal = Decimal("0")
    long_avg_price: Decimal = Decimal("0")
    short_avg_price: Decimal = Decimal("0")
    settlement_price: Decimal = Decimal("0")
    last_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    margin_used: Decimal = Decimal("0")
    version: int = 0
    updated_at: datetime | None = None

    @field_validator(
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
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)


class PositionSnapshot(DomainModel):
    account_id: str
    instrument_id: str
    long_today_qty: Decimal
    long_yesterday_qty: Decimal
    short_today_qty: Decimal
    short_yesterday_qty: Decimal
    long_avg_price: Decimal
    short_avg_price: Decimal
    version: int

    @field_validator(
        "long_today_qty",
        "long_yesterday_qty",
        "short_today_qty",
        "short_yesterday_qty",
        "long_avg_price",
        "short_avg_price",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @classmethod
    def from_position(cls, position: Position) -> "PositionSnapshot":
        return cls(
            account_id=position.account_id,
            instrument_id=position.instrument_id,
            long_today_qty=position.long_today_qty,
            long_yesterday_qty=position.long_yesterday_qty,
            short_today_qty=position.short_today_qty,
            short_yesterday_qty=position.short_yesterday_qty,
            long_avg_price=position.long_avg_price,
            short_avg_price=position.short_avg_price,
            version=position.version,
        )


class PositionEvent(DomainModel):
    id: str | None = None
    account_id: str
    instrument_id: str
    exchange: str
    exchange_trade_id: str
    trade_id: str
    position_id: str
    event_type: str
    direction: Direction
    offset: Offset
    price: Decimal
    quantity: Decimal
    before_snapshot: PositionSnapshot
    after_snapshot: PositionSnapshot
    occurred_at: datetime
    created_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="quantity")


class PositionManagerResult(DomainModel):
    status: PositionManagerResultStatus
    position: Position | None = None
    position_event: PositionEvent | None = None
    reason: str | None = None
    trade_id: str | None = None
    account_id: str | None = None
    instrument_id: str | None = None


class TradingCalendar(DomainModel):
    exchange: str
    trading_day: date
    is_trading_day: bool
    night_session_trading_day: date | None = None
    note: str | None = None


class TradingSession(DomainModel):
    exchange: str
    product_id: str | None = None
    instrument_id: str | None = None
    session_name: str
    start_time: str
    end_time: str
    is_night: bool = False
    effective_from: date | None = None
    effective_to: date | None = None
