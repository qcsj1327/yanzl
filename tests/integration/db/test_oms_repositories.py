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
from futures_mvp.db.models import AccountSnapshot as AccountSnapshotOrm
from futures_mvp.db.models import MarginSnapshot as MarginSnapshotOrm
from futures_mvp.db.models import MarketBar as MarketBarOrm
from futures_mvp.db.models import MarketTick as MarketTickOrm
from futures_mvp.db.models import Order, Position
from futures_mvp.db.models import OrderEvent as OrderEventOrm
from futures_mvp.db.models import PnLSnapshot as PnLSnapshotOrm
from futures_mvp.db.models import PositionEvent as PositionEventOrm
from futures_mvp.db.models import SettlementSnapshot as SettlementSnapshotOrm
from futures_mvp.db.models import Trade as TradeOrm
from futures_mvp.db.repositories import (
    SQLAlchemyAccountSnapshotRepository,
    SQLAlchemyMarginSnapshotRepository,
    SQLAlchemyMarketBarRepository,
    SQLAlchemyMarketTickRepository,
    SQLAlchemyOrderEventRepository,
    SQLAlchemyOrderRepository,
    SQLAlchemyPnLSnapshotRepository,
    SQLAlchemyPositionEventRepository,
    SQLAlchemyPositionRepository,
    SQLAlchemySettlementSnapshotRepository,
    SQLAlchemyTradeRepository,
)
from futures_mvp.db.unit_of_work import SQLAlchemyUnitOfWork
from futures_mvp.domain.enums import (
    BarTimeframe,
    Direction,
    EventSource,
    MarginPriceBasis,
    MarginResultStatus,
    MarketDataResultStatus,
    Offset,
    OrderStatus,
    OrderType,
    PnLPriceBasis,
    PnLResultStatus,
    PositionManagerResultStatus,
    SettlementResultStatus,
)
from futures_mvp.domain.models import (
    AccountContext,
    Bar,
    CloseTradeContext,
    MarginRule,
    MarginSnapshot,
    OrderEvent,
    OrderRequest,
    PnLSnapshot,
    PositionEvent,
    PositionSnapshot,
    SettlementContext,
    SettlementPrice,
    SettlementSnapshot,
    Tick,
    Trade,
)
from futures_mvp.interfaces.repositories import (
    EventAlreadyExistsError,
    IdempotencyConflictError,
    MarginSnapshotConflictError,
    MarketDataConflictError,
    OptimisticLockError,
    PnLSnapshotConflictError,
    PositionEventConflictError,
    RepositoryError,
    SettlementSnapshotConflictError,
    TradeIdempotencyConflictError,
)
from futures_mvp.modules.margin import MarginEngine
from futures_mvp.modules.pnl import PnLEngine
from futures_mvp.modules.position import PositionManager
from futures_mvp.modules.settlement import SettlementEngine


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
        session.execute(delete(MarketBarOrm))
        session.execute(delete(MarketTickOrm))
        session.execute(delete(SettlementSnapshotOrm))
        session.execute(delete(AccountSnapshotOrm))
        session.execute(delete(PnLSnapshotOrm))
        session.execute(delete(MarginSnapshotOrm))
        session.execute(delete(PositionEventOrm))
        session.execute(delete(Position))
        session.execute(delete(TradeOrm))
        session.execute(delete(OrderEventOrm))
        session.execute(delete(Order))
    yield
    with db_session_factory.begin() as session:
        session.execute(delete(MarketBarOrm))
        session.execute(delete(MarketTickOrm))
        session.execute(delete(SettlementSnapshotOrm))
        session.execute(delete(AccountSnapshotOrm))
        session.execute(delete(PnLSnapshotOrm))
        session.execute(delete(MarginSnapshotOrm))
        session.execute(delete(PositionEventOrm))
        session.execute(delete(Position))
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


def _market_tick(
    ts: datetime | None = None,
    *,
    price: Decimal = Decimal("500"),
    raw_payload: dict[str, object] | None = None,
) -> Tick:
    return Tick(
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        ts=ts or datetime(2026, 6, 7, 9, tzinfo=UTC),
        price=price,
        volume=Decimal("1"),
        turnover=Decimal("500"),
        open_interest=Decimal("10"),
        bid_price_1=Decimal("499"),
        ask_price_1=Decimal("501"),
        bid_volume_1=Decimal("2"),
        ask_volume_1=Decimal("3"),
        source="adapter",
        raw_payload=raw_payload,
    )


