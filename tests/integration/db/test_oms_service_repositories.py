from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from futures_mvp.db.config import settings
from futures_mvp.db.models import Order
from futures_mvp.db.models import OrderEvent as OrderEventOrm
from futures_mvp.db.repositories import SQLAlchemyOrderEventRepository, SQLAlchemyOrderRepository
from futures_mvp.db.unit_of_work import SQLAlchemyUnitOfWork
from futures_mvp.domain.enums import (
    Direction,
    EventApplicationStatus,
    EventSource,
    Offset,
    OrderStatus,
    OrderType,
    RiskDecision,
)
from futures_mvp.domain.models import OrderEvent, OrderRequest, OrderState, RiskResult
from futures_mvp.interfaces.repositories import OptimisticLockError
from futures_mvp.modules.oms import OMSService

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="session")
def db_session_factory() -> Iterator[sessionmaker[Session]]:
    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_config, "head")

    engine = create_engine(settings.database_url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_orders(db_session_factory: sessionmaker[Session]) -> Iterator[None]:
    with db_session_factory.begin() as session:
        session.execute(delete(OrderEventOrm))
        session.execute(delete(Order))
    yield
    with db_session_factory.begin() as session:
        session.execute(delete(OrderEventOrm))
        session.execute(delete(Order))


def _clock() -> datetime:
    return NOW


def _service(db_session_factory: sessionmaker[Session]) -> OMSService:
    return OMSService(
        lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory),
        clock=_clock,
    )


def _order_request(client_order_id: str | None = None) -> OrderRequest:
    return OrderRequest(
        client_order_id=client_order_id or f"client-{uuid4()}",
        account_id="account-1",
        instrument_id="rb2601",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("3500"),
        quantity=Decimal("1"),
    )


def _risk_result(decision: RiskDecision) -> RiskResult:
    return RiskResult(decision=decision, rule_name="integration-risk", reason="test")


def _event(
    order_id: str,
    *,
    previous_status: OrderStatus,
    new_status: OrderStatus,
    external_event_id: str = "exchange-event-1",
) -> OrderEvent:
    return OrderEvent(
        order_id=order_id,
        previous_status=previous_status,
        new_status=new_status,
        event_source=EventSource.EXCHANGE,
        external_event_id=external_event_id,
        raw_payload={"diagnostic": True},
        occurred_at=NOW,
    )


def _order_status(session: Session, order_id: str) -> str:
    order = session.get(Order, int(order_id))
    assert order is not None
    return order.status


def _event_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(OrderEventOrm)) or 0


def _set_order_status(
    db_session_factory: sessionmaker[Session],
    order_id: str,
    status: OrderStatus,
) -> None:
    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        uow.orders.update_status(order_id, status)
        uow.commit()


def _append_order_event_row(
    db_session_factory: sessionmaker[Session],
    order_id: str,
    *,
    previous_status: OrderStatus,
    new_status: OrderStatus,
    external_event_id: str,
) -> None:
    with db_session_factory.begin() as session:
        session.add(
            OrderEventOrm(
                order_id=int(order_id),
                previous_status=previous_status.value,
                new_status=new_status.value,
                event_source=EventSource.SYSTEM.value,
                external_event_id=external_event_id,
                raw_payload={"diagnostic": True},
                occurred_at=NOW,
            )
        )


def _append_status_stream(
    db_session_factory: sessionmaker[Session],
    order_id: str,
    transitions: list[tuple[OrderStatus, OrderStatus]],
    *,
    event_id_prefix: str,
) -> None:
    for index, (previous_status, new_status) in enumerate(transitions, start=1):
        _append_order_event_row(
            db_session_factory,
            order_id,
            previous_status=previous_status,
            new_status=new_status,
            external_event_id=f"{event_id_prefix}-{index}",
        )


