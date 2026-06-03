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
from futures_mvp.db.repositories import SQLAlchemyOrderEventRepository
from futures_mvp.db.unit_of_work import SQLAlchemyUnitOfWork
from futures_mvp.domain.enums import (
    Direction,
    EventSource,
    Offset,
    OrderStatus,
    OrderType,
    RiskDecision,
)
from futures_mvp.domain.models import OrderEvent, OrderRequest, RiskResult
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
    assert events[0].event_source == EventSource.OMS.value
    assert events[0].new_status == OrderStatus.CREATED.value


def test_service_apply_risk_result_accepted_commits_status_and_events(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)

    accepted = service.apply_risk_result(
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

    assert accepted.status == OrderStatus.RISK_ACCEPTED
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

    rejected = service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.REJECTED),
        external_event_id="risk-rejected-1",
    )

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.REJECTED_BY_RISK.value
        assert _event_count(session) == 2

    assert rejected.status == OrderStatus.REJECTED_BY_RISK


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

    current = service.apply_order_event(event)

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

    assert current.status == OrderStatus.RISK_ACCEPTED
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


def test_service_recover_order_terminal_status_is_protected(
    db_session_factory: sessionmaker[Session],
) -> None:
    service = _service(db_session_factory)
    request = _order_request()
    order = service.create_order(request, client_order_id=request.client_order_id)

    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        uow.orders.update_status(order.order_id, OrderStatus.FILLED)
        uow.commit()

    recovered = service.recover_order(order.order_id)

    with db_session_factory() as session:
        assert _order_status(session, order.order_id) == OrderStatus.FILLED.value

    assert recovered.status == OrderStatus.FILLED

