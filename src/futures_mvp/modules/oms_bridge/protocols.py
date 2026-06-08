from typing import Protocol

from futures_mvp.domain.models import OrderRequest, OrderState


class OMSOrderCreator(Protocol):
    def create_order(self, request: OrderRequest, *, client_order_id: str) -> OrderState: ...


class OMSOrderLookup(Protocol):
    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None: ...
