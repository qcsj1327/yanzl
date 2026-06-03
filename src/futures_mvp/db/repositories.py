from collections.abc import Iterable
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from futures_mvp.db.models import Order
from futures_mvp.db.models import OrderEvent as OrderEventOrm
from futures_mvp.domain.enums import Direction, EventSource, Offset, OrderStatus, OrderType
from futures_mvp.domain.models import OrderEvent, OrderRequest, OrderState
from futures_mvp.interfaces.repositories import (
    EventAlreadyExistsError,
    IdempotencyConflictError,
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
        version=order.version,
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


def _canonical_order_payload_from_request(order_request: OrderRequest) -> tuple[object, ...]:
    return (
        order_request.account_id,
        order_request.instrument_id,
        order_request.exchange,
        order_request.direction.value,
        order_request.offset.value,
        order_request.order_type.value,
        order_request.limit_price,
        order_request.quantity,
    )


def _canonical_order_payload_from_orm(order: Order) -> tuple[object, ...]:
    return (
        order.account_id,
        order.instrument_id,
        order.exchange,
        order.direction,
        order.offset,
        order.order_type,
        order.limit_price,
        order.quantity,
    )


def _same_canonical_order_payload(order: Order, order_request: OrderRequest) -> bool:
    return _canonical_order_payload_from_orm(order) == _canonical_order_payload_from_request(
        order_request
    )


class SQLAlchemyOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_order(self, order_request: OrderRequest, *, client_order_id: str) -> OrderState:
        existing = self._get_orm_by_client_order_id(client_order_id)
        if existing is not None:
            return self._existing_order_for_create(existing, order_request)

        try:
            with self._session.begin_nested():
                order = self._new_order(order_request, client_order_id=client_order_id)
                self._session.add(order)
                self._session.flush()
            return order_to_domain(order)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_client_order_id(client_order_id)
            if existing_after_conflict is None:
                raise RepositoryError(
                    f"client_order_id unique conflict but order not found: {client_order_id}"
                ) from exc
            return self._existing_order_for_create(existing_after_conflict, order_request)

    def _new_order(self, order_request: OrderRequest, *, client_order_id: str) -> Order:
        return Order(
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

    def _existing_order_for_create(
        self, existing: Order, order_request: OrderRequest
    ) -> OrderState:
        if not _same_canonical_order_payload(existing, order_request):
            raise IdempotencyConflictError(
                f"client_order_id reused with different canonical payload: "
                f"{existing.client_order_id}"
            )
        return order_to_domain(existing)

    def _get_orm_by_client_order_id(self, client_order_id: str) -> Order | None:
        return self._session.scalar(
            select(Order).where(Order.client_order_id == client_order_id)
        )

    def get_by_id(self, order_id: str) -> OrderState | None:
        db_order_id = parse_order_id(order_id)
        order = self._session.get(Order, db_order_id)
        return order_to_domain(order) if order else None

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None:
        order = self._get_orm_by_client_order_id(client_order_id)
        return order_to_domain(order) if order else None

    def update_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        *,
        expected_version: int | None = None,
    ) -> OrderState:
        db_order_id = parse_order_id(order_id)
        conditions = [Order.id == db_order_id]
        if expected_version is not None:
            conditions.append(Order.version == expected_version)

        result = cast(
            CursorResult[object],
            self._session.execute(
                update(Order)
                .where(*conditions)
                .values(status=new_status.value, version=Order.version + 1)
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            if expected_version is None:
                raise OrderNotFoundError(f"order not found: {order_id}")
            raise OptimisticLockError(
                f"order {order_id} version mismatch: expected {expected_version}"
            )
        self._session.flush()
        order = self._get_orm_by_id(db_order_id)
        if order is None:
            raise RepositoryError(f"order updated but not found: {order_id}")
        return order_to_domain(order)

    def _get_orm_by_id(self, db_order_id: int) -> Order | None:
        return self._session.scalar(
            select(Order)
            .where(Order.id == db_order_id)
            .execution_options(populate_existing=True)
        )

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
        try:
            with self._session.begin_nested():
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
        except IntegrityError as exc:
            existing_after_conflict = self.get_by_event_key(
                event.event_source,
                event.external_event_id,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "order event unique conflict but event not found: "
                    f"{event.event_source}/{event.external_event_id}"
                ) from exc
            raise EventAlreadyExistsError(
                f"order event already exists: {event.event_source}/{event.external_event_id}"
            ) from exc

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
