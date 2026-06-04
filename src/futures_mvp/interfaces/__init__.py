"""Abstract module interfaces for the futures MVP skeleton."""

from futures_mvp.interfaces.repositories import (
    DuplicateClientOrderError,
    EventAlreadyExistsError,
    IdempotencyConflictError,
    OptimisticLockError,
    OrderEventRepository,
    OrderNotFoundError,
    OrderRepository,
    PositionEventConflictError,
    PositionEventRepository,
    PositionRepository,
    RepositoryError,
    TradeIdempotencyConflictError,
    TradeRepository,
    UnitOfWork,
)

__all__ = [
    "DuplicateClientOrderError",
    "EventAlreadyExistsError",
    "IdempotencyConflictError",
    "OptimisticLockError",
    "OrderEventRepository",
    "OrderNotFoundError",
    "OrderRepository",
    "PositionEventConflictError",
    "PositionEventRepository",
    "PositionRepository",
    "RepositoryError",
    "TradeIdempotencyConflictError",
    "TradeRepository",
    "UnitOfWork",
]