def _market_bar(
    bar_ts: datetime | None = None,
    *,
    close: Decimal = Decimal("501"),
    raw_payload: dict[str, object] | None = None,
) -> Bar:
    return Bar(
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        timeframe=BarTimeframe.M1,
        bar_ts=bar_ts or datetime(2026, 6, 7, 9, tzinfo=UTC),
        open=Decimal("500"),
        high=Decimal("505"),
        low=Decimal("499"),
        close=close,
        volume=Decimal("10"),
        turnover=Decimal("5000"),
        open_interest=Decimal("20"),
        source="adapter",
        quality_status=MarketDataResultStatus.ACCEPTED,
        raw_payload=raw_payload,
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
    direction: Direction = Direction.BUY,
    offset: Offset = Offset.OPEN,
    price: Decimal = Decimal("3500.5"),
    quantity: Decimal = Decimal("1"),
    fee_amount: Decimal | None = Decimal("1.2"),
    fee_currency: str | None = "CNY",
    source_exchange_report_id: str = "report-1",
    source_report_id: str | None = "report-1",
    source_order_event_id: str | None = "event-1",
    client_order_id: str | None = "client-order-1",
    trade_instrument_id: str | None = "rb2601",
    symbol: str | None = "rb",
    raw_payload: dict[str, object] | None = None,
) -> Trade:
    return Trade(
        account_id="account-1",
        exchange="SHFE",
        exchange_trade_id=exchange_trade_id,
        order_id=order_id,
        client_order_id=client_order_id,
        instrument_id="rb2601",
        trade_instrument_id=trade_instrument_id,
        symbol=symbol,
        direction=direction,
        offset=offset,
        price=price,
        quantity=quantity,
        fee_amount=fee_amount,
        fee_currency=fee_currency,
        fee_source="EXCHANGE_REPORT" if fee_amount is not None else None,
        trade_time=datetime(2026, 1, 1, 9, 1, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        source_report_id=source_report_id,
        source_exchange_report_id=source_exchange_report_id,
        source_order_event_id=source_order_event_id,
        raw_payload=raw_payload or {"diagnostic": True},
    )


def _position_event(
    trade: Trade,
    position_id: str,
    *,
    before_snapshot: PositionSnapshot | None = None,
    after_snapshot: PositionSnapshot | None = None,
    quantity: Decimal | None = None,
    raw_payload: dict[str, object] | None = None,
) -> PositionEvent:
    before = before_snapshot or PositionSnapshot(
        account_id=trade.account_id,
        instrument_id=trade.instrument_id,
        long_today_qty=Decimal("0"),
        long_yesterday_qty=Decimal("0"),
        short_today_qty=Decimal("0"),
        short_yesterday_qty=Decimal("0"),
        long_avg_price=Decimal("0"),
        short_avg_price=Decimal("0"),
        version=0,
    )
    after = after_snapshot or PositionSnapshot(
        account_id=trade.account_id,
        instrument_id=trade.instrument_id,
        long_today_qty=quantity or trade.quantity,
        long_yesterday_qty=Decimal("0"),
        short_today_qty=Decimal("0"),
        short_yesterday_qty=Decimal("0"),
        long_avg_price=trade.price,
        short_avg_price=Decimal("0"),
        version=1,
    )
    return PositionEvent(
        account_id=trade.account_id,
        instrument_id=trade.instrument_id,
        exchange=trade.exchange,
        exchange_trade_id=trade.exchange_trade_id,
        trade_id=trade.id or "1",
        position_id=position_id,
        event_type="TRADE_APPLIED",
        direction=trade.direction,
        offset=trade.offset,
        price=trade.price,
        quantity=quantity or trade.quantity,
        before_snapshot=before,
        after_snapshot=after,
        occurred_at=trade.trade_time,
        created_at=datetime.now(UTC),
        raw_payload=raw_payload or {"diagnostic": True},
    )


def _margin_snapshot(
    *,
    position_version: int = 1,
    trading_day: date = date(2026, 1, 1),
    config_hash: str = "margin-config-v1",
    calculation_key: str = "account-1:rb2601:1:v1",
    initial_margin: Decimal = Decimal("3500"),
    margin_used: Decimal | None = None,
) -> MarginSnapshot:
    return MarginSnapshot(
        account_id="account-1",
        instrument_id="rb2601",
        position_version=position_version,
        trading_day=trading_day,
        config_hash=config_hash,
        rule_id="rule-1",
        rule_version="v1",
        calculation_key=calculation_key,
        long_qty=Decimal("1"),
        short_qty=Decimal("0"),
        price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        initial_margin=initial_margin,
        maintenance_margin=Decimal("2000"),
        margin_used=margin_used or initial_margin,
        available_cash=Decimal("10000"),
        equity=Decimal("20000"),
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
    )


def _pnl_snapshot(
    *,
    position_version: int = 1,
    trading_day: date = date(2026, 1, 1),
    config_hash: str = "pnl-config-v1",
    calculation_key: str = "account-1:rb2601:1:pnl",
    realized_pnl: Decimal = Decimal("100"),
    unrealized_pnl: Decimal = Decimal("50"),
    trade_id: str | None = "trade-1",
) -> PnLSnapshot:
    return PnLSnapshot(
        account_id="account-1",
        instrument_id="rb2601",
        position_version=position_version,
        trading_day=trading_day,
        config_hash=config_hash,
        trade_id=trade_id,
        margin_snapshot_id="margin-1",
        calculation_key=calculation_key,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        total_pnl=realized_pnl + unrealized_pnl,
        fee_amount=Decimal("2"),
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
    )


def _close_context() -> CloseTradeContext:
    return CloseTradeContext(
        account_id="account-1",
        instrument_id="rb2601",
        position_version=0,
        avg_cost=Decimal("3400"),
        available_qty=Decimal("2"),
        contract_multiplier=Decimal("10"),
    )


def _settlement_account_context() -> AccountContext:
    return AccountContext(
        account_id="account-1",
        equity=Decimal("10000"),
        available_cash=Decimal("6500"),
        frozen_cash=Decimal("0"),
        snapshot_time=datetime(2026, 6, 4, 14, tzinfo=UTC),
    )


def _settlement_price() -> SettlementPrice:
    return SettlementPrice(
        instrument_id="rb2601",
        exchange="SHFE",
        trading_day=date(2026, 6, 4),
        price=Decimal("3500"),
        received_at=datetime(2026, 6, 4, 14, tzinfo=UTC),
    )


def _settlement_snapshot() -> SettlementSnapshot:
    return SettlementSnapshot(
        account_id="account-1",
        trading_day=date(2026, 6, 4),
        calculation_key="account-1:2026-06-04:settlement",
        positions_before=(
            {
                "id": "1",
                "account_id": "account-1",
                "instrument_id": "rb2601",
                "long_today_qty": "1.00000000",
                "long_yesterday_qty": "2.00000000",
                "short_today_qty": "1.00000000",
                "short_yesterday_qty": "0E-8",
                "frozen_long_qty": "0E-8",
                "frozen_short_qty": "0E-8",
                "long_avg_price": "3400.00000000",
                "short_avg_price": "3600.00000000",
                "settlement_price": "0E-8",
                "last_price": "0E-8",
                "realized_pnl": "10.00000000",
                "unrealized_pnl": "20.00000000",
                "margin_used": "77.00000000",
                "version": 0,
            },
        ),
        positions_after=(
            {
                "id": "1",
                "account_id": "account-1",
                "instrument_id": "rb2601",
                "long_today_qty": "0",
                "long_yesterday_qty": "3.00000000",
                "short_today_qty": "0",
                "short_yesterday_qty": "1.00000000",
                "frozen_long_qty": "0E-8",
                "frozen_short_qty": "0E-8",
                "long_avg_price": "3400.00000000",
                "short_avg_price": "3600.00000000",
                "settlement_price": "0E-8",
                "last_price": "0E-8",
                "realized_pnl": "10.00000000",
                "unrealized_pnl": "20.00000000",
                "margin_used": "77.00000000",
                "version": 1,
            },
        ),
        settlement_prices=(_settlement_price().model_dump(mode="json"),),
        pnl_snapshot_ids=("1",),
        margin_snapshot_ids=("1",),
        cash_before=Decimal("10000"),
        cash_after=Decimal("10100"),
        realized_pnl=Decimal("100"),
        unrealized_pnl=Decimal("50"),
        margin_used=Decimal("3500"),
        status=SettlementResultStatus.SETTLED,
        created_at=datetime(2026, 6, 4, 15, tzinfo=UTC),
    )


def _margin_rule() -> MarginRule:
    return MarginRule(
        rule_id="rule-1",
        rule_version="v1",
        instrument_id="rb2601",
        exchange="SHFE",
        contract_multiplier=Decimal("10"),
        long_initial_margin_rate=Decimal("0.10"),
        short_initial_margin_rate=Decimal("0.20"),
        long_maintenance_margin_rate=Decimal("0.05"),
        short_maintenance_margin_rate=Decimal("0.10"),
        price_basis=MarginPriceBasis.MANUAL,
        price=Decimal("3500"),
    )


def _account_context(available_cash: Decimal = Decimal("100000")) -> AccountContext:
    return AccountContext(
        account_id="account-1",
        equity=Decimal("200000"),
        available_cash=available_cash,
        frozen_cash=Decimal("0"),
        snapshot_time=datetime(2026, 1, 1, 9, tzinfo=UTC),
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
    assert loaded.client_order_id == "client-order-1"
    assert loaded.trade_instrument_id == "rb2601"
    assert loaded.symbol == "rb"
    assert loaded.source_report_id == "report-1"
    assert loaded.source_exchange_report_id == "report-1"
    assert loaded.source_order_event_id == "event-1"
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


def test_trade_repository_stage_l3_aliases_and_order_query(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyTradeRepository(session)
        created = repository.append_trade(_trade(order_id))
        loaded = repository.get_by_trade_identity("account-1", "SHFE", "trade-1")
        listed = repository.list_by_order_id(order_id)

    assert loaded is not None
    assert loaded.id == created.id
    assert [trade.id for trade in listed] == [created.id]


def test_trade_repository_stage_l3_canonical_conflict(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        repository = SQLAlchemyTradeRepository(session)
        repository.append_trade(_trade(order_id))

        with pytest.raises(TradeIdempotencyConflictError):
            repository.append_trade(_trade(order_id, source_order_event_id="event-2"))


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


def test_position_repository_create_get_and_version_default(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyPositionRepository(session)
        created = repository.create_or_get_position("account-1", "rb2601")
        loaded = repository.get_by_account_instrument("account-1", "rb2601")

    assert created.id is not None
    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.long_today_qty == Decimal("0")
    assert loaded.version == 0


def test_position_repository_update_increments_version_and_stage_c_fields_only(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyPositionRepository(session)
        created = repository.create_or_get_position("account-1", "rb2601")
        seeded = session.get(Position, int(created.id or "0"))
        assert seeded is not None
        seeded.realized_pnl = Decimal("12")
        seeded.unrealized_pnl = Decimal("34")
        seeded.margin_used = Decimal("56")
        updated = repository.update_position(
            created.model_copy(
                update={
                    "long_today_qty": Decimal("2"),
                    "long_avg_price": Decimal("3500"),
                }
            ),
            expected_version=0,
        )

    assert updated.version == 1
    assert updated.long_today_qty == Decimal("2")
    assert updated.long_avg_price == Decimal("3500")
    assert updated.realized_pnl == Decimal("12")
    assert updated.unrealized_pnl == Decimal("34")
    assert updated.margin_used == Decimal("56")


def test_position_repository_expected_version_mismatch_is_controlled_error(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyPositionRepository(session)
        created = repository.create_or_get_position("account-1", "rb2601")

        with pytest.raises(OptimisticLockError):
            repository.update_position(
                created.model_copy(update={"long_today_qty": Decimal("1")}),
                expected_version=1,
            )


def test_position_event_repository_round_trip_and_unique_trade_key(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        trade = SQLAlchemyTradeRepository(session).create_or_get_trade(_trade(order_id))
        position = SQLAlchemyPositionRepository(session).create_or_get_position(
            trade.account_id,
            trade.instrument_id,
        )
        repository = SQLAlchemyPositionEventRepository(session)
        created = repository.append_position_event(_position_event(trade, position.id or "1"))
        loaded = repository.get_by_trade_key("account-1", "SHFE", "trade-1")
        event_count = session.scalar(select(func.count()).select_from(PositionEventOrm))

    assert created.id is not None
    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.trade_id == trade.id
    assert loaded.position_id == position.id
    assert loaded.before_snapshot.long_today_qty == Decimal("0")
    assert loaded.after_snapshot.long_today_qty == Decimal("1")
    assert event_count == 1


def test_position_event_duplicate_same_payload_returns_existing(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        trade = SQLAlchemyTradeRepository(session).create_or_get_trade(_trade(order_id))
        position = SQLAlchemyPositionRepository(session).create_or_get_position(
            trade.account_id,
            trade.instrument_id,
        )
        repository = SQLAlchemyPositionEventRepository(session)
        first = repository.append_position_event(
            _position_event(trade, position.id or "1", raw_payload={"source": "first"})
        )
        second = repository.append_position_event(
            _position_event(trade, position.id or "1", raw_payload={"source": "second"})
        )
        event_count = session.scalar(select(func.count()).select_from(PositionEventOrm))

    assert first.id == second.id
    assert event_count == 1
    assert second.raw_payload == {"source": "first"}


def test_position_event_duplicate_different_payload_raises_controlled_error(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        trade = SQLAlchemyTradeRepository(session).create_or_get_trade(_trade(order_id))
        position = SQLAlchemyPositionRepository(session).create_or_get_position(
            trade.account_id,
            trade.instrument_id,
        )
        repository = SQLAlchemyPositionEventRepository(session)
        repository.append_position_event(_position_event(trade, position.id or "1"))

        with pytest.raises(PositionEventConflictError) as exc_info:
            repository.append_position_event(
                _position_event(trade, position.id or "1", quantity=Decimal("2"))
            )

    assert not isinstance(exc_info.value, IntegrityError)


def test_position_event_duplicate_different_before_snapshot_raises_controlled_error(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        trade = SQLAlchemyTradeRepository(session).create_or_get_trade(_trade(order_id))
        position = SQLAlchemyPositionRepository(session).create_or_get_position(
            trade.account_id,
            trade.instrument_id,
        )
        repository = SQLAlchemyPositionEventRepository(session)
        repository.append_position_event(_position_event(trade, position.id or "1"))

        changed_before = PositionSnapshot(
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
            long_today_qty=Decimal("1"),
            long_yesterday_qty=Decimal("0"),
            short_today_qty=Decimal("0"),
            short_yesterday_qty=Decimal("0"),
            long_avg_price=Decimal("3500.5"),
            short_avg_price=Decimal("0"),
            version=0,
        )
        with pytest.raises(PositionEventConflictError):
            repository.append_position_event(
                _position_event(
                    trade,
                    position.id or "1",
                    before_snapshot=changed_before,
                )
            )


def test_position_event_duplicate_different_after_snapshot_raises_controlled_error(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        trade = SQLAlchemyTradeRepository(session).create_or_get_trade(_trade(order_id))
        position = SQLAlchemyPositionRepository(session).create_or_get_position(
            trade.account_id,
            trade.instrument_id,
        )
        repository = SQLAlchemyPositionEventRepository(session)
        repository.append_position_event(_position_event(trade, position.id or "1"))

        changed_after = PositionSnapshot(
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
            long_today_qty=Decimal("2"),
            long_yesterday_qty=Decimal("0"),
            short_today_qty=Decimal("0"),
            short_yesterday_qty=Decimal("0"),
            long_avg_price=trade.price,
            short_avg_price=Decimal("0"),
            version=1,
        )
        with pytest.raises(PositionEventConflictError):
            repository.append_position_event(
                _position_event(
                    trade,
                    position.id or "1",
                    after_snapshot=changed_after,
                )
            )


def test_position_manager_close_without_position_does_not_insert_empty_row(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        persisted_trade = SQLAlchemyTradeRepository(session).create_or_get_trade(
            _trade(order_id).model_copy(
                update={
                    "direction": Direction.SELL,
                    "offset": Offset.CLOSE_TODAY,
                }
            )
        )

    manager = PositionManager(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = manager.apply_trade(persisted_trade)

    with db_session_factory.begin() as session:
        position_count = session.scalar(select(func.count()).select_from(Position))
        event_count = session.scalar(select(func.count()).select_from(PositionEventOrm))

    assert result.status == PositionManagerResultStatus.REJECTED_INSUFFICIENT_POSITION
    assert position_count == 0
    assert event_count == 0


def test_position_manager_duplicate_detects_projection_divergence(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        order_id = _create_order(session)
        persisted_trade = SQLAlchemyTradeRepository(session).create_or_get_trade(_trade(order_id))

    manager = PositionManager(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    first = manager.apply_trade(persisted_trade)

    with db_session_factory.begin() as session:
        position = session.scalar(select(Position))
        assert position is not None
        position.long_today_qty = Decimal("2")

    replay = manager.replay_trades([persisted_trade])

    with db_session_factory.begin() as session:
        event_count = session.scalar(select(func.count()).select_from(PositionEventOrm))

    assert first.status == PositionManagerResultStatus.APPLIED
    assert replay.results[0].status == PositionManagerResultStatus.CONFLICT
    assert replay.results[0].reason == "position_projection_diverged_from_event_snapshot"
    assert replay.has_divergence
    assert event_count == 1


def test_unit_of_work_exposes_position_repositories(
    db_session_factory: sessionmaker[Session],
) -> None:
    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        assert isinstance(uow.positions, SQLAlchemyPositionRepository)
        assert isinstance(uow.position_events, SQLAlchemyPositionEventRepository)


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


def test_margin_snapshot_repository_round_trip_and_latest(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyMarginSnapshotRepository(session)
        first = repository.append_margin_snapshot(_margin_snapshot())
        second = repository.append_margin_snapshot(
            _margin_snapshot(
                position_version=2,
                calculation_key="account-1:rb2601:2:v1",
                initial_margin=Decimal("4200"),
            )
        )

        latest = repository.get_latest("account-1", "rb2601")
        by_version = repository.get_by_position_version("account-1", "rb2601", 1)
        by_identity = repository.get_by_accounting_identity(
            "account-1",
            "rb2601",
            1,
            date(2026, 1, 1),
            "margin-config-v1",
        )
        listed = repository.list_by_account("account-1")

    assert first.id is not None
    assert first.trading_day == date(2026, 1, 1)
    assert first.config_hash == "margin-config-v1"
    assert latest == second
    assert by_version == first
    assert by_identity == first
    assert listed == [first, second]


def test_margin_snapshot_duplicate_same_canonical_returns_existing(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyMarginSnapshotRepository(session)
        first = repository.append_margin_snapshot(_margin_snapshot())
        second = repository.append_margin_snapshot(_margin_snapshot())
        count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert second == first
    assert count == 1


def test_margin_snapshot_same_position_version_different_key_same_facts_returns_existing(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyMarginSnapshotRepository(session)
        first = repository.append_margin_snapshot(_margin_snapshot())
        second = repository.append_margin_snapshot(
            _margin_snapshot(calculation_key="account-1:rb2601:1:v1-retry")
        )
        count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert second == first
    assert count == 1


def test_margin_snapshot_duplicate_different_canonical_raises_controlled_error(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyMarginSnapshotRepository(session)
        repository.append_margin_snapshot(_margin_snapshot())

        with pytest.raises(MarginSnapshotConflictError):
            repository.append_margin_snapshot(
                _margin_snapshot(initial_margin=Decimal("9999"))
            )


def test_margin_snapshot_same_position_version_different_key_different_facts_conflicts(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyMarginSnapshotRepository(session)
        repository.append_margin_snapshot(_margin_snapshot())

        with pytest.raises(MarginSnapshotConflictError):
            repository.append_margin_snapshot(
                _margin_snapshot(
                    calculation_key="account-1:rb2601:1:v1-retry",
                    initial_margin=Decimal("9999"),
                )
            )
        count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert count == 1


def test_margin_snapshot_different_trading_day_or_config_are_independent_facts(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyMarginSnapshotRepository(session)
        first = repository.append_margin_snapshot(_margin_snapshot())
        next_day = repository.append_margin_snapshot(
            _margin_snapshot(
                trading_day=date(2026, 1, 2),
                calculation_key="account-1:rb2601:1:v1:2026-01-02",
            )
        )
        next_config = repository.append_margin_snapshot(
            _margin_snapshot(
                config_hash="margin-config-v2",
                calculation_key="account-1:rb2601:1:v2",
            )
        )
        by_version = repository.get_by_position_version("account-1", "rb2601", 1)
        count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert {first.id, next_day.id, next_config.id}
    assert by_version is None
    assert count == 3


def test_unit_of_work_exposes_margin_snapshots(
    db_session_factory: sessionmaker[Session],
) -> None:
    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        assert isinstance(uow.margin_snapshots, SQLAlchemyMarginSnapshotRepository)


def test_margin_engine_persists_snapshot_and_updates_margin_used_only(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_yesterday_qty=Decimal("1"),
            short_today_qty=Decimal("0"),
            short_yesterday_qty=Decimal("0"),
            long_avg_price=Decimal("3500"),
            short_avg_price=Decimal("0"),
            realized_pnl=Decimal("12"),
            unrealized_pnl=Decimal("34"),
            margin_used=Decimal("0"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = MarginEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.calculate_margin(
        domain_position,
        _margin_rule(),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )

    with db_session_factory() as session:
        updated = session.scalar(
            select(Position).where(
                Position.account_id == "account-1",
                Position.instrument_id == "rb2601",
            )
        )
        snapshot_count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert result.status == MarginResultStatus.CALCULATED
    assert result.snapshot is not None
    assert updated is not None
    assert updated.margin_used == Decimal("7000.00000000")
    assert updated.long_today_qty == Decimal("1.00000000")
    assert updated.long_yesterday_qty == Decimal("1.00000000")
    assert updated.long_avg_price == Decimal("3500.00000000")
    assert updated.realized_pnl == Decimal("12.00000000")
    assert updated.unrealized_pnl == Decimal("34.00000000")
    assert snapshot_count == 1


def test_margin_engine_live_duplicate_same_position_version_same_facts_noop(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_yesterday_qty=Decimal("1"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = MarginEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    first = engine.calculate_margin(
        domain_position,
        _margin_rule(),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )
    second = engine.calculate_margin(
        domain_position,
        _margin_rule(),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1-retry",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )

    with db_session_factory() as session:
        updated = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert first.status == MarginResultStatus.CALCULATED
    assert first.snapshot is not None
    assert second.status == MarginResultStatus.CALCULATED
    assert second.snapshot == first.snapshot
    assert updated is not None
    assert updated.version == 1
    assert updated.margin_used == first.snapshot.margin_used
    assert snapshot_count == 1


def test_margin_engine_live_duplicate_same_position_version_different_facts_conflicts(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_yesterday_qty=Decimal("1"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = MarginEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    first = engine.calculate_margin(
        domain_position,
        _margin_rule(),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )
    conflict = engine.calculate_margin(
        domain_position,
        _margin_rule().model_copy(update={"price": Decimal("3600")}),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1-retry",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )

    with db_session_factory() as session:
        updated = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert first.status == MarginResultStatus.CALCULATED
    assert first.snapshot is not None
    assert conflict.status == MarginResultStatus.CONFLICT
    assert conflict.reason == "margin_snapshot_position_version_diverged"
    assert updated is not None
    assert updated.version == 1
    assert updated.margin_used == first.snapshot.margin_used
    assert snapshot_count == 1


def test_margin_engine_margin_only_update_cannot_overwrite_malformed_position_fields(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_yesterday_qty=Decimal("2"),
            short_today_qty=Decimal("0"),
            short_yesterday_qty=Decimal("0"),
            long_avg_price=Decimal("3500"),
            short_avg_price=Decimal("0"),
            realized_pnl=Decimal("12"),
            unrealized_pnl=Decimal("34"),
            margin_used=Decimal("0"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    malformed_position = domain_position.model_copy(
        update={
            "long_today_qty": Decimal("999"),
            "long_avg_price": Decimal("9999"),
            "realized_pnl": Decimal("999"),
            "unrealized_pnl": Decimal("999"),
        }
    )
    engine = MarginEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.calculate_margin(
        malformed_position,
        _margin_rule(),
        _account_context(Decimal("10000000")),
        calculation_key="account-1:rb2601:0:malformed",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )

    with db_session_factory() as session:
        updated = session.scalar(
            select(Position).where(
                Position.account_id == "account-1",
                Position.instrument_id == "rb2601",
            )
        )

    assert result.status == MarginResultStatus.CALCULATED
    assert result.snapshot is not None
    assert updated is not None
    assert updated.version == 1
    assert updated.margin_used == result.snapshot.margin_used
    assert updated.long_today_qty == Decimal("1.00000000")
    assert updated.long_yesterday_qty == Decimal("2.00000000")
    assert updated.long_avg_price == Decimal("3500.00000000")
    assert updated.realized_pnl == Decimal("12.00000000")
    assert updated.unrealized_pnl == Decimal("34.00000000")


def test_margin_engine_rejected_result_does_not_persist_or_update(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(account_id="account-1", instrument_id="rb2601")
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = MarginEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.calculate_margin(
        domain_position,
        _margin_rule().model_copy(update={"price": None}),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )

    with db_session_factory() as session:
        updated = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert result.status == MarginResultStatus.REJECTED_MISSING_PRICE
    assert updated is not None
    assert updated.margin_used == Decimal("0E-8")
    assert snapshot_count == 0


def test_margin_engine_identity_mismatch_does_not_persist_or_update(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(account_id="account-1", instrument_id="rb2601")
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = MarginEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    account_mismatch = engine.calculate_margin(
        domain_position,
        _margin_rule(),
        _account_context().model_copy(update={"account_id": "account-2"}),
        calculation_key="account-1:rb2601:0:account-mismatch",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )
    instrument_mismatch = engine.calculate_margin(
        domain_position,
        _margin_rule().model_copy(update={"instrument_id": "ag2601"}),
        _account_context(),
        calculation_key="account-1:rb2601:0:instrument-mismatch",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )

    with db_session_factory() as session:
        updated = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert account_mismatch.status == MarginResultStatus.ERROR
    assert account_mismatch.reason == "margin_identity_mismatch: account_id"
    assert instrument_mismatch.status == MarginResultStatus.ERROR
    assert instrument_mismatch.reason == "margin_identity_mismatch: instrument_id"
    assert updated is not None
    assert updated.version == 0
    assert updated.margin_used == Decimal("0E-8")
    assert snapshot_count == 0


def test_margin_engine_duplicate_replay_noop_and_live_divergence_conflict(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None
    engine = MarginEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    first = engine.calculate_margin(
        domain_position,
        _margin_rule(),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )
    assert first.status == MarginResultStatus.CALCULATED

    assert first.snapshot is not None
    replay_position = domain_position.model_copy(update={"margin_used": first.snapshot.margin_used})
    replay = engine.replay_margin(
        replay_position,
        _margin_rule(),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )

    assert replay.status == MarginResultStatus.CALCULATED
    with db_session_factory() as session:
        snapshot_count_after_replay = session.scalar(
            select(func.count()).select_from(MarginSnapshotOrm)
        )
    assert snapshot_count_after_replay == 1

    diverged_position = domain_position.model_copy(update={"margin_used": Decimal("1")})
    divergence = engine.replay_margin(
        diverged_position,
        _margin_rule(),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )

    assert divergence.status == MarginResultStatus.CONFLICT
    assert divergence.reason == "position_margin_used_diverged_from_snapshot"


def test_margin_replay_same_position_version_different_key_same_facts_noop(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = MarginEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    first = engine.calculate_margin(
        domain_position,
        _margin_rule(),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )
    assert first.status == MarginResultStatus.CALCULATED
    assert first.snapshot is not None

    replay_position = domain_position.model_copy(update={"margin_used": first.snapshot.margin_used})
    replay_same_facts = engine.replay_margin(
        replay_position,
        _margin_rule(),
        _account_context(),
        calculation_key="account-1:rb2601:0:v2",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )
    replay_conflict = engine.replay_margin(
        replay_position,
        _margin_rule().model_copy(update={"price": Decimal("3600")}),
        _account_context(),
        calculation_key="account-1:rb2601:0:v3",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )

    with db_session_factory() as session:
        updated = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert replay_same_facts.status == MarginResultStatus.CALCULATED
    assert replay_same_facts.snapshot == first.snapshot
    assert replay_conflict.status == MarginResultStatus.CONFLICT
    assert replay_conflict.reason == "margin_snapshot_replay_diverged"
    assert updated is not None
    assert updated.version == 1
    assert updated.margin_used == first.snapshot.margin_used
    assert snapshot_count == 1


def test_margin_engine_snapshot_conflict_rolls_back_position_update(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(account_id="account-1", instrument_id="rb2601")
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
        SQLAlchemyMarginSnapshotRepository(session).append_margin_snapshot(
            _margin_snapshot(
                position_version=0,
                calculation_key="account-1:rb2601:0:v1",
                initial_margin=Decimal("9999"),
            )
        )
    assert domain_position is not None

    engine = MarginEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.calculate_margin(
        domain_position,
        _margin_rule(),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )

    with db_session_factory() as session:
        position_after = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert result.status == MarginResultStatus.CONFLICT
    assert position_after is not None
    assert position_after.margin_used == Decimal("0E-8")
    assert snapshot_count == 1


def test_margin_engine_optimistic_lock_rolls_back_snapshot_append(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(account_id="account-1", instrument_id="rb2601")
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
        position.version = 1
    assert domain_position is not None

    engine = MarginEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.calculate_margin(
        domain_position,
        _margin_rule(),
        _account_context(),
        calculation_key="account-1:rb2601:0:v1",
        calculated_at=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
    )

    with db_session_factory() as session:
        snapshot_count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))
        position_after = session.scalar(select(Position))

    assert result.status == MarginResultStatus.ERROR
    assert snapshot_count == 0
    assert position_after is not None
    assert position_after.margin_used == Decimal("0E-8")


def test_pnl_snapshot_repository_round_trip_and_latest(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyPnLSnapshotRepository(session)
        first = repository.append_pnl_snapshot(_pnl_snapshot())
        second = repository.append_pnl_snapshot(
            _pnl_snapshot(
                position_version=2,
                calculation_key="account-1:rb2601:2:pnl",
                realized_pnl=Decimal("200"),
            )
        )

        latest = repository.get_latest("account-1", "rb2601")
        by_key = repository.get_by_calculation_key("account-1", "rb2601", first.calculation_key)
        by_version = repository.get_by_position_version("account-1", "rb2601", 1)
        by_identity = repository.get_by_accounting_identity(
            "account-1",
            "rb2601",
            1,
            date(2026, 1, 1),
            "pnl-config-v1",
        )
        listed = repository.list_by_account("account-1")

    assert first.id is not None
    assert first.trading_day == date(2026, 1, 1)
    assert first.config_hash == "pnl-config-v1"
    assert latest == second
    assert by_key == first
    assert by_version == first
    assert by_identity == first
    assert listed == [first, second]


def test_pnl_snapshot_duplicate_same_canonical_returns_existing(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyPnLSnapshotRepository(session)
        first = repository.append_pnl_snapshot(_pnl_snapshot())
        second = repository.append_pnl_snapshot(_pnl_snapshot())
        count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert second == first
    assert count == 1


def test_pnl_snapshot_same_position_version_different_key_same_facts_returns_existing(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyPnLSnapshotRepository(session)
        first = repository.append_pnl_snapshot(_pnl_snapshot())
        second = repository.append_pnl_snapshot(
            _pnl_snapshot(calculation_key="account-1:rb2601:1:pnl-retry")
        )
        count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert second == first
    assert count == 1


def test_pnl_snapshot_duplicate_different_canonical_raises_controlled_error(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyPnLSnapshotRepository(session)
        repository.append_pnl_snapshot(_pnl_snapshot())

        with pytest.raises(PnLSnapshotConflictError) as exc_info:
            repository.append_pnl_snapshot(_pnl_snapshot(realized_pnl=Decimal("999")))

    assert not isinstance(exc_info.value, IntegrityError)


def test_pnl_snapshot_same_position_version_different_key_different_canonical_conflicts(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyPnLSnapshotRepository(session)
        repository.append_pnl_snapshot(_pnl_snapshot())

        with pytest.raises(PnLSnapshotConflictError):
            repository.append_pnl_snapshot(
                _pnl_snapshot(
                    calculation_key="account-1:rb2601:1:pnl-retry",
                    realized_pnl=Decimal("999"),
                )
            )
        count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert count == 1


def test_pnl_snapshot_different_trading_day_or_config_are_independent_facts(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repository = SQLAlchemyPnLSnapshotRepository(session)
        first = repository.append_pnl_snapshot(_pnl_snapshot())
        next_day = repository.append_pnl_snapshot(
            _pnl_snapshot(
                trading_day=date(2026, 1, 2),
                calculation_key="account-1:rb2601:1:pnl:2026-01-02",
            )
        )
        next_config = repository.append_pnl_snapshot(
            _pnl_snapshot(
                config_hash="pnl-config-v2",
                calculation_key="account-1:rb2601:1:pnl-v2",
            )
        )
        by_version = repository.get_by_position_version("account-1", "rb2601", 1)
        count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert {first.id, next_day.id, next_config.id}
    assert by_version is None
    assert count == 3


def test_unit_of_work_exposes_pnl_snapshots(
    db_session_factory: sessionmaker[Session],
) -> None:
    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        assert isinstance(uow.pnl_snapshots, SQLAlchemyPnLSnapshotRepository)


def test_position_repository_update_pnl_updates_only_pnl_fields(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_yesterday_qty=Decimal("2"),
            long_avg_price=Decimal("3500"),
            margin_used=Decimal("88"),
        )
        session.add(position)
        session.flush()

        updated = SQLAlchemyPositionRepository(session).update_pnl(
            "account-1",
            "rb2601",
            Decimal("123"),
            Decimal("456"),
            expected_version=0,
        )

    assert updated.version == 1
    assert updated.realized_pnl == Decimal("123")
    assert updated.unrealized_pnl == Decimal("456")
    assert updated.long_today_qty == Decimal("1")
    assert updated.long_yesterday_qty == Decimal("2")
    assert updated.long_avg_price == Decimal("3500")
    assert updated.margin_used == Decimal("88")


def test_pnl_engine_persists_snapshot_and_updates_pnl_only(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_yesterday_qty=Decimal("1"),
            short_today_qty=Decimal("1"),
            long_avg_price=Decimal("3400"),
            short_avg_price=Decimal("3600"),
            realized_pnl=Decimal("10"),
            unrealized_pnl=Decimal("0"),
            margin_used=Decimal("77"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = PnLEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.calculate_pnl(
        domain_position,
        trade=_trade(
            "order-1",
            direction=Direction.SELL,
            offset=Offset.CLOSE_TODAY,
            price=Decimal("3500"),
            fee_amount=Decimal("2"),
        ),
        close_context=_close_context(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )

    with db_session_factory() as session:
        updated = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert result.status == PnLResultStatus.CALCULATED
    assert result.snapshot is not None
    assert updated is not None
    assert updated.realized_pnl == Decimal("1008.00000000")
    assert updated.unrealized_pnl == Decimal("3000.00000000")
    assert updated.long_today_qty == Decimal("1.00000000")
    assert updated.long_yesterday_qty == Decimal("1.00000000")
    assert updated.long_avg_price == Decimal("3400.00000000")
    assert updated.margin_used == Decimal("77.00000000")
    assert snapshot_count == 1


def test_pnl_engine_rejected_result_does_not_persist_or_update(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(account_id="account-1", instrument_id="rb2601")
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = PnLEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.calculate_pnl(
        domain_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=None,
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )

    with db_session_factory() as session:
        updated = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert result.status == PnLResultStatus.REJECTED_MISSING_PRICE
    assert updated is not None
    assert updated.realized_pnl == Decimal("0E-8")
    assert updated.unrealized_pnl == Decimal("0E-8")
    assert snapshot_count == 0


def test_pnl_engine_fee_unknown_rejects_persistent_projection(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_avg_price=Decimal("3400"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = PnLEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.calculate_pnl(
        domain_position,
        trade=_trade(
            "order-1",
            direction=Direction.SELL,
            offset=Offset.CLOSE_TODAY,
            price=Decimal("3500"),
            fee_amount=None,
            fee_currency=None,
        ),
        close_context=_close_context(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )

    with db_session_factory() as session:
        position_after = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert result.status == PnLResultStatus.REJECTED_MISSING_FEE
    assert result.reason == "fee_unknown"
    assert result.realized is not None
    assert result.realized.gross_realized_pnl == Decimal("1000")
    assert result.realized.net_realized_pnl is None
    assert position_after is not None
    assert position_after.realized_pnl == Decimal("0E-8")
    assert position_after.unrealized_pnl == Decimal("0E-8")
    assert position_after.version == 0
    assert snapshot_count == 0


def test_pnl_engine_duplicate_calculate_same_canonical_noop(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_avg_price=Decimal("3400"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = PnLEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    first = engine.calculate_pnl(
        domain_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )
    duplicate = engine.calculate_pnl(
        domain_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 4, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )

    with db_session_factory() as session:
        position_after = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert first.status == PnLResultStatus.CALCULATED
    assert duplicate.status == PnLResultStatus.CALCULATED
    assert duplicate.snapshot == first.snapshot
    assert position_after is not None
    assert position_after.version == 1
    assert position_after.unrealized_pnl == Decimal("1000.00000000")
    assert snapshot_count == 1


def test_pnl_engine_duplicate_calculate_different_canonical_conflicts_without_update(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_avg_price=Decimal("3400"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = PnLEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    first = engine.calculate_pnl(
        domain_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )
    conflict = engine.calculate_pnl(
        domain_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3501"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 4, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )

    with db_session_factory() as session:
        position_after = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert first.status == PnLResultStatus.CALCULATED
    assert conflict.status == PnLResultStatus.CONFLICT
    assert conflict.reason == "pnl_snapshot_diverged"
    assert position_after is not None
    assert position_after.version == 1
    assert position_after.unrealized_pnl == Decimal("1000.00000000")
    assert snapshot_count == 1


def test_pnl_replay_duplicate_noop_and_live_divergence_conflict(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_avg_price=Decimal("3400"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = PnLEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    first = engine.calculate_pnl(
        domain_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )
    assert first.status == PnLResultStatus.CALCULATED
    assert first.snapshot is not None

    replay_position = domain_position.model_copy(
        update={
            "realized_pnl": first.snapshot.realized_pnl,
            "unrealized_pnl": first.snapshot.unrealized_pnl,
        }
    )
    replay = engine.replay_pnl(
        replay_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )
    diverged = engine.replay_pnl(
        domain_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )

    with db_session_factory() as session:
        snapshot_count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert replay.status == PnLResultStatus.CALCULATED
    assert diverged.status == PnLResultStatus.CALCULATED
    assert snapshot_count == 1


def test_pnl_replay_uses_live_position_row_for_divergence(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_avg_price=Decimal("3400"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
    assert domain_position is not None

    engine = PnLEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    first = engine.calculate_pnl(
        domain_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )
    assert first.status == PnLResultStatus.CALCULATED
    assert first.snapshot is not None

    with db_session_factory.begin() as session:
        live_position = session.scalar(select(Position))
        assert live_position is not None
        live_position.realized_pnl = Decimal("999")
        live_position.unrealized_pnl = Decimal("999")

    forged_position = domain_position.model_copy(
        update={
            "realized_pnl": first.snapshot.realized_pnl,
            "unrealized_pnl": first.snapshot.unrealized_pnl,
        }
    )
    replay = engine.replay_pnl(
        forged_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )

    with db_session_factory() as session:
        position_after = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert replay.status == PnLResultStatus.CONFLICT
    assert replay.reason == "live_pnl_diverged_from_snapshot"
    assert position_after is not None
    assert position_after.realized_pnl == Decimal("999.00000000")
    assert position_after.unrealized_pnl == Decimal("999.00000000")
    assert position_after.version == 1
    assert snapshot_count == 1


def test_pnl_replay_canonical_conflict_does_not_update_position(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_avg_price=Decimal("3400"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
        SQLAlchemyPnLSnapshotRepository(session).append_pnl_snapshot(
            _pnl_snapshot(position_version=0, calculation_key="account-1:rb2601:0:pnl")
        )
    assert domain_position is not None

    engine = PnLEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.replay_pnl(
        domain_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )

    with db_session_factory() as session:
        position_after = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert result.status == PnLResultStatus.CONFLICT
    assert result.reason == "pnl_snapshot_replay_diverged"
    assert position_after is not None
    assert position_after.realized_pnl == Decimal("0E-8")
    assert position_after.unrealized_pnl == Decimal("0E-8")
    assert snapshot_count == 1


def test_pnl_engine_snapshot_conflict_rolls_back_position_update(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(account_id="account-1", instrument_id="rb2601")
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
        SQLAlchemyPnLSnapshotRepository(session).append_pnl_snapshot(
            _pnl_snapshot(
                position_version=0,
                calculation_key="account-1:rb2601:0:pnl",
                realized_pnl=Decimal("999"),
            )
        )
    assert domain_position is not None

    engine = PnLEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.calculate_pnl(
        domain_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )

    with db_session_factory() as session:
        position_after = session.scalar(select(Position))
        snapshot_count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))

    assert result.status == PnLResultStatus.CONFLICT
    assert position_after is not None
    assert position_after.realized_pnl == Decimal("0E-8")
    assert position_after.unrealized_pnl == Decimal("0E-8")
    assert snapshot_count == 1


def test_pnl_engine_optimistic_lock_rolls_back_snapshot_append(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(account_id="account-1", instrument_id="rb2601")
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
        position.version = 1
    assert domain_position is not None

    engine = PnLEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.calculate_pnl(
        domain_position,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculation_key="account-1:rb2601:0:pnl",
        calculated_at=datetime(2026, 1, 1, 9, 3, tzinfo=UTC),
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
    )

    with db_session_factory() as session:
        snapshot_count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))
        position_after = session.scalar(select(Position))

    assert result.status == PnLResultStatus.ERROR
    assert snapshot_count == 0
    assert position_after is not None
    assert position_after.realized_pnl == Decimal("0E-8")
    assert position_after.unrealized_pnl == Decimal("0E-8")


def test_unit_of_work_exposes_stage_f_repositories(
    db_session_factory: sessionmaker[Session],
) -> None:
    with SQLAlchemyUnitOfWork(session_factory=db_session_factory) as uow:
        assert isinstance(uow.account_snapshots, SQLAlchemyAccountSnapshotRepository)
        assert isinstance(uow.settlement_snapshots, SQLAlchemySettlementSnapshotRepository)


def test_position_repository_settlement_roll_updates_only_qty_buckets(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_yesterday_qty=Decimal("2"),
            short_today_qty=Decimal("3"),
            short_yesterday_qty=Decimal("4"),
            long_avg_price=Decimal("3400"),
            short_avg_price=Decimal("3600"),
            realized_pnl=Decimal("10"),
            unrealized_pnl=Decimal("20"),
            margin_used=Decimal("77"),
        )
        session.add(position)
        session.flush()

        updated = SQLAlchemyPositionRepository(session).roll_today_to_yesterday_for_settlement(
            "account-1",
            "rb2601",
            expected_version=0,
        )

    assert updated.long_today_qty == Decimal("0E-8")
    assert updated.long_yesterday_qty == Decimal("3.00000000")
    assert updated.short_today_qty == Decimal("0E-8")
    assert updated.short_yesterday_qty == Decimal("7.00000000")
    assert updated.long_avg_price == Decimal("3400.00000000")
    assert updated.short_avg_price == Decimal("3600.00000000")
    assert updated.realized_pnl == Decimal("10.00000000")
    assert updated.unrealized_pnl == Decimal("20.00000000")
    assert updated.margin_used == Decimal("77.00000000")
    assert updated.version == 1


def test_settlement_snapshot_repository_duplicate_and_conflict(
    db_session_factory: sessionmaker[Session],
) -> None:
    snapshot = _settlement_snapshot()
    with db_session_factory.begin() as session:
        repository = SQLAlchemySettlementSnapshotRepository(session)
        appended = repository.append_settlement_snapshot(snapshot)
        duplicate = repository.append_settlement_snapshot(
            snapshot.model_copy(update={"created_at": datetime(2026, 6, 4, 16, tzinfo=UTC)})
        )

        with pytest.raises(SettlementSnapshotConflictError):
            repository.append_settlement_snapshot(
                snapshot.model_copy(update={"cash_after": Decimal("999")})
            )

    assert appended.id is not None
    assert duplicate == appended


def test_settlement_engine_persists_account_snapshot_rolls_positions_and_duplicates_noop(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_yesterday_qty=Decimal("2"),
            short_today_qty=Decimal("1"),
            long_avg_price=Decimal("3400"),
            short_avg_price=Decimal("3600"),
            realized_pnl=Decimal("10"),
            unrealized_pnl=Decimal("20"),
            margin_used=Decimal("77"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
        margin_snapshot = SQLAlchemyMarginSnapshotRepository(session).append_margin_snapshot(
            _margin_snapshot(
                position_version=0,
                trading_day=date(2026, 6, 4),
                calculation_key="settlement-margin",
            )
        )
        pnl_snapshot = SQLAlchemyPnLSnapshotRepository(session).append_pnl_snapshot(
            _pnl_snapshot(
                position_version=0,
                trading_day=date(2026, 6, 4),
                calculation_key="settlement-pnl",
                trade_id=None,
            ).model_copy(update={"price_basis": PnLPriceBasis.SETTLEMENT_PRICE})
        )
    assert domain_position is not None

    context = SettlementContext(
        account_id="account-1",
        trading_day=date(2026, 6, 4),
        account_before=_settlement_account_context(),
        positions=(domain_position,),
        pnl_snapshots=(pnl_snapshot,),
        margin_snapshots=(margin_snapshot,),
        settlement_prices=(_settlement_price(),),
        calculation_key="account-1:2026-06-04:settlement",
        settled_at=datetime(2026, 6, 4, 15, tzinfo=UTC),
    )
    engine = SettlementEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))

    first = engine.settle(context)
    duplicate = engine.settle(context)

    with db_session_factory() as session:
        position_after = session.scalar(select(Position))
        settlement_count = session.scalar(select(func.count()).select_from(SettlementSnapshotOrm))
        account_count = session.scalar(select(func.count()).select_from(AccountSnapshotOrm))
        pnl_count = session.scalar(select(func.count()).select_from(PnLSnapshotOrm))
        margin_count = session.scalar(select(func.count()).select_from(MarginSnapshotOrm))

    assert first.status == SettlementResultStatus.SETTLED
    assert first.snapshot is not None
    assert first.snapshot.account_snapshot_before_id is not None
    assert first.snapshot.account_snapshot_after_id is not None
    assert duplicate.status == SettlementResultStatus.DUPLICATE
    assert position_after is not None
    assert position_after.long_today_qty == Decimal("0E-8")
    assert position_after.long_yesterday_qty == Decimal("3.00000000")
    assert position_after.short_today_qty == Decimal("0E-8")
    assert position_after.short_yesterday_qty == Decimal("1.00000000")
    assert position_after.long_avg_price == Decimal("3400.00000000")
    assert position_after.realized_pnl == Decimal("10.00000000")
    assert position_after.margin_used == Decimal("77.00000000")
    assert position_after.version == 1
    assert settlement_count == 1
    assert account_count == 2
    assert pnl_count == 1
    assert margin_count == 1


def test_settlement_engine_rejected_frozen_qty_has_no_persistence(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            frozen_long_qty=Decimal("1"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
        margin_snapshot = SQLAlchemyMarginSnapshotRepository(session).append_margin_snapshot(
            _margin_snapshot(
                position_version=0,
                trading_day=date(2026, 6, 4),
                calculation_key="settlement-margin",
            )
        )
        pnl_snapshot = SQLAlchemyPnLSnapshotRepository(session).append_pnl_snapshot(
            _pnl_snapshot(
                position_version=0,
                trading_day=date(2026, 6, 4),
                calculation_key="settlement-pnl",
                trade_id=None,
            ).model_copy(update={"price_basis": PnLPriceBasis.SETTLEMENT_PRICE})
        )
    assert domain_position is not None

    engine = SettlementEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    result = engine.settle(
        SettlementContext(
            account_id="account-1",
            trading_day=date(2026, 6, 4),
            account_before=_settlement_account_context(),
            positions=(domain_position,),
            pnl_snapshots=(pnl_snapshot,),
            margin_snapshots=(margin_snapshot,),
            settlement_prices=(_settlement_price(),),
            calculation_key="account-1:2026-06-04:settlement",
            settled_at=datetime(2026, 6, 4, 15, tzinfo=UTC),
        )
    )

    with db_session_factory() as session:
        settlement_count = session.scalar(select(func.count()).select_from(SettlementSnapshotOrm))
        account_count = session.scalar(select(func.count()).select_from(AccountSnapshotOrm))
        position_after = session.scalar(select(Position))

    assert result.status == SettlementResultStatus.REJECTED_FROZEN_POSITION
    assert result.snapshot is None
    assert settlement_count == 0
    assert account_count == 0
    assert position_after is not None
    assert position_after.version == 0
    assert position_after.long_today_qty == Decimal("1.00000000")


def test_settlement_replay_detects_live_position_divergence(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        position = Position(
            account_id="account-1",
            instrument_id="rb2601",
            long_today_qty=Decimal("1"),
            long_yesterday_qty=Decimal("2"),
            long_avg_price=Decimal("3400"),
        )
        session.add(position)
        session.flush()
        domain_position = SQLAlchemyPositionRepository(session).get_by_account_instrument(
            "account-1",
            "rb2601",
        )
        margin_snapshot = SQLAlchemyMarginSnapshotRepository(session).append_margin_snapshot(
            _margin_snapshot(
                position_version=0,
                trading_day=date(2026, 6, 4),
                calculation_key="settlement-margin",
            )
        )
        pnl_snapshot = SQLAlchemyPnLSnapshotRepository(session).append_pnl_snapshot(
            _pnl_snapshot(
                position_version=0,
                trading_day=date(2026, 6, 4),
                calculation_key="settlement-pnl",
                trade_id=None,
            ).model_copy(update={"price_basis": PnLPriceBasis.SETTLEMENT_PRICE})
        )
    assert domain_position is not None

    context = SettlementContext(
        account_id="account-1",
        trading_day=date(2026, 6, 4),
        account_before=_settlement_account_context(),
        positions=(domain_position,),
        pnl_snapshots=(pnl_snapshot,),
        margin_snapshots=(margin_snapshot,),
        settlement_prices=(_settlement_price(),),
        calculation_key="account-1:2026-06-04:settlement",
        settled_at=datetime(2026, 6, 4, 15, tzinfo=UTC),
    )
    engine = SettlementEngine(lambda: SQLAlchemyUnitOfWork(session_factory=db_session_factory))
    assert engine.settle(context).status == SettlementResultStatus.SETTLED

    with db_session_factory.begin() as session:
        live_position = session.scalar(select(Position))
        assert live_position is not None
        live_position.long_yesterday_qty = Decimal("999")

    replay = engine.replay_settlement(context)

    with db_session_factory() as session:
        settlement_count = session.scalar(select(func.count()).select_from(SettlementSnapshotOrm))
        position_after = session.scalar(select(Position))

    assert replay.status == SettlementResultStatus.CONFLICT
    assert replay.reason == "live_position_diverged_from_settlement_snapshot"
    assert settlement_count == 1
    assert position_after is not None
    assert position_after.long_yesterday_qty == Decimal("999.00000000")
    assert position_after.version == 1


def test_market_tick_repository_round_trip_lists_and_idempotency(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repo = SQLAlchemyMarketTickRepository(session)
        tick = _market_tick(raw_payload={"diagnostic": "first"})
        persisted = repo.append_tick(tick)
        duplicate = repo.append_tick(tick.model_copy(update={"raw_payload": {"changed": True}}))
        listed_by_instrument = repo.list_by_instrument(
            "SHFE",
            "au2606",
            datetime(2026, 6, 7, 8, tzinfo=UTC),
            datetime(2026, 6, 7, 10, tzinfo=UTC),
        )
        listed_by_day = repo.list_by_trading_day("SHFE", "au2606", date(2026, 6, 7))

    assert persisted == tick
    assert duplicate == tick
    assert listed_by_instrument == [tick]
    assert listed_by_day == [tick]


def test_market_tick_repository_conflict_excludes_raw_payload(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repo = SQLAlchemyMarketTickRepository(session)
        tick = _market_tick(raw_payload={"diagnostic": "first"})
        repo.append_tick(tick)

        with pytest.raises(MarketDataConflictError):
            repo.append_tick(tick.model_copy(update={"price": Decimal("501")}))


def test_market_bar_repository_round_trip_lists_and_idempotency(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repo = SQLAlchemyMarketBarRepository(session)
        bar = _market_bar(raw_payload={"diagnostic": "first"})
        persisted = repo.append_bar(bar)
        duplicate = repo.append_bar(bar.model_copy(update={"raw_payload": {"changed": True}}))
        listed_by_instrument = repo.list_by_instrument(
            "SHFE",
            "au2606",
            BarTimeframe.M1,
            datetime(2026, 6, 7, 8, tzinfo=UTC),
            datetime(2026, 6, 7, 10, tzinfo=UTC),
        )
        listed_by_day = repo.list_by_trading_day(
            "SHFE",
            "au2606",
            BarTimeframe.M1,
            date(2026, 6, 7),
        )

    assert persisted == bar
    assert duplicate == bar
    assert listed_by_instrument == [bar]
    assert listed_by_day == [bar]


def test_market_bar_repository_conflict_excludes_raw_payload(
    db_session_factory: sessionmaker[Session],
) -> None:
    with db_session_factory.begin() as session:
        repo = SQLAlchemyMarketBarRepository(session)
        bar = _market_bar(raw_payload={"diagnostic": "first"})
        repo.append_bar(bar)

        with pytest.raises(MarketDataConflictError):
            repo.append_bar(bar.model_copy(update={"close": Decimal("502")}))
