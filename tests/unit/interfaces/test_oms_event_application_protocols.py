from datetime import UTC, datetime
from decimal import Decimal

from futures_mvp.domain.enums import (
    Direction,
    EventApplicationStatus,
    EventSource,
    Offset,
    OrderStatus,
    OrderType,
)
from futures_mvp.domain.models import (
    OrderEvent,
    OrderEventApplicationResult,
    OrderRequest,
    OrderState,
)
from futures_mvp.modules.oms_event_application import OMSOrderEventApplier, OMSOrderEventLookup

NOW = datetime(2026, 6, 8, 9, tzinfo=UTC)


class FakeOMSOrderEventApplier:
    def apply_order_event(self, event: OrderEvent) -> OrderEventApplicationResult:
        return OrderEventApplicationResult(
            status=EventApplicationStatus.APPLIED,
            order=OrderState(
                order_id=event.order_id,
                request=OrderRequest(
                    client_order_id="client-1",
                    account_id="acct-1",
                    instrument_id="IF2606",
                    exchange="CFFEX",
                    direction=Direction.BUY,
                    offset=Offset.OPEN,
                    order_type=OrderType.LIMIT,
                    limit_price=Decimal("500"),
                    quantity=Decimal("1"),
                ),
                status=event.new_status,
            ),
        )


class FakeOMSOrderEventLookup:
    def __init__(self, event: OrderEvent | None = None) -> None:
        self.event = event

    def get_by_event_key(
        self,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None:
        if (
            self.event is not None
            and self.event.event_source is event_source
            and self.event.external_event_id == external_event_id
        ):
            return self.event
        return None


def test_oms_order_event_applier_protocol() -> None:
    applier = FakeOMSOrderEventApplier()

    assert isinstance(applier, OMSOrderEventApplier)
    result = applier.apply_order_event(
        OrderEvent(
            order_id="order-1",
            previous_status=OrderStatus.SUBMITTED,
            new_status=OrderStatus.ACKED,
            event_source=EventSource.EXECUTION_REPORT_NORMALIZER,
            external_event_id="oe-1",
            raw_payload={},
            occurred_at=NOW,
        )
    )
    assert result.status is EventApplicationStatus.APPLIED


def test_oms_order_event_lookup_protocol() -> None:
    event = OrderEvent(
        order_id="order-1",
        previous_status=OrderStatus.SUBMITTED,
        new_status=OrderStatus.ACKED,
        event_source=EventSource.EXECUTION_REPORT_NORMALIZER,
        external_event_id="oe-1",
        raw_payload={},
        occurred_at=NOW,
    )
    lookup = FakeOMSOrderEventLookup(event)

    assert isinstance(lookup, OMSOrderEventLookup)
    assert lookup.get_by_event_key(EventSource.EXECUTION_REPORT_NORMALIZER, "oe-1") == event
