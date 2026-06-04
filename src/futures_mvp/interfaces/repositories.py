from datetime import date
from decimal import Decimal
from types import TracebackType
from typing import Protocol, runtime_checkable

from futures_mvp.domain.enums import EventSource, OrderStatus
from futures_mvp.domain.errors import FuturesMvpError
from futures_mvp.domain.models import (
    AccountSnapshot,
    MarginSnapshot,
    OrderEvent,
    OrderRequest,
    OrderState,
    PnLSnapshot,
    Position,
    PositionEvent,
    SettlementSnapshot,
    Trade,
)


class RepositoryError(FuturesMvpError):
    """Base error for repository port failures."""


class OrderNotFoundError(RepositoryError):
    """Raised when an order cannot be found by the requested identity."""


class DuplicateClientOrderError(RepositoryError):
    """Raised when a client_order_id already exists."""


class IdempotencyConflictError(DuplicateClientOrderError):
    """Raised when a client_order_id is reused with a different canonical payload."""


class EventAlreadyExistsError(RepositoryError):
    """Raised when an order event idempotency key already exists."""


class OptimisticLockError(RepositoryError):
    """Raised when an order version check fails during persistence."""


class TradeIdempotencyConflictError(RepositoryError):
    """Raised when an exchange trade id is reused with different trade facts."""


class PositionEventConflictError(RepositoryError):
    """Raised when an exchange trade id is reused with different position facts."""


class MarginSnapshotConflictError(RepositoryError):
    """Raised when a margin snapshot identity is reused with different facts."""


class PnLSnapshotConflictError(RepositoryError):
    """Raised when a PnL calculation key is reused with different facts."""


class SettlementSnapshotConflictError(RepositoryError):
    """Raised when a settlement account/day is reused with different facts."""


@runtime_checkable
class OrderRepository(Protocol):
    def create_order(self, order_request: OrderRequest, *, client_order_id: str) -> OrderState: ...

    def get_by_id(self, order_id: str) -> OrderState | None: ...

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None: ...

    def update_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        *,
        expected_version: int | None = None,
    ) -> OrderState: ...

    def list_open_orders(self) -> list[OrderState]: ...


@runtime_checkable
class OrderEventRepository(Protocol):
    def append_event(self, event: OrderEvent) -> OrderEvent: ...

    def get_by_event_key(
        self,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None: ...

    def list_by_order_id(self, order_id: str) -> list[OrderEvent]: ...


@runtime_checkable
class TradeRepository(Protocol):
    def create_or_get_trade(self, trade: Trade) -> Trade: ...

    def get_by_exchange_trade_id(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None: ...


@runtime_checkable
class PositionRepository(Protocol):
    def get_by_account_instrument(
        self,
        account_id: str,
        instrument_id: str,
    ) -> Position | None: ...

    def create_or_get_position(self, account_id: str, instrument_id: str) -> Position: ...

    def update_position(
        self,
        position: Position,
        *,
        expected_version: int | None = None,
    ) -> Position: ...

    def update_margin_used(
        self,
        account_id: str,
        instrument_id: str,
        margin_used: Decimal,
        *,
        expected_version: int | None = None,
    ) -> Position: ...

    def update_pnl(
        self,
        account_id: str,
        instrument_id: str,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal,
        *,
        expected_version: int | None = None,
    ) -> Position: ...

    def roll_today_to_yesterday_for_settlement(
        self,
        account_id: str,
        instrument_id: str,
        *,
        expected_version: int,
    ) -> Position: ...

    def list_by_account(self, account_id: str) -> list[Position]: ...


@runtime_checkable
class PositionEventRepository(Protocol):
    def append_position_event(self, event: PositionEvent) -> PositionEvent: ...

    def get_by_trade_key(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> PositionEvent | None: ...

    def list_by_position(self, account_id: str, instrument_id: str) -> list[PositionEvent]: ...

    def list_by_account(self, account_id: str) -> list[PositionEvent]: ...


@runtime_checkable
class MarginSnapshotRepository(Protocol):
    def append_margin_snapshot(self, snapshot: MarginSnapshot) -> MarginSnapshot: ...

    def get_latest(self, account_id: str, instrument_id: str) -> MarginSnapshot | None: ...

    def list_by_account(self, account_id: str) -> list[MarginSnapshot]: ...

    def get_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> MarginSnapshot | None: ...


@runtime_checkable
class PnLSnapshotRepository(Protocol):
    def append_pnl_snapshot(self, snapshot: PnLSnapshot) -> PnLSnapshot: ...

    def get_latest(self, account_id: str, instrument_id: str) -> PnLSnapshot | None: ...

    def list_by_account(self, account_id: str) -> list[PnLSnapshot]: ...

    def get_by_calculation_key(
        self,
        account_id: str,
        instrument_id: str,
        calculation_key: str,
    ) -> PnLSnapshot | None: ...

    def get_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> PnLSnapshot | None: ...


@runtime_checkable
class AccountSnapshotRepository(Protocol):
    def append_account_snapshot(self, snapshot: AccountSnapshot) -> AccountSnapshot: ...

    def get_by_id(self, snapshot_id: str) -> AccountSnapshot | None: ...

    def get_latest(self, account_id: str) -> AccountSnapshot | None: ...

    def list_by_account(self, account_id: str) -> list[AccountSnapshot]: ...


@runtime_checkable
class SettlementSnapshotRepository(Protocol):
    def append_settlement_snapshot(self, snapshot: SettlementSnapshot) -> SettlementSnapshot: ...

    def get_by_account_trading_day(
        self,
        account_id: str,
        trading_day: date,
    ) -> SettlementSnapshot | None: ...

    def get_by_calculation_key(
        self,
        account_id: str,
        trading_day: date,
        calculation_key: str,
    ) -> SettlementSnapshot | None: ...

    def list_by_account(self, account_id: str) -> list[SettlementSnapshot]: ...

    def list_by_trading_day(self, trading_day: date) -> list[SettlementSnapshot]: ...


@runtime_checkable
class UnitOfWork(Protocol):
    orders: OrderRepository
    order_events: OrderEventRepository
    trades: TradeRepository
    positions: PositionRepository
    position_events: PositionEventRepository
    margin_snapshots: MarginSnapshotRepository
    pnl_snapshots: PnLSnapshotRepository
    account_snapshots: AccountSnapshotRepository
    settlement_snapshots: SettlementSnapshotRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...
