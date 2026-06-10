from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from futures_mvp.domain.enums import Direction, Offset, PnLPriceBasis, PnLResultStatus
from futures_mvp.domain.models import CloseTradeContext, PnLSnapshot, Position, Trade
from futures_mvp.modules.pnl.calculator import calculate_realized_pnl, calculate_unrealized_pnl
from futures_mvp.modules.pnl.engine import PnLEngine

TRADING_DAY = date(2026, 1, 1)
CONFIG_HASH = "pnl-config-v1"


def _trade(
    *,
    direction: Direction = Direction.SELL,
    offset: Offset = Offset.CLOSE_TODAY,
    price: Decimal = Decimal("110"),
    fee_amount: Decimal | None = Decimal("2"),
    fee_currency: str | None = "CNY",
) -> Trade:
    return Trade(
        id="trade-1",
        account_id="acct-1",
        exchange="SHFE",
        exchange_trade_id="exchange-trade-1",
        order_id="order-1",
        instrument_id="rb2610",
        direction=direction,
        offset=offset,
        price=price,
        quantity=Decimal("1"),
        fee_amount=fee_amount,
        fee_currency=fee_currency,
        fee_source="EXCHANGE_REPORT" if fee_amount is not None else None,
        trade_time=datetime(2026, 1, 1, 9, tzinfo=UTC),
    )


def _context() -> CloseTradeContext:
    return CloseTradeContext(
        account_id="acct-1",
        instrument_id="rb2610",
        position_version=3,
        avg_cost=Decimal("100"),
        available_qty=Decimal("2"),
        contract_multiplier=Decimal("10"),
    )


def _position() -> Position:
    return Position(
        id="1",
        account_id="acct-1",
        instrument_id="rb2610",
        long_today_qty=Decimal("1"),
        long_yesterday_qty=Decimal("1"),
        short_today_qty=Decimal("1"),
        long_avg_price=Decimal("100"),
        short_avg_price=Decimal("120"),
        realized_pnl=Decimal("10"),
        version=3,
    )


def test_long_close_realized_pnl_with_known_and_zero_fee() -> None:
    known = calculate_realized_pnl(
        _trade(fee_amount=Decimal("2"), fee_currency="CNY"),
        _context(),
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
    )
    zero = calculate_realized_pnl(
        _trade(fee_amount=Decimal("0"), fee_currency="CNY"),
        _context(),
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
    )

    assert known.status == PnLResultStatus.CALCULATED
    assert known.realized is not None
    assert known.realized.gross_realized_pnl == Decimal("100")
    assert known.realized.net_realized_pnl == Decimal("98")
    assert zero.realized is not None
    assert zero.realized.net_realized_pnl == Decimal("100")


def test_short_close_realized_pnl_and_fee_unknown() -> None:
    result = calculate_realized_pnl(
        _trade(direction=Direction.BUY, price=Decimal("90"), fee_amount=None, fee_currency=None),
        _context(),
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
    )

    assert result.status == PnLResultStatus.CALCULATED
    assert result.reason == "fee_unknown"
    assert result.realized is not None
    assert result.realized.gross_realized_pnl == Decimal("100")
    assert result.realized.net_realized_pnl is None


def test_open_trade_returns_unsupported_and_identity_mismatch_errors() -> None:
    unsupported = calculate_realized_pnl(
        _trade(offset=Offset.OPEN),
        _context(),
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
    )
    mismatch = calculate_realized_pnl(
        _trade(),
        _context().model_copy(update={"instrument_id": "ag2610"}),
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
    )

    assert unsupported.status == PnLResultStatus.DOMAIN_FIELD_UNSUPPORTED
    assert mismatch.status == PnLResultStatus.ERROR
    assert mismatch.reason == "pnl_identity_mismatch: instrument_id"


