from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from futures_mvp.db.models import Order
from futures_mvp.db.models import OrderEvent as OrderEventOrm
from futures_mvp.domain.enums import Direction, EventSource, Offset, OrderStatus, OrderType
from futures_mvp.domain.models import OrderEvent, OrderRequest, OrderState
from futures_mvp.interfaces.repositories import (
    EventAlreadyExistsError,
    OptimisticLockError,
    OrderNotFoundError,
    RepositoryError,
)

OPEN_RECOVERY_STATUSES = frozenset(
    {
        OrderStatus.SUBMITTING,
        OrderStatus.SUBMIT_TIMEOUT,
        OrderStatus.SUBMITTED,
        OrderStatus.ACKED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCEL_FAILED,
        OrderStatus.UNKNOWN,
    }
)


def parse_order_id(order_id: str) -> int:
    try:
        return int(order_id)
    except ValueError as exc:
        raise RepositoryError(f"invalid order_id: {order_id}") from exc


def order_to_domain(order: Order) -> OrderState:
    request = OrderRequest(
        client_order_id=order.client_order_id,
        account_id=order.account_id,
        instrument_id=order.instrument_id,
        exchange=order.exchange,
        direction=Direction(order.direction),
        offset=Offset(order.offset),
        order_type=OrderType(order.order_type),
        limit_price=order.limit_price,
        quantity=order.quantity,
    )
    return OrderState(
        order_id=str(order.id),
        request=request,
        status=OrderStatus(order.status),
        filled_quantity=order.filled_quantity,
        reject_reason=order.reject_reason,
    )


def order_event_to_domain(event: OrderEventOrm) -> OrderEvent:
    return OrderEvent(
        order_id=str(event.order_id),
        previous_status=OrderStatus(event.previous_status) if event.previous_status else None,
        new_status=OrderStatus(event.new_status),
        event_source=EventSource(event.event_source),
        external_event_id=event.external_event_id,
        raw_payload=event.raw_payload,
        occurred_at=event.occurred_at,
    )


def _status_values(statuses: Iterable[OrderStatus]) -> list[str]:
    return [status.value for status in statuses]


class SQLAlchemyOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_order(self, order_request: OrderRequest, *, client_order_id: str) -> OrderState:
        order = Order(
            client_order_id=client_order_id,
            account_id=order_request.account_id,
            instrument_id=order_request.instrument_id,
            exchange=order_request.exchange,
            direction=order_request.direction.value,
            offset=order_request.offset.value,
            order_type=order_request.order_type.value,
            limit_price=order_request.limit_price,
            quantity=order_request.quantity,
            filled_quantity=order_request.quantity * 0,
            status=OrderStatus.CREATED.value,
            version=0,
        )
        self._session.add(order)
        self._session.flush()
        return order_to_domain(order)

    def get_by_id(self, order_id: str) -> OrderState | None:
        db_order_id = parse_order_id(order_id)
        order = self._session.get(Order, db_order_id)
        return order_to_domain(order) if order else None

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None:
        order = self._session.scalar(
            select(Order).where(Order.client_order_id == client_order_id)
        )
        return order_to_domain(order) if order else None

    def update_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        *,
        expected_version: int | None = None,
    ) -> OrderState:
        db_order_id = parse_order_id(order_id)
        order = self._session.get(Order, db_order_id)
        if order is None:
            raise OrderNotFoundError(f"order not found: {order_id}")
        if expected_version is not None and order.version != expected_version:
            raise OptimisticLockError(
                f"order {order_id} version mismatch: "
                f"expected {expected_version}, got {order.version}"
            )
        order.status = new_status.value
        order.version += 1
        self._session.flush()
        return order_to_domain(order)

    def list_open_orders(self) -> list[OrderState]:
        orders = self._session.scalars(
            select(Order).where(Order.status.in_(_status_values(OPEN_RECOVERY_STATUSES)))
        ).all()
        return [order_to_domain(order) for order in orders]


class SQLAlchemyOrderEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_event(self, event: OrderEvent) -> OrderEvent:
        existing = self.get_by_event_key(event.event_source, event.external_event_id)
        if existing is not None:
            raise EventAlreadyExistsError(
                f"order event already exists: {event.event_source}/{event.external_event_id}"
            )
        order_event = OrderEventOrm(
            order_id=parse_order_id(event.order_id),
            previous_status=event.previous_status.value if event.previous_status else None,
            new_status=event.new_status.value,
            event_source=event.event_source.value,
            external_event_id=event.external_event_id,
            raw_payload=event.raw_payload,
            occurred_at=event.occurred_at,
        )
        self._session.add(order_event)
        self._session.flush()
        return order_event_to_domain(order_event)

    def get_by_event_key(
        self,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None:
        event = self._session.scalar(
            select(OrderEventOrm).where(
                OrderEventOrm.event_source == event_source.value,
                OrderEventOrm.external_event_id == external_event_id,
            )
        )
        return order_event_to_domain(event) if event else None

    def list_by_order_id(self, order_id: str) -> list[OrderEvent]:
        db_order_id = parse_order_id(order_id)
        events = self._session.scalars(
            select(OrderEventOrm)
            .where(OrderEventOrm.order_id == db_order_id)
            .order_by(OrderEventOrm.id.asc())
        ).all()
        return [order_event_to_domain(event) for event in events]
