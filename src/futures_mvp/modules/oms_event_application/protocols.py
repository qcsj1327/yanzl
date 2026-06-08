from typing import Protocol, runtime_checkable

from futures_mvp.domain.enums import EventSource
from futures_mvp.domain.models import OrderEvent, OrderEventApplicationResult


@runtime_checkable
class OMSOrderEventApplier(Protocol):
    def apply_order_event(self, event: OrderEvent) -> OrderEventApplicationResult: ...


@runtime_checkable
class OMSOrderEventLookup(Protocol):
    def get_by_event_key(
        self,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None: ...
