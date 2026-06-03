from collections.abc import Callable, Iterator
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
from futures_mvp.db.repositories import (
    SQLAlchemyOrderEventRepository,
    SQLAlchemyOrderRepository,
)
from futures_mvp.db.unit_of_work import SQLAlchemyUnitOfWork
from futures_mvp.domain.enums import Direction, EventSource, Offset, OrderStatus, OrderType
from futures_mvp.domain.models import OrderEvent, OrderRequest
from futures_mvp.interfaces.repositories import (
    EventAlreadyExistsError,
    IdempotencyConflictError,
    OptimisticLockError,
    RepositoryError,
)


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


def _client_order_id() -> str:
    return f"client-{uuid4()}"


def _order_request(
    client_order_id: str | None = None,
    *,
    account_id: str = "account-1",
    instrument_id: str = "rb2601",
    limit_price: Decimal = Decimal("3500"),
    quantity: Decimal = Decimal("2"),
) -> OrderRequest:
    return OrderRequest(
        client_order_id=client_order_id or _client_order_id(),
        account_id=account_id,
        instrument_id=instrument_id,
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        order_type=OrderType.LIMIT,
        limit_price=limit_price,
        quantity=quantity,
    )


def _order_event(
    order_id: str,
    external_event_id: str | None = None,
    new_status: OrderStatus = OrderStatus.CREATED,
    previous_status: OrderStatus | None = None,
    raw_payload: dict[str, object] | None = None,
    occurred_at: datetime | None = None,
) -> OrderEvent:
    return OrderEvent(
        order_id=order_id,
        previous_status=previous_status,
        new_status=new_status,
        event_source=EventSource.OMS,
        external_event_id=external_event_id or f"event-{uuid4()}",
        raw_payload=raw_payload or {"diagnostic": True},
        occurred_at=occurred_at or datetime.now(UTC),
    )


def _create_order(session: Session, client_order_id: str | None = None) -> str:
    request = _order_request(client_order_id)
    repository = SQLAlchemyOrderRepository(session)
    return repository.create_order(request, client_order_id=request.client_order_id).order_id


def _order_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Order)) or 0


def _order_event_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(OrderEventOrm)) or 0


def _order_count_by_client_order_id(session: Session, client_order_id: str) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.client_order_id == client_order_id)
        )
        or 0
    )


def _order_event_count_by_external_event_id(session: Session, external_event_id: str) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(OrderEventOrm)
            .where(OrderEventOrm.external_event_id == external_event_id)
        )
        or 0
    )


