from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from threading import Barrier, Thread
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from futures_mvp.db.config import settings
from futures_mvp.db.models import Order, Position
from futures_mvp.db.models import OrderEvent as OrderEventOrm
from futures_mvp.db.models import Trade as TradeOrm
from futures_mvp.db.repositories import (
    SQLAlchemyOrderEventRepository,
    SQLAlchemyOrderRepository,
    SQLAlchemyTradeRepository,
)
from futures_mvp.db.unit_of_work import SQLAlchemyUnitOfWork
from futures_mvp.domain.enums import Direction, EventSource, Offset, OrderStatus, OrderType
from futures_mvp.domain.models import OrderEvent, OrderRequest, Trade
from futures_mvp.interfaces.repositories import (
    EventAlreadyExistsError,
    IdempotencyConflictError,
    OptimisticLockError,
    RepositoryError,
    TradeIdempotencyConflictError,
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
        session.execute(delete(TradeOrm))
        session.execute(delete(OrderEventOrm))
        session.execute(delete(Order))
    yield
    with db_session_factory.begin() as session:
        session.execute(delete(TradeOrm))
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


def _trade(
    order_id: str,
    *,
    exchange_trade_id: str = "trade-1",
    price: Decimal = Decimal("3500.5"),
    quantity: Decimal = Decimal("1"),
    source_exchange_report_id: str = "report-1",
    raw_payload: dict[str, object] | None = None,
) -> Trade:
    return Trade(
        account_id="account-1",
        exchange="SHFE",
        exchange_trade_id=exchange_trade_id,
        order_id=order_id,
        instrument_id="rb2601",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        price=price,
        quantity=quantity,
        fee_amount=Decimal("1.2"),
        fee_currency="CNY",
        fee_source="EXCHANGE_REPORT",
        trade_time=datetime(2026, 1, 1, 9, 1, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        source_exchange_report_id=source_exchange_report_id,
        raw_payload=raw_payload or {"diagnostic": True},
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


def _order_status_and_version(session: Session, order_id: str) -> tuple[str, int]:
    order = session.get(Order, int(order_id))
    assert order is not None
    return order.status, order.version


def _run_concurrent_create_order(
    db_session_factory: sessionmaker[Session],
    first_request: OrderRequest,
    second_request: OrderRequest,
) -> tuple[list[str], list[BaseException]]:
    barrier = Barrier(2)
    order_ids: list[str] = []
    errors: list[BaseException] = []

    def create_in_thread(order_request: OrderRequest) -> None:
        session = db_session_factory()
        try:
            repository = SQLAlchemyOrderRepository(session)
            barrier.wait()
            order = repository.create_order(
                order_request,
                client_order_id=order_request.client_order_id,
            )
            session.commit()
            order_ids.append(order.order_id)
        except BaseException as exc:
            session.rollback()
            errors.append(exc)
        finally:
            session.close()

    first_thread = Thread(target=create_in_thread, args=(first_request,))
    second_thread = Thread(target=create_in_thread, args=(second_request,))
    first_thread.start()
    second_thread.start()
    first_thread.join(timeout=10)
    second_thread.join(timeout=10)

    if first_thread.is_alive() or second_thread.is_alive():
        raise AssertionError("concurrent create_order test threads did not finish")

    return order_ids, errors


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
    assert loaded.version == 0


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


def test_concurrent_create_order_same_payload_returns_single_order(
    db_session_factory: sessionmaker[Session],
) -> None:
    client_order_id = _client_order_id()
    first_request = _order_request(client_order_id)
    second_request = _order_request(client_order_id)

    order_ids, errors = _run_concurrent_create_order(
        db_session_factory,
        first_request,
        second_request,
    )

    with db_session_factory() as verification_session:
        persisted_count = _order_count_by_client_order_id(verification_session, client_order_id)

    assert errors == []
    assert len(order_ids) == 2
    assert len(set(order_ids)) == 1
    assert persisted_count == 1


def test_concurrent_create_order_different_payload_raises_idempotency_conflict(
    db_session_factory: sessionmaker[Session],
) -> None:
    client_order_id = _client_order_id()
    first_request = _order_request(client_order_id)
    second_request = _order_request(client_order_id, instrument_id="cu2601")

    order_ids, errors = _run_concurrent_create_order(
        db_session_factory,
        first_request,
        second_request,
    )

    with db_session_factory() as verification_session:
        persisted_count = _order_count_by_client_order_id(verification_session, client_order_id)

    assert len(order_ids) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], IdempotencyConflictError)
    assert not isinstance(errors[0], IntegrityError)
    assert persisted_count == 1


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
    assert updated.version == 1
    assert version == 1


def test_update_status_returns_incremented_versions(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyOrderRepository(session)

        first = repository.update_status(
            order_id,
            OrderStatus.RISK_CHECKING,
            expected_version=0,
        )
        second = repository.update_status(
            order_id,
            OrderStatus.RISK_ACCEPTED,
            expected_version=first.version,
        )

    assert first.version == 1
    assert second.version == 2


def test_update_status_expected_version_mismatch_raises_optimistic_lock(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyOrderRepository(session)

        with pytest.raises(OptimisticLockError):
            repository.update_status(order_id, OrderStatus.RISK_CHECKING, expected_version=99)


def test_update_status_uses_atomic_expected_version_check(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as setup_session:
        order_id = _create_order(setup_session)

    session_a = db_session_factory()
    session_b = db_session_factory()
    try:
        order_a = session_a.get(Order, int(order_id))
        order_b = session_b.get(Order, int(order_id))
        assert order_a is not None
        assert order_b is not None
        version_a = order_a.version
        version_b = order_b.version
        assert version_a == 0
        assert version_b == 0

        repository_a = SQLAlchemyOrderRepository(session_a)
        repository_b = SQLAlchemyOrderRepository(session_b)

        repository_a.update_status(order_id, OrderStatus.SUBMITTED, expected_version=version_a)
        session_a.commit()

        with pytest.raises(OptimisticLockError):
            repository_b.update_status(order_id, OrderStatus.ACKED, expected_version=version_b)
        session_b.rollback()
    finally:
        session_a.close()
        session_b.close()

    with db_session_factory() as verification_session:
        status, version = _order_status_and_version(verification_session, order_id)

    assert status == OrderStatus.SUBMITTED.value
    assert version == 1


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


def test_concurrent_duplicate_event_raises_event_already_exists(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as setup_session:
        order_id = _create_order(setup_session)

    event_id = "concurrent-duplicate-event"
    barrier = Barrier(2)
    successes: list[OrderEvent] = []
    errors: list[BaseException] = []

    def append_in_thread() -> None:
        session = db_session_factory()
        try:
            repository = SQLAlchemyOrderEventRepository(session)
            barrier.wait()
            event = repository.append_event(_order_event(order_id, external_event_id=event_id))
            session.commit()
            successes.append(event)
        except BaseException as exc:
            session.rollback()
            errors.append(exc)
        finally:
            session.close()

    first_thread = Thread(target=append_in_thread)
    second_thread = Thread(target=append_in_thread)
    first_thread.start()
    second_thread.start()
    first_thread.join(timeout=10)
    second_thread.join(timeout=10)

    if first_thread.is_alive() or second_thread.is_alive():
        raise AssertionError("concurrent append_event test threads did not finish")

    with db_session_factory() as verification_session:
        event_count = _order_event_count_by_external_event_id(verification_session, event_id)

    assert len(successes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], EventAlreadyExistsError)
    assert not isinstance(errors[0], IntegrityError)
    assert event_count == 1


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


def test_unit_of_work_exposes_trade_repository(
    db_session_factory: sessionmaker[Session],
) -> None:
    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        assert isinstance(uow.trades, SQLAlchemyTradeRepository)


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


def test_trade_repository_create_and_get_by_exchange_trade_id(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyTradeRepository(session)
        created = repository.create_or_get_trade(_trade(order_id))
        loaded = repository.get_by_exchange_trade_id("account-1", "SHFE", "trade-1")

    assert created.id is not None
    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.account_id == "account-1"
    assert loaded.exchange == "SHFE"
    assert loaded.exchange_trade_id == "trade-1"
    assert loaded.order_id == order_id
    assert loaded.price == Decimal("3500.5")
    assert loaded.quantity == Decimal("1")
    assert loaded.fee_amount == Decimal("1.2")
    assert loaded.fee_currency == "CNY"
    assert loaded.fee_source == "EXCHANGE_REPORT"
    assert loaded.trading_day == date(2026, 1, 1)
    assert loaded.source_exchange_report_id == "report-1"
    assert loaded.raw_payload == {"diagnostic": True}


def test_trade_repository_duplicate_same_payload_returns_existing(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyTradeRepository(session)
        first = repository.create_or_get_trade(_trade(order_id))
        second = repository.create_or_get_trade(_trade(order_id))
        trade_count = session.scalar(select(func.count()).select_from(TradeOrm))

    assert first.id == second.id
    assert trade_count == 1


def test_trade_repository_duplicate_same_facts_ignores_different_raw_payload(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyTradeRepository(session)
        first = repository.create_or_get_trade(
            _trade(order_id, raw_payload={"source": "first"})
        )
        second = repository.create_or_get_trade(
            _trade(order_id, raw_payload={"source": "second", "diagnostic": True})
        )
        trade_count = session.scalar(select(func.count()).select_from(TradeOrm))

    assert first.id == second.id
    assert trade_count == 1
    assert second.price == Decimal("3500.5")
    assert second.quantity == Decimal("1")
    assert second.fee_amount == Decimal("1.2")
    assert second.raw_payload == {"source": "first"}


def test_trade_repository_duplicate_different_payload_raises_controlled_error(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyTradeRepository(session)
        repository.create_or_get_trade(_trade(order_id))

        with pytest.raises(TradeIdempotencyConflictError):
            repository.create_or_get_trade(_trade(order_id, price=Decimal("3501")))


def test_trade_repository_unique_conflict_does_not_leak_integrity_error(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyTradeRepository(session)
        repository.create_or_get_trade(_trade(order_id))

        with pytest.raises(TradeIdempotencyConflictError) as exc_info:
            repository.create_or_get_trade(_trade(order_id, quantity=Decimal("2")))

    assert not isinstance(exc_info.value, IntegrityError)


def test_trade_repository_does_not_mutate_positions(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        before_count = session.scalar(select(func.count()).select_from(Position))
        SQLAlchemyTradeRepository(session).create_or_get_trade(_trade(order_id))
        after_count = session.scalar(select(func.count()).select_from(Position))

    assert before_count == after_count == 0


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
    with db_session_factory.begin() as session:
        repository = SQLAlchemyOrderRepository(session)
        expected_open_order_ids = []
        for status in [
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMIT_TIMEOUT,
            OrderStatus.SUBMITTED,
            OrderStatus.ACKED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CANCEL_PENDING,
            OrderStatus.CANCEL_FAILED,
            OrderStatus.UNKNOWN,
        ]:
            client_order_id = _client_order_id()
            order = repository.create_order(
                _order_request(client_order_id),
                client_order_id=client_order_id,
            )
            repository.update_status(order.order_id, status)
            expected_open_order_ids.append(order.order_id)

        for status in [
            OrderStatus.REJECTED_BY_RISK,
            OrderStatus.SUBMIT_FAILED,
            OrderStatus.CANCELED,
            OrderStatus.FILLED,
            OrderStatus.REJECTED_BY_EXCHANGE,
            OrderStatus.EXPIRED,
        ]:
            client_order_id = _client_order_id()
            order = repository.create_order(
                _order_request(client_order_id),
                client_order_id=client_order_id,
            )
            repository.update_status(order.order_id, status)

        listed = repository.list_open_orders()

    assert {order.order_id for order in listed} == set(expected_open_order_ids)
