from decimal import Decimal

from futures_mvp.domain.enums import Direction, Offset, OrderStatus, OrderType
from futures_mvp.domain.models import OrderRequest, OrderState
from futures_mvp.modules.oms_bridge.protocols import OMSOrderCreator, OMSOrderLookup


class FakeOMSAdapter:
    def __init__(self) -> None:
        self.orders: dict[str, OrderState] = {}

    def create_order(self, request: OrderRequest, *, client_order_id: str) -> OrderState:
        order = OrderState(
            order_id=str(len(self.orders) + 1),
            request=request,
            status=OrderStatus.CREATED,
        )
        self.orders[client_order_id] = order
        return order

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None:
        return self.orders.get(client_order_id)


def _request() -> OrderRequest:
    return OrderRequest(
        client_order_id="client-1",
        account_id="account-1",
        instrument_id="au2606",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("500"),
        quantity=Decimal("2"),
    )


def test_oms_bridge_protocols_can_be_implemented_by_fake_adapter() -> None:
    adapter = FakeOMSAdapter()
    creator: OMSOrderCreator = adapter
    lookup: OMSOrderLookup = adapter

    order = creator.create_order(_request(), client_order_id="client-1")

    assert lookup.get_by_client_order_id("client-1") == order