def test_service_create_order_commits_order_and_initial_event(
    db_session_factory: sessionmaker[Session],
) -> None:
    request = _order_request()

    order = _service(db_session_factory).create_order(
        request,
        client_order_id=request.client_order_id,
    )

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.CREATED.value
        events = session.scalars(select(OrderEventOrm)).all()

    assert len(events) == 1
    assert order.version == 0
    assert events[0].event_source == EventSource.OMS.value
    assert events[0].new_status == OrderStatus.CREATED.value


def test_service_apply_risk_result_accepted_commits_status_and_events(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)

    result = service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.RISK_ACCEPTED.value
        statuses = [
            event.new_status
            for event in session.scalars(
                select(OrderEventOrm).order_by(OrderEventOrm.id.asc())
            )
        ]

    assert result.status == EventApplicationStatus.APPLIED
    assert result.order.status == OrderStatus.RISK_ACCEPTED
    assert result.order.version == 2
    assert statuses == [
        OrderStatus.CREATED.value,
        OrderStatus.RISK_CHECKING.value,
        OrderStatus.RISK_ACCEPTED.value,
    ]


def test_service_apply_risk_result_rejected_commits_status_and_event(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)

    result = service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.REJECTED),
        external_event_id="risk-rejected-1",
    )

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.REJECTED_BY_RISK.value
        assert _event_count(session) == 2

    assert result.status == EventApplicationStatus.APPLIED
    assert result.order.status == OrderStatus.REJECTED_BY_RISK
    assert result.order.version == 1