def test_unrealized_pnl_for_long_short_mixed_position() -> None:
    result = calculate_unrealized_pnl(
        _position(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("110"),
        contract_multiplier=Decimal("10"),
    )

    assert result.status == PnLResultStatus.CALCULATED
    assert result.unrealized is not None
    assert result.unrealized.long_qty == Decimal("2")
    assert result.unrealized.short_qty == Decimal("1")
    assert result.unrealized.gross_unrealized_pnl == Decimal("300")
    assert result.unrealized.net_unrealized_pnl == Decimal("300")


def test_unrealized_missing_inputs_return_typed_results() -> None:
    assert (
        calculate_unrealized_pnl(
            None,
            price_basis=PnLPriceBasis.LAST_PRICE,
            mark_price=Decimal("110"),
            contract_multiplier=Decimal("10"),
        ).status
        == PnLResultStatus.REJECTED_MISSING_POSITION
    )
    assert (
        calculate_unrealized_pnl(
            _position(),
            price_basis=PnLPriceBasis.SETTLEMENT_PRICE,
            mark_price=None,
            contract_multiplier=Decimal("10"),
        ).status
        == PnLResultStatus.REJECTED_MISSING_PRICE
    )
    assert (
        calculate_unrealized_pnl(
            _position(),
            price_basis=PnLPriceBasis.MANUAL,
            mark_price=Decimal("110"),
            contract_multiplier=None,
        ).status
        == PnLResultStatus.REJECTED_MISSING_MULTIPLIER
    )


def test_engine_rejected_result_does_not_persist_or_update() -> None:
    uow = FakeUnitOfWork()
    engine = PnLEngine(lambda: uow)

    result = engine.calculate_pnl(
        _position(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=None,
        contract_multiplier=Decimal("10"),
        calculation_key="acct-1:rb2610:3:pnl",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )

    assert result.status == PnLResultStatus.REJECTED_MISSING_PRICE
    assert uow.pnl_snapshots.snapshots == []
    assert uow.positions.pnl_updates == []
    assert uow.committed is False


def test_engine_calculated_result_persists_snapshot_and_updates_pnl_only() -> None:
    uow = FakeUnitOfWork()
    engine = PnLEngine(lambda: uow)

    result = engine.calculate_pnl(
        _position(),
        trade=_trade(),
        close_context=_context(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("110"),
        contract_multiplier=Decimal("10"),
        calculation_key="acct-1:rb2610:3:pnl",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )

    assert result.status == PnLResultStatus.CALCULATED
    assert result.snapshot is not None
    assert result.snapshot.realized_pnl == Decimal("108")
    assert result.snapshot.unrealized_pnl == Decimal("300")
    assert uow.pnl_snapshots.snapshots == [result.snapshot]
    assert uow.positions.pnl_updates == [
        ("acct-1", "rb2610", Decimal("108"), Decimal("300"), 3)
    ]
    assert uow.committed is True


def test_engine_duplicate_same_canonical_is_noop_without_position_update() -> None:
    uow = FakeUnitOfWork()
    engine = PnLEngine(lambda: uow)
    first = engine.calculate_pnl(
        _position(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("110"),
        contract_multiplier=Decimal("10"),
        calculation_key="acct-1:rb2610:3:pnl",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )
    assert first.snapshot is not None
    uow.positions.pnl_updates.clear()
    uow.committed = False

    duplicate = engine.calculate_pnl(
        _position(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("110"),
        contract_multiplier=Decimal("10"),
        calculation_key="acct-1:rb2610:3:pnl",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )

    assert duplicate.status == PnLResultStatus.CALCULATED
    assert duplicate.snapshot == first.snapshot
    assert len(uow.pnl_snapshots.snapshots) == 1
    assert uow.positions.pnl_updates == []
    assert uow.committed is False


def test_engine_duplicate_different_canonical_conflicts_without_position_update() -> None:
    uow = FakeUnitOfWork()
    engine = PnLEngine(lambda: uow)
    first = engine.calculate_pnl(
        _position(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("110"),
        contract_multiplier=Decimal("10"),
        calculation_key="acct-1:rb2610:3:pnl",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )
    assert first.snapshot is not None
    uow.positions.pnl_updates.clear()

    duplicate = engine.calculate_pnl(
        _position(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("111"),
        contract_multiplier=Decimal("10"),
        calculation_key="acct-1:rb2610:3:pnl",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )

    assert duplicate.status == PnLResultStatus.CONFLICT
    assert duplicate.snapshot == first.snapshot
    assert len(uow.pnl_snapshots.snapshots) == 1
    assert uow.positions.pnl_updates == []


def test_engine_rejects_fee_unknown_for_persistent_projection() -> None:
    uow = FakeUnitOfWork()
    engine = PnLEngine(lambda: uow)

    result = engine.calculate_pnl(
        _position(),
        trade=_trade(fee_amount=None, fee_currency=None),
        close_context=_context(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("110"),
        contract_multiplier=Decimal("10"),
        calculation_key="acct-1:rb2610:3:pnl",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )

    assert result.status == PnLResultStatus.REJECTED_MISSING_FEE
    assert result.reason == "fee_unknown"
    assert result.realized is not None
    assert result.realized.gross_realized_pnl == Decimal("100")
    assert result.realized.net_realized_pnl is None
    assert result.snapshot is None
    assert uow.pnl_snapshots.snapshots == []
    assert uow.positions.pnl_updates == []


def test_engine_missing_trading_day_or_config_hash_rejects_before_persistence() -> None:
    missing_day_uow = FakeUnitOfWork()
    missing_config_uow = FakeUnitOfWork()

    missing_day = PnLEngine(lambda: missing_day_uow).calculate_pnl(
        _position(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("110"),
        contract_multiplier=Decimal("10"),
        calculation_key="acct-1:rb2610:3:pnl",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        config_hash=CONFIG_HASH,
    )
    missing_config = PnLEngine(lambda: missing_config_uow).calculate_pnl(
        _position(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("110"),
        contract_multiplier=Decimal("10"),
        calculation_key="acct-1:rb2610:3:pnl",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash="",
    )

    assert missing_day.status == PnLResultStatus.ERROR
    assert missing_day.reason == "trading_day is required"
    assert missing_day_uow.pnl_snapshots.snapshots == []
    assert missing_config.status == PnLResultStatus.ERROR
    assert missing_config.reason == "config_hash is required"
    assert missing_config_uow.pnl_snapshots.snapshots == []


def test_engine_missing_position_rejects_before_uow() -> None:
    uow = FakeUnitOfWork()
    engine = PnLEngine(lambda: uow)

    result = engine.calculate_pnl(
        None,
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("110"),
        contract_multiplier=Decimal("10"),
        calculation_key="acct-1:rb2610:3:pnl",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )

    assert result.status == PnLResultStatus.ERROR
    assert result.reason == "missing_position"
    assert uow.entered is False
    assert uow.pnl_snapshots.snapshots == []
    assert uow.positions.pnl_updates == []
    assert uow.committed is False


def test_engine_stale_position_version_rejects_before_persistence() -> None:
    uow = FakeUnitOfWork(live_position=_position().model_copy(update={"version": 4}))
    engine = PnLEngine(lambda: uow)

    result = engine.calculate_pnl(
        _position(),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("110"),
        contract_multiplier=Decimal("10"),
        calculation_key="acct-1:rb2610:3:pnl",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )

    assert result.status == PnLResultStatus.ERROR
    assert result.reason == "stale_position_version"
    assert uow.pnl_snapshots.snapshots == []
    assert uow.positions.pnl_updates == []
    assert uow.committed is False


def test_pnl_module_boundaries() -> None:
    sources = "\n".join(
        path.read_text() for path in Path("src/futures_mvp/modules/pnl").glob("*.py")
    )
    forbidden = {
        "futures_mvp.modules.oms",
        "futures_mvp.modules.risk",
        "futures_mvp.modules.execution",
        "futures_mvp.modules.margin",
        "futures_mvp.modules.settlement",
        "broker",
        "runtime",
        "OrderStatus",
        "OrderEvent",
        "ExchangeReport",
        "raw_payload",
    }
    assert not any(pattern in sources for pattern in forbidden)


class FakePnLSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: list[PnLSnapshot] = []

    def append_pnl_snapshot(self, snapshot: PnLSnapshot) -> PnLSnapshot:
        existing = self.get_by_calculation_key(
            snapshot.account_id,
            snapshot.instrument_id,
            snapshot.calculation_key,
        )
        if existing is not None:
            return existing
        self.snapshots.append(snapshot)
        return snapshot

    def get_latest(self, account_id: str, instrument_id: str) -> PnLSnapshot | None:
        del account_id, instrument_id
        return None

    def list_by_account(self, account_id: str) -> list[PnLSnapshot]:
        del account_id
        return []

    def get_by_calculation_key(
        self,
        account_id: str,
        instrument_id: str,
        calculation_key: str,
    ) -> PnLSnapshot | None:
        return next(
            (
                snapshot
                for snapshot in self.snapshots
                if snapshot.account_id == account_id
                and snapshot.instrument_id == instrument_id
                and snapshot.calculation_key == calculation_key
            ),
            None,
        )

    def get_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> PnLSnapshot | None:
        return next(
            (
                snapshot
                for snapshot in self.snapshots
                if snapshot.account_id == account_id
                and snapshot.instrument_id == instrument_id
                and snapshot.position_version == position_version
            ),
            None,
        )

    def get_by_accounting_identity(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
        trading_day: date,
        config_hash: str,
    ) -> PnLSnapshot | None:
        return next(
            (
                snapshot
                for snapshot in self.snapshots
                if snapshot.account_id == account_id
                and snapshot.instrument_id == instrument_id
                and snapshot.position_version == position_version
                and snapshot.trading_day == trading_day
                and snapshot.config_hash == config_hash
            ),
            None,
        )


class FakePositionRepository:
    def __init__(self, live_position: Position | None = None) -> None:
        self.live_position = live_position
        self.pnl_updates: list[tuple[str, str, Decimal, Decimal, int | None]] = []

    def get_by_account_instrument(self, account_id: str, instrument_id: str) -> Position | None:
        if (
            self.live_position is not None
            and self.live_position.account_id == account_id
            and self.live_position.instrument_id == instrument_id
        ):
            return self.live_position
        return None

    def update_pnl(
        self,
        account_id: str,
        instrument_id: str,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal,
        *,
        expected_version: int | None = None,
    ) -> Position:
        self.pnl_updates.append(
            (account_id, instrument_id, realized_pnl, unrealized_pnl, expected_version)
        )
        return Position(
            id="1",
            account_id=account_id,
            instrument_id=instrument_id,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            version=expected_version or 0,
        )


class FakeUnitOfWork:
    def __init__(self, live_position: Position | None = None) -> None:
        self.pnl_snapshots = FakePnLSnapshotRepository()
        self.positions = FakePositionRepository(live_position or _position())
        self.committed = False
        self.entered = False

    def __enter__(self) -> "FakeUnitOfWork":
        self.entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> bool | None:
        del exc_type, exc, tb
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.committed = False