def test_create_order_then_get_by_client_order_id(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        request = _order_request()
        repository = SQLAlchemyOrderRepository(session)

        created = repository.create_order(request, client_order_id=request.client_order_id)
        loaded = repository.get_by_client_order_id(request.client_order_id)

    assert loaded == created
    assert loaded is not None
    assert loaded.request.limit_price == Decimal("3500")
    assert loaded.request.quantity == Decimal("2")


def test_create_order_same_client_order_id_and_same_payload_returns_existing_order(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        client_order_id = _client_order_id()
        request = _order_request(client_order_id)
        repository = SQLAlchemyOrderRepository(session)

        first = repository.create_order(request, client_order_id=client_order_id)
        second = repository.create_order(request, client_order_id=client_order_id)

        assert second == first
        assert _order_count(session) == 1


def test_create_order_same_payload_does_not_rewrite_existing_status(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        client_order_id = _client_order_id()
        request = _order_request(client_order_id)
        repository = SQLAlchemyOrderRepository(session)

        created = repository.create_order(request, client_order_id=client_order_id)
        repository.update_status(created.order_id, OrderStatus.SUBMITTED)
        repeated = repository.create_order(request, client_order_id=client_order_id)

    assert repeated.status is OrderStatus.SUBMITTED


def test_create_order_decimal_equivalent_payload_is_idempotent(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        client_order_id = _client_order_id()
        first_request = _order_request(
            client_order_id,
            limit_price=Decimal("1.0"),
            quantity=Decimal("2.0"),
        )
        second_request = _order_request(
            client_order_id,
            limit_price=Decimal("1.00"),
            quantity=Decimal("2.00"),
        )
        repository = SQLAlchemyOrderRepository(session)

        first = repository.create_order(first_request, client_order_id=client_order_id)
        second = repository.create_order(second_request, client_order_id=client_order_id)

        assert second.order_id == first.order_id
        assert _order_count(session) == 1


@pytest.mark.parametrize(
    "changed_request",
    [
        pytest.param(
            lambda client_order_id: _order_request(client_order_id, account_id="account-2"),
            id="different_account_id",
        ),
        pytest.param(
            lambda client_order_id: _order_request(client_order_id, instrument_id="cu2601"),
            id="different_instrument_id",
        ),
        pytest.param(
            lambda client_order_id: _order_request(client_order_id, limit_price=Decimal("3501")),
            id="different_limit_price",
        ),
        pytest.param(
            lambda client_order_id: _order_request(client_order_id, quantity=Decimal("3")),
            id="different_quantity",
        ),
    ],
)
def test_create_order_same_client_order_id_different_payload_raises_conflict(
    db_session_factory: sessionmaker[Session],
    changed_request: Callable[[str], OrderRequest],
) -> None:
    with db_session_factory.begin() as session:
        client_order_id = _client_order_id()
        repository = SQLAlchemyOrderRepository(session)
        created = repository.create_order(
            _order_request(client_order_id),
            client_order_id=client_order_id,
        )
        event_repository = SQLAlchemyOrderEventRepository(session)
        event_repository.append_event(_order_event(created.order_id))
        order_count_before = _order_count(session)
        event_count_before = _order_event_count(session)

        with pytest.raises(IdempotencyConflictError):
            repository.create_order(
                changed_request(client_order_id),
                client_order_id=client_order_id,
            )

        assert _order_count(session) == order_count_before
        assert _order_event_count(session) == event_count_before


def test_get_by_id_accepts_string_db_id(db_session_factory: sessionmaker[Session]) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyOrderRepository(session)

        loaded = repository.get_by_id(order_id)

    assert loaded is not None
    assert loaded.order_id == order_id


def test_invalid_order_id_string_is_rejected(db_session_factory: sessionmaker[Session]) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyOrderRepository(session)

        with pytest.raises(RepositoryError):
            repository.get_by_id("not-an-int")


def test_update_status_updates_status_and_version(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyOrderRepository(session)

        updated = repository.update_status(
            order_id,
            OrderStatus.RISK_CHECKING,
            expected_version=0,
        )
        db_order = session.get(Order, int(order_id))
        version = db_order.version if db_order else None

    assert updated.status is OrderStatus.RISK_CHECKING
    assert version == 1


def test_update_status_expected_version_mismatch_raises_optimistic_lock(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyOrderRepository(session)

        with pytest.raises(OptimisticLockError):
            repository.update_status(order_id, OrderStatus.RISK_CHECKING, expected_version=99)


def test_append_event_then_list_by_order_id(db_session_factory: sessionmaker[Session]) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyOrderEventRepository(session)
        event = _order_event(order_id)

        appended = repository.append_event(event)
        listed = repository.list_by_order_id(order_id)

    assert appended == event
    assert listed == [event]


def test_append_event_then_get_by_event_key(db_session_factory: sessionmaker[Session]) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyOrderEventRepository(session)
        event = _order_event(order_id)

        appended = repository.append_event(event)
        loaded = repository.get_by_event_key(event.event_source, event.external_event_id)

    assert loaded == appended


def test_event_replay_ordering_uses_id_ascending(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyOrderEventRepository(session)
        second = repository.append_event(_order_event(order_id, "event-2", OrderStatus.SUBMITTED))
        first = repository.append_event(_order_event(order_id, "event-1", OrderStatus.CREATED))

        listed = repository.list_by_order_id(order_id)

    assert listed == [second, first]


def test_list_by_order_id_invalid_order_id_is_rejected(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyOrderEventRepository(session)

        with pytest.raises(RepositoryError):
            repository.list_by_order_id("not-an-int")


def test_duplicate_event_raises_and_does_not_add_row(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyOrderEventRepository(session)
        event = _order_event(order_id, external_event_id="duplicate-event")
        repository.append_event(event)
        event_count_before = _order_event_count(session)

        with pytest.raises(EventAlreadyExistsError):
            repository.append_event(event)

        assert _order_event_count(session) == event_count_before


def test_append_event_does_not_auto_commit(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as setup_session:
        order_id = _create_order(setup_session)

    session = db_session_factory()
    try:
        repository = SQLAlchemyOrderEventRepository(session)
        event = _order_event(order_id, external_event_id="uncommitted-event")
        repository.append_event(event)

        with db_session_factory() as other_session:
            persisted = other_session.scalar(
                select(OrderEventOrm).where(
                    OrderEventOrm.external_event_id == event.external_event_id
                )
            )

        assert persisted is None
    finally:
        session.rollback()
        session.close()


def test_append_event_rollback_leaves_no_event(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as setup_session:
        order_id = _create_order(setup_session)

    event_id = "rolled-back-event"
    session = db_session_factory()
    try:
        repository = SQLAlchemyOrderEventRepository(session)
        repository.append_event(_order_event(order_id, external_event_id=event_id))
        session.rollback()
    finally:
        session.close()

    with db_session_factory() as verification_session:
        assert _order_event_count_by_external_event_id(verification_session, event_id) == 0


def test_create_order_and_append_event_rollback_leaves_no_order_or_event(
    db_session_factory: sessionmaker[Session],
) -> None:
    client_order_id = _client_order_id()
    event_id = "rolled-back-create-event"

    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        order = uow.orders.create_order(
            _order_request(client_order_id),
            client_order_id=client_order_id,
        )
        uow.order_events.append_event(_order_event(order.order_id, external_event_id=event_id))
        uow.rollback()

    with db_session_factory() as verification_session:
        assert _order_count_by_client_order_id(verification_session, client_order_id) == 0
        assert _order_event_count_by_external_event_id(verification_session, event_id) == 0


def test_create_order_and_append_event_commit_persists_both(
    db_session_factory: sessionmaker[Session],
) -> None:
    client_order_id = _client_order_id()
    event_id = "committed-create-event"

    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        order = uow.orders.create_order(
            _order_request(client_order_id),
            client_order_id=client_order_id,
        )
        uow.order_events.append_event(_order_event(order.order_id, external_event_id=event_id))
        uow.commit()

    with db_session_factory() as verification_session:
        assert _order_count_by_client_order_id(verification_session, client_order_id) == 1
        assert _order_event_count_by_external_event_id(verification_session, event_id) == 1


def test_unit_of_work_exception_rolls_back_order_and_event(
    db_session_factory: sessionmaker[Session],
) -> None:
    client_order_id = _client_order_id()
    event_id = "exception-rollback-event"

    with pytest.raises(RuntimeError):
        with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
            order = uow.orders.create_order(
                _order_request(client_order_id),
                client_order_id=client_order_id,
            )
            uow.order_events.append_event(_order_event(order.order_id, external_event_id=event_id))
            raise RuntimeError("force rollback")

    with db_session_factory() as verification_session:
        assert _order_count_by_client_order_id(verification_session, client_order_id) == 0
        assert _order_event_count_by_external_event_id(verification_session, event_id) == 0


def test_update_status_and_append_event_commit_persists_both(
    db_session_factory: sessionmaker[Session],
) -> None:
    client_order_id = _client_order_id()
    event_id = "acked-event"
    with db_session_factory.begin() as setup_session:
        order_id = _create_order(setup_session, client_order_id)

    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        uow.orders.update_status(order_id, OrderStatus.ACKED, expected_version=0)
        uow.order_events.append_event(
            _order_event(
                order_id,
                external_event_id=event_id,
                previous_status=OrderStatus.CREATED,
                new_status=OrderStatus.ACKED,
            )
        )
        uow.commit()

    with db_session_factory() as verification_session:
        order = verification_session.get(Order, int(order_id))
        event_count = _order_event_count_by_external_event_id(verification_session, event_id)

    assert order is not None
    assert order.status == OrderStatus.ACKED.value
    assert event_count == 1


def test_update_status_and_failed_append_event_rollback_leaves_order_unchanged(
    db_session_factory: sessionmaker[Session],
) -> None:
    client_order_id = _client_order_id()
    event_id = "duplicate-status-event"
    with db_session_factory.begin() as setup_session:
        order_id = _create_order(setup_session, client_order_id)
        event_repository = SQLAlchemyOrderEventRepository(setup_session)
        event_repository.append_event(_order_event(order_id, external_event_id=event_id))

    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        uow.orders.update_status(order_id, OrderStatus.ACKED, expected_version=0)
        with pytest.raises(EventAlreadyExistsError):
            uow.order_events.append_event(_order_event(order_id, external_event_id=event_id))
        uow.rollback()

    with db_session_factory() as verification_session:
        order = verification_session.get(Order, int(order_id))
        event_count = _order_event_count_by_external_event_id(verification_session, event_id)

    assert order is not None
    assert order.status == OrderStatus.CREATED.value
    assert event_count == 1


def test_order_event_occurred_at_and_raw_payload_round_trip(
    db_session_factory: sessionmaker[Session],
) -> None:
    occurred_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    raw_payload = {"diagnostic": True, "nested": {"source": "test"}}

    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyOrderEventRepository(session)
        event = repository.append_event(
            _order_event(
                order_id,
                external_event_id="payload-round-trip-event",
                raw_payload=raw_payload,
                occurred_at=occurred_at,
            )
        )

        loaded = repository.get_by_event_key(event.event_source, event.external_event_id)

    assert loaded is not None
    assert loaded.occurred_at == occurred_at
    assert loaded.raw_payload == raw_payload


def test_unit_of_work_rollback_leaves_no_order(
    db_session_factory: sessionmaker[Session],
) -> None:
    client_order_id = _client_order_id()

    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        uow.orders.create_order(_order_request(client_order_id), client_order_id=client_order_id)
        uow.rollback()

    with db_session_factory() as session:
        persisted = session.scalar(select(Order).where(Order.client_order_id == client_order_id))

    assert persisted is None


def test_repository_methods_do_not_auto_commit(
    db_session_factory: sessionmaker[Session],
) -> None:
    client_order_id = _client_order_id()
    session = db_session_factory()
    try:
        repository = SQLAlchemyOrderRepository(session)
        repository.create_order(_order_request(client_order_id), client_order_id=client_order_id)

        with db_session_factory() as other_session:
            persisted = other_session.scalar(
                select(Order).where(Order.client_order_id == client_order_id)
            )

        assert persisted is None
    finally:
        session.rollback()
        session.close()


def test_list_open_orders_returns_only_open_recovery_statuses(
    db_session_factory: sessionmaker[Session],
) -> None:
    open_client_id = _client_order_id()
    terminal_client_id = _client_order_id()

    with db_session_factory.begin() as session:
        repository = SQLAlchemyOrderRepository(session)
        open_order = repository.create_order(
            _order_request(open_client_id),
            client_order_id=open_client_id,
        )
        terminal_order = repository.create_order(
            _order_request(terminal_client_id),
            client_order_id=terminal_client_id,
        )
        repository.update_status(open_order.order_id, OrderStatus.SUBMITTED)
        repository.update_status(terminal_order.order_id, OrderStatus.FILLED)

        listed = repository.list_open_orders()

    assert [order.order_id for order in listed] == [open_order.order_id]
