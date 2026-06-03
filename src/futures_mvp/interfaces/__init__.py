"""Abstract module interfaces for the futures MVP skeleton."""

from futures_mvp.interfaces.repositories import (
    DuplicateClientOrderError,
    EventAlreadyExistsError,
    IdempotencyConflictError,
    OptimisticLockError,
    OrderEventRepository,
    OrderNotFoundError,
    OrderRepository,
    RepositoryError,
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
    "RepositoryError",
    "UnitOfWork",
]