def test_service_apply_order_event_append_unique_conflict_returns_current_order(
    db_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )
    event = _event(
        order.order_id,
        previous_status=OrderStatus.RISK_ACCEPTED,
        new_status=OrderStatus.SUBMITTING,
    )

    with db_session_factory.begin() as session:
        session.add(
            OrderEventOrm(
                order_id=int(order.order_id),
                previous_status=event.previous_status.value,
                new_status=event.new_status.value,
                event_source=event.event_source.value,
                external_event_id=event.external_event_id,
                raw_payload=event.raw_payload,
                occurred_at=event.occurred_at,
            )
        )

    original_get_by_event_key = SQLAlchemyOrderEventRepository.get_by_event_key
    hidden_calls_remaining = 2

    def hide_existing_event_twice(
        self: SQLAlchemyOrderEventRepository,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None:
        nonlocal hidden_calls_remaining
        if (
            event_source == event.event_source
            and external_event_id == event.external_event_id
            and hidden_calls_remaining > 0
        ):
            hidden_calls_remaining -= 1
            return None
        return original_get_by_event_key(self, event_source, external_event_id)

    monkeypatch.setattr(
        SQLAlchemyOrderEventRepository,
        "get_by_event_key",
        hide_existing_event_twice,
    )

    result = service.apply_order_event(event)

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.RISK_ACCEPTED.value
        event_count = (
            session.scalar(
                select(func.count())
                .select_from(OrderEventOrm)
                .where(OrderEventOrm.external_event_id == event.external_event_id)
            )
            or 0
        )

    assert result.status == EventApplicationStatus.DUPLICATE
    assert result.order.status == OrderStatus.RISK_ACCEPTED
    assert event_count == 1


def test_service_apply_order_event_duplicate_same_order_returns_duplicate(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )
    event = _event(
        order.order_id,
        previous_status=OrderStatus.RISK_ACCEPTED,
        new_status=OrderStatus.SUBMITTING,
        external_event_id="exchange-duplicate-same-order",
    )

    first = service.apply_order_event(event)
    second = service.apply_order_event(event)

    with db_session_factory() as session:
        event_count = (
            session.scalar(
                select(func.count())
                .select_from(OrderEventOrm)
                .where(OrderEventOrm.external_event_id == event.external_event_id)
            )
            or 0
        )

    assert first.status == EventApplicationStatus.APPLIED
    assert second.status == EventApplicationStatus.DUPLICATE
    assert second.order.order_id == order.order_id
    assert event_count == 1


def test_service_apply_order_event_duplicate_key_for_different_order_is_collision(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    first_request = _order_request()
    second_request = _order_request()
    first_order = service.create_order(
        first_request,
        client_order_id=first_request.client_order_id,
    )
    second_order = service.create_order(
        second_request,
        client_order_id=second_request.client_order_id,
    )
    shared_event_id = "exchange-collision"

    with db_session_factory.begin() as session:
        session.add(
            OrderEventOrm(
                order_id=int(first_order.order_id),
                previous_status=OrderStatus.CREATED.value,
                new_status=OrderStatus.UNKNOWN.value,
                event_source=EventSource.EXCHANGE.value,
                external_event_id=shared_event_id,
                raw_payload={"diagnostic": True},
                occurred_at=NOW,
            )
        )

    result = service.apply_order_event(
        _event(
            second_order.order_id,
            previous_status=OrderStatus.CREATED,
            new_status=OrderStatus.UNKNOWN,
            external_event_id=shared_event_id,
        )
    )

    with db_session_factory() as session:
        assert _order_status(session, second_order.order_id) == OrderStatus.CREATED.value
        event_count = (
            session.scalar(
                select(func.count())
                .select_from(OrderEventOrm)
                .where(OrderEventOrm.external_event_id == shared_event_id)
            )
            or 0
        )

    assert result.status == EventApplicationStatus.EVENT_KEY_COLLISION
    assert result.order.order_id == second_order.order_id
    assert event_count == 1


def test_service_apply_order_event_append_failure_rolls_back_status(
    db_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )

    original_append_event = SQLAlchemyOrderEventRepository.append_event

    def fail_exchange_append(
        self: SQLAlchemyOrderEventRepository,
        event: OrderEvent,
    ) -> OrderEvent:
        if event.event_source == EventSource.EXCHANGE:
            raise RuntimeError("forced append failure")
        return original_append_event(self, event)

    monkeypatch.setattr(SQLAlchemyOrderEventRepository, "append_event", fail_exchange_append)

    with pytest.raises(RuntimeError, match="forced append failure"):
        service.apply_order_event(
            _event(
                order.order_id,
                previous_status=OrderStatus.RISK_ACCEPTED,
                new_status=OrderStatus.SUBMITTING,
            )
        )

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.RISK_ACCEPTED.value
        assert _event_count(session) == 3


def test_service_optimistic_lock_failure_rolls_back_without_event(
    db_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )
    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as stale_uow:
        stale_order = stale_uow.orders.get_by_id(order.order_id)
        assert stale_order is not None

    service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.RISK_ACCEPTED,
            new_status=OrderStatus.SUBMITTING,
            external_event_id="exchange-event-1",
        )
    )

    original_get_by_id = SQLAlchemyOrderRepository.get_by_id

    def stale_get_by_id(
        self: SQLAlchemyOrderRepository,
        order_id: str,
    ) -> OrderState | None:
        if order_id == stale_order.order_id:
            return stale_order
        return original_get_by_id(self, order_id)

    monkeypatch.setattr(SQLAlchemyOrderRepository, "get_by_id", stale_get_by_id)

    with pytest.raises(OptimisticLockError):
        service.apply_order_event(
            _event(
                order.order_id,
                previous_status=OrderStatus.RISK_ACCEPTED,
                new_status=OrderStatus.SUBMITTING,
                external_event_id="exchange-event-2",
            )
        )

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.SUBMITTING.value
        assert _event_count(session) == 4


def test_uow_append_event_then_update_failure_rolls_back_event(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)
    event = _event(
        order.order_id,
        previous_status=OrderStatus.CREATED,
        new_status=OrderStatus.UNKNOWN,
        external_event_id="append-before-update-failure",
    )

    with pytest.raises(OptimisticLockError):
        with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
            uow.order_events.append_event(event)
            uow.orders.update_status(
                order.order_id,
                OrderStatus.UNKNOWN,
                expected_version=99,
            )
            uow.commit()

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.CREATED.value
        event_count = (
            session.scalar(
                select(func.count())
                .select_from(OrderEventOrm)
                .where(OrderEventOrm.external_event_id == event.external_event_id)
            )
            or 0
        )

    assert event_count == 0


