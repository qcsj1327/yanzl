from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from futures_mvp.domain.decimal import require_decimal
from futures_mvp.domain.enums import (
    Direction,
    EventApplicationStatus,
    EventSource,
    MarginPriceBasis,
    MarginResultStatus,
    Offset,
    OrderStatus,
    OrderType,
    PnLPriceBasis,
    PnLResultStatus,
    PositionManagerResultStatus,
    RiskDecision,
    SettlementResultStatus,
)


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def require_positive_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return value


def require_non_negative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
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


class MarginRule(DomainModel):
    rule_id: str | None = None
    instrument_id: str
    exchange: str
    contract_multiplier: Decimal
    long_initial_margin_rate: Decimal
    short_initial_margin_rate: Decimal
    long_maintenance_margin_rate: Decimal
    short_maintenance_margin_rate: Decimal
    price_basis: MarginPriceBasis
    price: Decimal | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    rule_version: str | None = None

    @field_validator(
        "contract_multiplier",
        "long_initial_margin_rate",
        "short_initial_margin_rate",
        "long_maintenance_margin_rate",
        "short_maintenance_margin_rate",
        "price",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("contract_multiplier")
    @classmethod
    def _contract_multiplier_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="contract_multiplier")

    @field_validator(
        "long_initial_margin_rate",
        "short_initial_margin_rate",
        "long_maintenance_margin_rate",
        "short_maintenance_margin_rate",
    )
    @classmethod
    def _rates_non_negative(cls, value: Decimal) -> Decimal:
        return require_non_negative_decimal(value, field_name="margin_rate")


