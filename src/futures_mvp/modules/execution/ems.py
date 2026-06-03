from __future__ import annotations

from typing import TYPE_CHECKING

from futures_mvp.domain.models import OrderState

if TYPE_CHECKING:
    from futures_mvp.interfaces.engines import ExchangeCommandPort


class ExecutionManagementSystem:
    def __init__(self, exchange: ExchangeCommandPort) -> None:
        self._exchange = exchange

    def submit(self, order: OrderState) -> None:
        self._exchange.submit_limit_order(order)

    def cancel(self, order: OrderState) -> None:
        self._exchange.cancel_order(order)