def test_service_unknown_recovers_from_previous_status_unknown(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)
    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        uow.orders.update_status(order.order_id, OrderStatus.UNKNOWN, expected_version=0)
        uow.commit()

    recovered = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.UNKNOWN,
            new_status=OrderStatus.FILLED,
            external_event_id="unknown-recovery-ok",
        )
    )

    assert recovered.status == EventApplicationStatus.RECOVERED_FROM_UNKNOWN
    assert recovered.order.status == OrderStatus.FILLED


def test_service_unknown_previous_status_mismatch_does_not_recover(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)
    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        uow.orders.update_status(order.order_id, OrderStatus.UNKNOWN, expected_version=0)
        uow.commit()

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.ACKED,
            new_status=OrderStatus.FILLED,
            external_event_id="unknown-recovery-bad-previous",
        )
    )

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.UNKNOWN.value

    assert result.status == EventApplicationStatus.MISMATCH_REJECTED
    assert result.order.status == OrderStatus.UNKNOWN


@pytest.mark.parametrize(
    "forbidden_status",
    [OrderStatus.CANCEL_PENDING, OrderStatus.CANCEL_FAILED],
)
def test_service_unknown_recovery_rejects_forbidden_targets(
    db_session_factory: sessionmaker[Session],
    forbidden_status: OrderStatus,
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)
    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        uow.orders.update_status(order.order_id, OrderStatus.UNKNOWN, expected_version=0)
        uow.commit()

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.UNKNOWN,
            new_status=forbidden_status,
            external_event_id=f"unknown-forbidden-{forbidden_status.value}",
        )
    )

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.UNKNOWN.value

    assert result.status == EventApplicationStatus.MISMATCH_REJECTED
    assert result.order.status == OrderStatus.UNKNOWN


def test_service_apply_order_event_ignores_raw_payload_as_source_of_truth(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-raw-payload",
    )
    event = _event(
        order.order_id,
        previous_status=OrderStatus.RISK_ACCEPTED,
        new_status=OrderStatus.SUBMITTING,
        external_event_id="raw-payload-not-truth",
    ).model_copy(update={"raw_payload": {"new_status": OrderStatus.FILLED.value}})

    result = service.apply_order_event(event)

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.SUBMITTING.value

    assert result.status == EventApplicationStatus.APPLIED
    assert result.order.status == OrderStatus.SUBMITTING


def test_service_recover_order_consistent_event_stream_is_noop(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)

    result = service.recover_order(order.order_id)

    assert result.status == EventApplicationStatus.APPLIED
    assert result.order.status == OrderStatus.CREATED


def test_service_recover_order_missing_initial_event_enters_unknown(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)
    with db_session_factory.begin() as session:
        session.execute(delete(OrderEventOrm).where(OrderEventOrm.order_id == int(order.order_id)))

    result = service.recover_order(order.order_id)

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.UNKNOWN.value

    assert result.status == EventApplicationStatus.ENTERED_UNKNOWN
    assert result.order.status == OrderStatus.UNKNOWN


def test_service_recover_order_unknown_unrecoverable_stays_unknown(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)
    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        uow.orders.update_status(order.order_id, OrderStatus.UNKNOWN, expected_version=0)
        uow.commit()

    result = service.recover_order(order.order_id)

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.UNKNOWN.value

    assert result.status == EventApplicationStatus.MISMATCH_REJECTED
    assert result.order.status == OrderStatus.UNKNOWN