class AccountContext(DomainModel):
    account_id: str
    equity: Decimal
    available_cash: Decimal
    frozen_cash: Decimal
    currency: str | None = None
    snapshot_time: datetime

    @field_validator("equity", "available_cash", "frozen_cash", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("available_cash")
    @classmethod
    def _available_cash_non_negative(cls, value: Decimal) -> Decimal:
        return require_non_negative_decimal(value, field_name="available_cash")


class AccountSnapshot(DomainModel):
    id: str | None = None
    account_id: str
    equity: Decimal
    available_cash: Decimal
    margin_used: Decimal
    frozen_margin: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    snapshot_time: datetime

    @field_validator(
        "equity",
        "available_cash",
        "margin_used",
        "frozen_margin",
        "realized_pnl",
        "unrealized_pnl",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("available_cash", "margin_used", "frozen_margin")
    @classmethod
    def _non_negative(cls, value: Decimal) -> Decimal:
        return require_non_negative_decimal(value, field_name="account_snapshot_value")


class MarginRequirement(DomainModel):
    account_id: str
    instrument_id: str
    long_initial_margin: Decimal
    short_initial_margin: Decimal
    total_initial_margin: Decimal
    long_maintenance_margin: Decimal
    short_maintenance_margin: Decimal
    total_maintenance_margin: Decimal
    margin_used: Decimal
    required_cash: Decimal
    is_sufficient: bool
    reason: str | None = None

    @field_validator(
        "long_initial_margin",
        "short_initial_margin",
        "total_initial_margin",
        "long_maintenance_margin",
        "short_maintenance_margin",
        "total_maintenance_margin",
        "margin_used",
        "required_cash",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)


class MarginSnapshot(DomainModel):
    id: str | None = None
    account_id: str
    instrument_id: str
    position_version: int
    rule_id: str | None = None
    rule_version: str | None = None
    calculation_key: str
    long_qty: Decimal
    short_qty: Decimal
    price: Decimal
    contract_multiplier: Decimal
    initial_margin: Decimal
    maintenance_margin: Decimal
    margin_used: Decimal
    available_cash: Decimal
    equity: Decimal
    calculated_at: datetime

    @field_validator(
        "long_qty",
        "short_qty",
        "price",
        "contract_multiplier",
        "initial_margin",
        "maintenance_margin",
        "margin_used",
        "available_cash",
        "equity",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("calculation_key")
    @classmethod
    def _calculation_key_required(cls, value: str) -> str:
        if not value:
            raise ValueError("calculation_key is required")
        return value


class MarginResult(DomainModel):
    status: MarginResultStatus
    requirement: MarginRequirement | None = None
    snapshot: MarginSnapshot | None = None
    reason: str | None = None
    account_id: str | None = None
    instrument_id: str | None = None


class CloseTradeContext(DomainModel):
    account_id: str
    instrument_id: str
    position_version: int
    avg_cost: Decimal
    available_qty: Decimal
    contract_multiplier: Decimal
    context_time: datetime | None = None

    @field_validator("avg_cost", "available_qty", "contract_multiplier", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("avg_cost", "available_qty")
    @classmethod
    def _non_negative(cls, value: Decimal) -> Decimal:
        return require_non_negative_decimal(value, field_name="pnl_context_value")

    @field_validator("contract_multiplier")
    @classmethod
    def _contract_multiplier_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="contract_multiplier")


class RealizedPnL(DomainModel):
    account_id: str
    instrument_id: str
    trade_id: str
    direction: Direction
    offset: Offset
    quantity: Decimal
    close_price: Decimal
    avg_cost: Decimal
    contract_multiplier: Decimal
    gross_realized_pnl: Decimal
    fee_amount: Decimal | None = None
    net_realized_pnl: Decimal | None = None
    currency: str | None = None
    calculated_at: datetime

    @field_validator(
        "quantity",
        "close_price",
        "avg_cost",
        "contract_multiplier",
        "gross_realized_pnl",
        "fee_amount",
        "net_realized_pnl",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("quantity", "contract_multiplier")
    @classmethod
    def _positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="pnl_positive_value")


class UnrealizedPnL(DomainModel):
    account_id: str
    instrument_id: str
    long_qty: Decimal
    short_qty: Decimal
    long_avg_price: Decimal
    short_avg_price: Decimal
    price_basis: PnLPriceBasis
    mark_price: Decimal
    contract_multiplier: Decimal
    gross_unrealized_pnl: Decimal
    net_unrealized_pnl: Decimal

    @field_validator(
        "long_qty",
        "short_qty",
        "long_avg_price",
        "short_avg_price",
        "mark_price",
        "contract_multiplier",
        "gross_unrealized_pnl",
        "net_unrealized_pnl",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("contract_multiplier")
    @classmethod
    def _contract_multiplier_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="contract_multiplier")


class PnLSnapshot(DomainModel):
    id: str | None = None
    account_id: str
    instrument_id: str
    position_version: int
    trade_id: str | None = None
    margin_snapshot_id: str | None = None
    calculation_key: str
    price_basis: PnLPriceBasis
    mark_price: Decimal
    contract_multiplier: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    fee_amount: Decimal | None = None
    calculated_at: datetime

    @field_validator(
        "mark_price",
        "contract_multiplier",
        "realized_pnl",
        "unrealized_pnl",
        "total_pnl",
        "fee_amount",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("contract_multiplier")
    @classmethod
    def _contract_multiplier_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="contract_multiplier")

    @field_validator("calculation_key")
    @classmethod
    def _calculation_key_required(cls, value: str) -> str:
        if not value:
            raise ValueError("calculation_key is required")
        return value


class PnLResult(DomainModel):
    status: PnLResultStatus
    realized: RealizedPnL | None = None
    unrealized: UnrealizedPnL | None = None
    snapshot: PnLSnapshot | None = None
    reason: str | None = None
    account_id: str | None = None
    instrument_id: str | None = None


class SettlementPrice(DomainModel):
    instrument_id: str
    exchange: str
    trading_day: date
    price: Decimal
    source: str | None = None
    received_at: datetime

    @field_validator("price", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("price")
    @classmethod
    def _price_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="settlement_price")


class SettlementContext(DomainModel):
    account_id: str
    trading_day: date
    account_before: AccountContext | AccountSnapshot
    positions: tuple[Position, ...]
    pnl_snapshots: tuple[PnLSnapshot, ...]
    margin_snapshots: tuple[MarginSnapshot, ...]
    settlement_prices: tuple[SettlementPrice, ...]
    calculation_key: str
    settled_at: datetime

    @field_validator("calculation_key")
    @classmethod
    def _calculation_key_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("calculation_key is required")
        return value

    @model_validator(mode="after")
    def _account_identity_matches(self) -> "SettlementContext":
        if self.account_before.account_id != self.account_id:
            raise ValueError("account_before.account_id must match account_id")
        return self


class SettlementSnapshot(DomainModel):
    id: str | None = None
    account_id: str
    trading_day: date
    calculation_key: str
    positions_before: tuple[dict[str, Any], ...]
    positions_after: tuple[dict[str, Any], ...]
    settlement_prices: tuple[dict[str, Any], ...]
    pnl_snapshot_ids: tuple[str, ...]
    margin_snapshot_ids: tuple[str, ...]
    account_snapshot_before_id: str | None = None
    account_snapshot_after_id: str | None = None
    cash_before: Decimal
    cash_after: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    margin_used: Decimal
    status: SettlementResultStatus
    reason: str | None = None
    created_at: datetime

    @field_validator(
        "cash_before",
        "cash_after",
        "realized_pnl",
        "unrealized_pnl",
        "margin_used",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("margin_used")
    @classmethod
    def _margin_used_non_negative(cls, value: Decimal) -> Decimal:
        return require_non_negative_decimal(value, field_name="margin_used")

    @field_validator("calculation_key")
    @classmethod
    def _snapshot_calculation_key_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("calculation_key is required")
        return value


class SettlementResult(DomainModel):
    status: SettlementResultStatus
    snapshot: SettlementSnapshot | None = None
    reason: str | None = None
    account_id: str | None = None
    trading_day: date | None = None


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
