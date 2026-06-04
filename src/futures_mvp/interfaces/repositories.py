from types import TracebackType
from typing import Protocol, runtime_checkable

from futures_mvp.domain.enums import EventSource, OrderStatus
from futures_mvp.domain.errors import FuturesMvpError
from futures_mvp.domain.models import OrderEvent, OrderRequest, OrderState, Trade


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
class UnitOfWork(Protocol):
    orders: OrderRepository
    order_events: OrderEventRepository
    trades: TradeRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...