def test_open_orders_can_be_batch_recovered_without_external_engines(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    open_statuses = [
        OrderStatus.SUBMITTING,
        OrderStatus.SUBMIT_TIMEOUT,
        OrderStatus.SUBMITTED,
        OrderStatus.ACKED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCEL_FAILED,
        OrderStatus.UNKNOWN,
    ]
    terminal_statuses = [
        OrderStatus.REJECTED_BY_RISK,
        OrderStatus.SUBMIT_FAILED,
        OrderStatus.CANCELED,
        OrderStatus.FILLED,
        OrderStatus.REJECTED_BY_EXCHANGE,
        OrderStatus.EXPIRED,
    ]
    open_order_ids: dict[OrderStatus, str] = {}
    terminal_order_ids: set[str] = set()

    for status in open_statuses:
        request = _order_request()
        order = service.create_order(request, client_order_id=request.client_order_id)
        _set_order_status(db_session_factory, order.order_id, status)
        open_order_ids[status] = order.order_id

    _append_status_stream(
        db_session_factory,
        open_order_ids[OrderStatus.SUBMITTING],
        [
            (OrderStatus.CREATED, OrderStatus.RISK_CHECKING),
            (OrderStatus.RISK_CHECKING, OrderStatus.RISK_ACCEPTED),
            (OrderStatus.RISK_ACCEPTED, OrderStatus.SUBMITTING),
        ],
        event_id_prefix="batch-consistent-submitting",
    )

    recoverable_request = _order_request()
    recoverable_unknown = service.create_order(
        recoverable_request,
        client_order_id=recoverable_request.client_order_id,
    )
    _append_status_stream(
        db_session_factory,
        recoverable_unknown.order_id,
        [
            (OrderStatus.CREATED, OrderStatus.RISK_CHECKING),
            (OrderStatus.RISK_CHECKING, OrderStatus.RISK_ACCEPTED),
            (OrderStatus.RISK_ACCEPTED, OrderStatus.SUBMITTING),
            (OrderStatus.SUBMITTING, OrderStatus.SUBMITTED),
            (OrderStatus.SUBMITTED, OrderStatus.ACKED),
            (OrderStatus.ACKED, OrderStatus.FILLED),
        ],
        event_id_prefix="batch-recoverable-unknown",
    )
    _set_order_status(db_session_factory, recoverable_unknown.order_id, OrderStatus.UNKNOWN)

    for status in terminal_statuses:
        request = _order_request()
        order = service.create_order(request, client_order_id=request.client_order_id)
        _set_order_status(db_session_factory, order.order_id, status)
        terminal_order_ids.add(order.order_id)

    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        open_orders = uow.orders.list_open_orders()

    listed_order_ids = {order.order_id for order in open_orders}
    assert set(open_order_ids.values()).issubset(listed_order_ids)
    assert recoverable_unknown.order_id in listed_order_ids
    assert listed_order_ids.isdisjoint(terminal_order_ids)

    results = {
        order.order_id: service.recover_order(order.order_id)
        for order in open_orders
    }

    consistent_result = results[open_order_ids[OrderStatus.SUBMITTING]]
    assert consistent_result.status == EventApplicationStatus.APPLIED
    assert consistent_result.order.status == OrderStatus.SUBMITTING

    recovered_result = results[recoverable_unknown.order_id]
    assert recovered_result.status == EventApplicationStatus.RECOVERED_FROM_UNKNOWN
    assert recovered_result.order.status == OrderStatus.FILLED

    unrecoverable_result = results[open_order_ids[OrderStatus.UNKNOWN]]
    assert unrecoverable_result.status == EventApplicationStatus.MISMATCH_REJECTED
    assert unrecoverable_result.order.status == OrderStatus.UNKNOWN


def test_service_recover_order_terminal_status_is_protected(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)

    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        uow.orders.update_status(order.order_id, OrderStatus.FILLED)
        uow.commit()

    result = service.recover_order(order.order_id)

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.FILLED.value

    assert result.status == EventApplicationStatus.IGNORED_TERMINAL
    assert result.order.status == OrderStatus.FILLED
