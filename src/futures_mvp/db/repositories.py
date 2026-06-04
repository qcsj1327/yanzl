from collections.abc import Iterable
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from futures_mvp.db.models import Order
from futures_mvp.db.models import OrderEvent as OrderEventOrm
from futures_mvp.db.models import Position as PositionOrm
from futures_mvp.db.models import PositionEvent as PositionEventOrm
from futures_mvp.db.models import Trade as TradeOrm
from futures_mvp.domain.enums import Direction, EventSource, Offset, OrderStatus, OrderType
from futures_mvp.domain.models import (
    OrderEvent,
    OrderRequest,
    OrderState,
    Position,
    PositionEvent,
    PositionSnapshot,
    Trade,
)
from futures_mvp.interfaces.repositories import (
    EventAlreadyExistsError,
    IdempotencyConflictError,
    OptimisticLockError,
    OrderNotFoundError,
    PositionEventConflictError,
    RepositoryError,
    TradeIdempotencyConflictError,
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


def trade_to_domain(trade: TradeOrm) -> Trade:
    return Trade(
        id=str(trade.id),
        account_id=trade.account_id,
        exchange=trade.exchange,
        exchange_trade_id=trade.exchange_trade_id,
        order_id=str(trade.order_id),
        instrument_id=trade.instrument_id,
        direction=Direction(trade.direction),
        offset=Offset(trade.offset),
        price=trade.price,
        quantity=trade.quantity,
        fee_amount=trade.fee_amount,
        fee_currency=trade.fee_currency,
        fee_source=trade.fee_source,
        trade_time=trade.trade_time,
        trading_day=trade.trading_day,
        source_exchange_report_id=trade.source_exchange_report_id,
        raw_payload=trade.raw_payload or {},
    )


def position_to_domain(position: PositionOrm) -> Position:
    return Position(
        id=str(position.id),
        account_id=position.account_id,
        instrument_id=position.instrument_id,
        long_today_qty=position.long_today_qty,
        long_yesterday_qty=position.long_yesterday_qty,
        short_today_qty=position.short_today_qty,
        short_yesterday_qty=position.short_yesterday_qty,
        frozen_long_qty=position.frozen_long_qty,
        frozen_short_qty=position.frozen_short_qty,
        long_avg_price=position.long_avg_price,
        short_avg_price=position.short_avg_price,
        settlement_price=position.settlement_price,
        last_price=position.last_price,
        realized_pnl=position.realized_pnl,
        unrealized_pnl=position.unrealized_pnl,
        margin_used=position.margin_used,
        version=position.version,
        updated_at=position.updated_at,
    )


def position_event_to_domain(event: PositionEventOrm) -> PositionEvent:
    return PositionEvent(
        id=str(event.id),
        account_id=event.account_id,
        instrument_id=event.instrument_id,
        exchange=event.exchange,
        exchange_trade_id=event.exchange_trade_id,
        trade_id=str(event.trade_id),
        position_id=str(event.position_id),
        event_type=event.event_type,
        direction=Direction(event.direction),
        offset=Offset(event.offset),
        price=event.price,
        quantity=event.quantity,
        before_snapshot=PositionSnapshot.model_validate(event.before_snapshot),
        after_snapshot=PositionSnapshot.model_validate(event.after_snapshot),
        occurred_at=event.occurred_at,
        created_at=event.created_at,
        raw_payload=event.raw_payload or {},
    )


def _snapshot_to_json(snapshot: PositionSnapshot) -> dict[str, object]:
    return cast(dict[str, object], snapshot.model_dump(mode="json"))


def _canonical_snapshot_payload(
    snapshot: PositionSnapshot | dict[str, object],
) -> tuple[object, ...]:
    typed_snapshot = (
        snapshot
        if isinstance(snapshot, PositionSnapshot)
        else PositionSnapshot.model_validate(snapshot)
    )
    return tuple(sorted(typed_snapshot.model_dump(mode="json").items()))


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


def _canonical_trade_payload_from_domain(trade: Trade) -> tuple[object, ...]:
    return (
        trade.account_id,
        trade.exchange,
        trade.exchange_trade_id,
        trade.order_id,
        trade.instrument_id,
        trade.direction.value,
        trade.offset.value,
        trade.price,
        trade.quantity,
        trade.fee_amount,
        trade.fee_currency,
        trade.fee_source,
        trade.trade_time,
        trade.trading_day,
        trade.source_exchange_report_id,
    )


def _canonical_trade_payload_from_orm(trade: TradeOrm) -> tuple[object, ...]:
    return (
        trade.account_id,
        trade.exchange,
        trade.exchange_trade_id,
        str(trade.order_id),
        trade.instrument_id,
        trade.direction,
        trade.offset,
        trade.price,
        trade.quantity,
        trade.fee_amount,
        trade.fee_currency,
        trade.fee_source,
        trade.trade_time,
        trade.trading_day,
        trade.source_exchange_report_id,
    )


def _same_canonical_trade_payload(existing: TradeOrm, trade: Trade) -> bool:
    return _canonical_trade_payload_from_orm(existing) == _canonical_trade_payload_from_domain(
        trade
    )


def _canonical_position_event_payload_from_domain(event: PositionEvent) -> tuple[object, ...]:
    return (
        event.account_id,
        event.instrument_id,
        event.exchange,
        event.exchange_trade_id,
        event.trade_id,
        event.position_id,
        event.event_type,
        event.direction.value,
        event.offset.value,
        event.price,
        event.quantity,
        _canonical_snapshot_payload(event.before_snapshot),
        _canonical_snapshot_payload(event.after_snapshot),
        event.occurred_at,
    )


def _canonical_position_event_payload_from_orm(event: PositionEventOrm) -> tuple[object, ...]:
    return (
        event.account_id,
        event.instrument_id,
        event.exchange,
        event.exchange_trade_id,
        str(event.trade_id),
        str(event.position_id),
        event.event_type,
        event.direction,
        event.offset,
        event.price,
        event.quantity,
        _canonical_snapshot_payload(event.before_snapshot),
        _canonical_snapshot_payload(event.after_snapshot),
        event.occurred_at,
    )


def _same_canonical_position_event_payload(
    existing: PositionEventOrm,
    event: PositionEvent,
) -> bool:
    return _canonical_position_event_payload_from_orm(
        existing
    ) == _canonical_position_event_payload_from_domain(event)


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


class SQLAlchemyTradeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_or_get_trade(self, trade: Trade) -> Trade:
        existing = self._get_orm_by_exchange_trade_id(
            trade.account_id,
            trade.exchange,
            trade.exchange_trade_id,
        )
        if existing is not None:
            return self._existing_trade_for_create(existing, trade)

        try:
            with self._session.begin_nested():
                trade_orm = self._new_trade(trade)
                self._session.add(trade_orm)
                self._session.flush()
            return trade_to_domain(trade_orm)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_exchange_trade_id(
                trade.account_id,
                trade.exchange,
                trade.exchange_trade_id,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "trade unique conflict but trade not found: "
                    f"{trade.account_id}/{trade.exchange}/{trade.exchange_trade_id}"
                ) from exc
            return self._existing_trade_for_create(existing_after_conflict, trade)

    def get_by_exchange_trade_id(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None:
        trade = self._get_orm_by_exchange_trade_id(account_id, exchange, exchange_trade_id)
        return trade_to_domain(trade) if trade else None

    def _new_trade(self, trade: Trade) -> TradeOrm:
        return TradeOrm(
            account_id=trade.account_id,
            exchange=trade.exchange,
            exchange_trade_id=trade.exchange_trade_id,
            order_id=parse_order_id(trade.order_id),
            instrument_id=trade.instrument_id,
            direction=trade.direction.value,
            offset=trade.offset.value,
            price=trade.price,
            quantity=trade.quantity,
            fee_amount=trade.fee_amount,
            fee_currency=trade.fee_currency,
            fee_source=trade.fee_source,
            trade_time=trade.trade_time,
            trading_day=trade.trading_day,
            source_exchange_report_id=trade.source_exchange_report_id,
            raw_payload=trade.raw_payload,
        )

    def _get_orm_by_exchange_trade_id(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> TradeOrm | None:
        return self._session.scalar(
            select(TradeOrm).where(
                TradeOrm.account_id == account_id,
                TradeOrm.exchange == exchange,
                TradeOrm.exchange_trade_id == exchange_trade_id,
            )
        )

    def _existing_trade_for_create(self, existing: TradeOrm, trade: Trade) -> Trade:
        if not _same_canonical_trade_payload(existing, trade):
            raise TradeIdempotencyConflictError(
                "exchange_trade_id reused with different canonical payload: "
                f"{trade.account_id}/{trade.exchange}/{trade.exchange_trade_id}"
            )
        return trade_to_domain(existing)


class SQLAlchemyPositionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_account_instrument(
        self,
        account_id: str,
        instrument_id: str,
    ) -> Position | None:
        position = self._get_orm_by_account_instrument(account_id, instrument_id)
        return position_to_domain(position) if position else None

    def create_or_get_position(self, account_id: str, instrument_id: str) -> Position:
        existing = self._get_orm_by_account_instrument(account_id, instrument_id)
        if existing is not None:
            return position_to_domain(existing)

        try:
            with self._session.begin_nested():
                position = PositionOrm(
                    account_id=account_id,
                    instrument_id=instrument_id,
                )
                self._session.add(position)
                self._session.flush()
            return position_to_domain(position)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_account_instrument(
                account_id,
                instrument_id,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "position unique conflict but position not found: "
                    f"{account_id}/{instrument_id}"
                ) from exc
            return position_to_domain(existing_after_conflict)

    def update_position(
        self,
        position: Position,
        *,
        expected_version: int | None = None,
    ) -> Position:
        if position.id is None:
            raise RepositoryError("position.id is required for update_position")
        db_position_id = parse_order_id(position.id)
        conditions = [PositionOrm.id == db_position_id]
        if expected_version is not None:
            conditions.append(PositionOrm.version == expected_version)

        result = cast(
            CursorResult[object],
            self._session.execute(
                update(PositionOrm)
                .where(*conditions)
                .values(
                    long_today_qty=position.long_today_qty,
                    long_yesterday_qty=position.long_yesterday_qty,
                    short_today_qty=position.short_today_qty,
                    short_yesterday_qty=position.short_yesterday_qty,
                    long_avg_price=position.long_avg_price,
                    short_avg_price=position.short_avg_price,
                    version=PositionOrm.version + 1,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            if expected_version is None:
                raise RepositoryError(f"position not found: {position.id}")
            raise OptimisticLockError(
                f"position {position.id} version mismatch: expected {expected_version}"
            )
        self._session.flush()
        updated = self._get_orm_by_id(db_position_id)
        if updated is None:
            raise RepositoryError(f"position updated but not found: {position.id}")
        return position_to_domain(updated)

    def list_by_account(self, account_id: str) -> list[Position]:
        positions = self._session.scalars(
            select(PositionOrm)
            .where(PositionOrm.account_id == account_id)
            .order_by(PositionOrm.instrument_id.asc())
        ).all()
        return [position_to_domain(position) for position in positions]

    def _get_orm_by_id(self, db_position_id: int) -> PositionOrm | None:
        return self._session.scalar(
            select(PositionOrm)
            .where(PositionOrm.id == db_position_id)
            .execution_options(populate_existing=True)
        )

    def _get_orm_by_account_instrument(
        self,
        account_id: str,
        instrument_id: str,
    ) -> PositionOrm | None:
        return self._session.scalar(
            select(PositionOrm).where(
                PositionOrm.account_id == account_id,
                PositionOrm.instrument_id == instrument_id,
            )
        )


class SQLAlchemyPositionEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_position_event(self, event: PositionEvent) -> PositionEvent:
        existing = self._get_orm_by_trade_key(
            event.account_id,
            event.exchange,
            event.exchange_trade_id,
        )
        if existing is not None:
            return self._existing_position_event_for_append(existing, event)

        try:
            with self._session.begin_nested():
                event_orm = PositionEventOrm(
                    account_id=event.account_id,
                    instrument_id=event.instrument_id,
                    exchange=event.exchange,
                    exchange_trade_id=event.exchange_trade_id,
                    trade_id=parse_order_id(event.trade_id),
                    position_id=parse_order_id(event.position_id),
                    event_type=event.event_type,
                    direction=event.direction.value,
                    offset=event.offset.value,
                    price=event.price,
                    quantity=event.quantity,
                    before_snapshot=_snapshot_to_json(event.before_snapshot),
                    after_snapshot=_snapshot_to_json(event.after_snapshot),
                    occurred_at=event.occurred_at,
                    created_at=event.created_at,
                    raw_payload=event.raw_payload,
                )
                self._session.add(event_orm)
                self._session.flush()
            return position_event_to_domain(event_orm)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_trade_key(
                event.account_id,
                event.exchange,
                event.exchange_trade_id,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "position event unique conflict but event not found: "
                    f"{event.account_id}/{event.exchange}/{event.exchange_trade_id}"
                ) from exc
            return self._existing_position_event_for_append(existing_after_conflict, event)

    def get_by_trade_key(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> PositionEvent | None:
        event = self._get_orm_by_trade_key(account_id, exchange, exchange_trade_id)
        return position_event_to_domain(event) if event else None

    def list_by_position(self, account_id: str, instrument_id: str) -> list[PositionEvent]:
        events = self._session.scalars(
            select(PositionEventOrm)
            .where(
                PositionEventOrm.account_id == account_id,
                PositionEventOrm.instrument_id == instrument_id,
            )
            .order_by(PositionEventOrm.id.asc())
        ).all()
        return [position_event_to_domain(event) for event in events]

    def list_by_account(self, account_id: str) -> list[PositionEvent]:
        events = self._session.scalars(
            select(PositionEventOrm)
            .where(PositionEventOrm.account_id == account_id)
            .order_by(PositionEventOrm.id.asc())
        ).all()
        return [position_event_to_domain(event) for event in events]

    def _get_orm_by_trade_key(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> PositionEventOrm | None:
        return self._session.scalar(
            select(PositionEventOrm).where(
                PositionEventOrm.account_id == account_id,
                PositionEventOrm.exchange == exchange,
                PositionEventOrm.exchange_trade_id == exchange_trade_id,
            )
        )

    def _existing_position_event_for_append(
        self,
        existing: PositionEventOrm,
        event: PositionEvent,
    ) -> PositionEvent:
        if not _same_canonical_position_event_payload(existing, event):
            raise PositionEventConflictError(
                "exchange_trade_id reused with different position event payload: "
                f"{event.account_id}/{event.exchange}/{event.exchange_trade_id}"
            )
        return position_event_to_domain(existing)
