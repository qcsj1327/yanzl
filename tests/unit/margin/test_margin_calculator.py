from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from futures_mvp.domain.enums import MarginPriceBasis, MarginResultStatus
from futures_mvp.domain.models import AccountContext, MarginRule, MarginSnapshot, Position
from futures_mvp.modules.margin.calculator import MarginCalculator, resolve_margin_prices
from futures_mvp.modules.margin.engine import MarginEngine

TRADING_DAY = date(2026, 1, 1)
CONFIG_HASH = "margin-config-v1"


def _account(available_cash: Decimal = Decimal("100000")) -> AccountContext:
    return AccountContext(
        account_id="acct-1",
        equity=Decimal("200000"),
        available_cash=available_cash,
        frozen_cash=Decimal("0"),
        snapshot_time=datetime(2026, 1, 1, 9, tzinfo=UTC),
    )


def _position() -> Position:
    return Position(
        id="1",
        account_id="acct-1",
        instrument_id="rb2610",
        long_today_qty=Decimal("1"),
        long_yesterday_qty=Decimal("2"),
        short_today_qty=Decimal("1"),
        short_yesterday_qty=Decimal("0"),
        long_avg_price=Decimal("100"),
        short_avg_price=Decimal("80"),
        version=3,
    )


def _rule(
    price_basis: MarginPriceBasis = MarginPriceBasis.MANUAL,
    *,
    price: Decimal | None = Decimal("100"),
) -> MarginRule:
    return MarginRule(
        rule_id="rule-1",
        rule_version="v1",
        instrument_id="rb2610",
        exchange="SHFE",
        contract_multiplier=Decimal("10"),
        long_initial_margin_rate=Decimal("0.10"),
        short_initial_margin_rate=Decimal("0.20"),
        long_maintenance_margin_rate=Decimal("0.05"),
        short_maintenance_margin_rate=Decimal("0.10"),
        price_basis=price_basis,
        price=price,
    )


def test_manual_price_calculates_long_short_mixed_margin() -> None:
    result = MarginCalculator().calculate(_position(), _rule(), _account())

    assert result.status == MarginResultStatus.CALCULATED
    assert result.requirement is not None
    assert result.requirement.long_initial_margin == Decimal("300.00")
    assert result.requirement.short_initial_margin == Decimal("200.00")
    assert result.requirement.total_initial_margin == Decimal("500.00")
    assert result.requirement.long_maintenance_margin == Decimal("150.00")
    assert result.requirement.short_maintenance_margin == Decimal("100.00")
    assert result.requirement.total_maintenance_margin == Decimal("250.00")
    assert result.requirement.margin_used == Decimal("500.00")
    assert result.requirement.required_cash == Decimal("500.00")
    assert result.requirement.is_sufficient is True


def test_today_and_yesterday_quantities_feed_margin() -> None:
    result = MarginCalculator().calculate(
        Position(
            id="1",
            account_id="acct-1",
            instrument_id="rb2610",
            long_today_qty=Decimal("1"),
            long_yesterday_qty=Decimal("1"),
            version=1,
        ),
        _rule(),
        _account(),
    )

    assert result.requirement is not None
    assert result.requirement.long_initial_margin == Decimal("200.00")


def test_insufficient_cash_returns_typed_result_with_requirement() -> None:
    result = MarginCalculator().calculate(_position(), _rule(), _account(Decimal("10")))

    assert result.status == MarginResultStatus.REJECTED_INSUFFICIENT_CASH
    assert result.requirement is not None
    assert result.requirement.is_sufficient is False
    assert result.reason == "insufficient_cash"


def test_missing_rule_position_and_price_return_typed_results() -> None:
    calculator = MarginCalculator()

    assert (
        calculator.calculate(None, _rule(), _account()).status
        == MarginResultStatus.REJECTED_MISSING_POSITION
    )
    assert (
        calculator.calculate(_position(), None, _account()).status
        == MarginResultStatus.REJECTED_MISSING_RULE
    )
    assert (
        calculator.calculate(
            _position(),
            _rule(MarginPriceBasis.MANUAL, price=None),
            _account(),
        ).status
        == MarginResultStatus.REJECTED_MISSING_PRICE
    )


def test_last_and_settlement_price_use_typed_price_inputs() -> None:
    calculator = MarginCalculator()

    last_result = calculator.calculate(
        _position(),
        _rule(MarginPriceBasis.LAST_PRICE, price=None),
        _account(),
        latest_price=Decimal("110"),
    )
    settlement_result = calculator.calculate(
        _position(),
        _rule(MarginPriceBasis.SETTLEMENT_PRICE, price=None),
        _account(),
        settlement_price=Decimal("90"),
    )

    assert last_result.requirement is not None
    assert settlement_result.requirement is not None
    assert last_result.requirement.total_initial_margin == Decimal("550.00")
    assert settlement_result.requirement.total_initial_margin == Decimal("450.00")


def test_avg_price_uses_side_prices_for_mixed_position() -> None:
    position = _position()
    rule = _rule(MarginPriceBasis.AVG_PRICE, price=None)
    result = MarginCalculator().calculate(position, rule, _account())
    resolved_prices = resolve_margin_prices(position, rule)

    assert result.status == MarginResultStatus.CALCULATED
    assert result.requirement is not None
    assert result.requirement.long_initial_margin == Decimal("300.00")
    assert result.requirement.short_initial_margin == Decimal("160.00")
    assert result.requirement.total_initial_margin == Decimal("460.00")
    assert resolved_prices is not None
    assert resolved_prices.snapshot_price == Decimal("95")


def test_avg_price_missing_side_avg_rejects() -> None:
    position = _position().model_copy(update={"short_avg_price": Decimal("0")})

    result = MarginCalculator().calculate(
        position,
        _rule(MarginPriceBasis.AVG_PRICE, price=None),
        _account(),
    )

    assert result.status == MarginResultStatus.REJECTED_MISSING_PRICE


def test_calculator_does_not_mutate_position() -> None:
    position = _position()

    MarginCalculator().calculate(position, _rule(), _account())

    assert position == _position()


def test_identity_mismatch_returns_typed_error() -> None:
    calculator = MarginCalculator()

    account_result = calculator.calculate(
        _position(),
        _rule(),
        _account().model_copy(update={"account_id": "acct-2"}),
    )
    instrument_result = calculator.calculate(
        _position(),
        _rule().model_copy(update={"instrument_id": "ag2610"}),
        _account(),
    )

    assert account_result.status == MarginResultStatus.ERROR
    assert account_result.reason == "margin_identity_mismatch: account_id"
    assert instrument_result.status == MarginResultStatus.ERROR
    assert instrument_result.reason == "margin_identity_mismatch: instrument_id"


def test_engine_rejected_calculator_result_does_not_persist_or_update() -> None:
    uow = FakeUnitOfWork()
    engine = MarginEngine(lambda: uow)

    result = engine.calculate_margin(
        _position(),
        _rule(MarginPriceBasis.MANUAL, price=None),
        _account(),
        calculation_key="acct-1:rb2610:3:v1",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )

    assert result.status == MarginResultStatus.REJECTED_MISSING_PRICE
    assert uow.margin_snapshots.snapshots == []
    assert uow.positions.updated == []
    assert uow.committed is False


def test_engine_identity_mismatch_does_not_persist_or_update() -> None:
    uow = FakeUnitOfWork()
    engine = MarginEngine(lambda: uow)

    result = engine.calculate_margin(
        _position(),
        _rule().model_copy(update={"instrument_id": "ag2610"}),
        _account(),
        calculation_key="acct-1:rb2610:3:v1",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )

    assert result.status == MarginResultStatus.ERROR
    assert result.reason == "margin_identity_mismatch: instrument_id"
    assert uow.margin_snapshots.snapshots == []
    assert uow.positions.updated == []
    assert uow.committed is False


def test_engine_missing_trading_day_or_config_hash_rejects_before_persistence() -> None:
    missing_day_uow = FakeUnitOfWork()
    missing_config_uow = FakeUnitOfWork()

    missing_day = MarginEngine(lambda: missing_day_uow).calculate_margin(
        _position(),
        _rule(),
        _account(),
        calculation_key="acct-1:rb2610:3:v1",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        config_hash=CONFIG_HASH,
    )
    missing_config = MarginEngine(lambda: missing_config_uow).calculate_margin(
        _position(),
        _rule(),
        _account(),
        calculation_key="acct-1:rb2610:3:v1",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash="",
    )

    assert missing_day.status == MarginResultStatus.ERROR
    assert missing_day.reason == "trading_day is required"
    assert missing_day_uow.margin_snapshots.snapshots == []
    assert missing_config.status == MarginResultStatus.ERROR
    assert missing_config.reason == "config_hash is required"
    assert missing_config_uow.margin_snapshots.snapshots == []


def test_engine_missing_position_rejects_before_uow() -> None:
    uow = FakeUnitOfWork()
    engine = MarginEngine(lambda: uow)

    result = engine.calculate_margin(
        None,
        _rule(),
        _account(),
        calculation_key="acct-1:rb2610:3:v1",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )

    assert result.status == MarginResultStatus.ERROR
    assert result.reason == "missing_position"
    assert uow.entered is False
    assert uow.margin_snapshots.snapshots == []
    assert uow.positions.margin_updates == []
    assert uow.committed is False


def test_engine_stale_position_version_rejects_before_persistence() -> None:
    uow = FakeUnitOfWork(live_position=_position().model_copy(update={"version": 4}))
    engine = MarginEngine(lambda: uow)

    result = engine.calculate_margin(
        _position(),
        _rule(),
        _account(),
        calculation_key="acct-1:rb2610:3:v1",
        calculated_at=datetime(2026, 1, 1, 9, tzinfo=UTC),
        trading_day=TRADING_DAY,
        config_hash=CONFIG_HASH,
    )

    assert result.status == MarginResultStatus.ERROR
    assert result.reason == "stale_position_version"
    assert uow.margin_snapshots.snapshots == []
    assert uow.positions.margin_updates == []
    assert uow.committed is False


def test_margin_module_boundaries() -> None:
    sources = "\n".join(
        path.read_text()
        for path in Path("src/futures_mvp/modules/margin").glob("*.py")
    )

    forbidden = {
        "futures_mvp.modules.oms",
        "futures_mvp.modules.risk",
        "futures_mvp.modules.execution",
        "futures_mvp.modules.pnl",
        "futures_mvp.modules.settlement",
        "broker",
        "runtime",
        "OrderStatus",
        "OrderEvent",
        "ExchangeReport",
        "raw_payload",
    }
    assert not any(pattern in sources for pattern in forbidden)


class FakeMarginSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: list[MarginSnapshot] = []

    def append_margin_snapshot(self, snapshot: MarginSnapshot) -> MarginSnapshot:
        self.snapshots.append(snapshot)
        return snapshot

    def get_latest(self, account_id: str, instrument_id: str) -> MarginSnapshot | None:
        del account_id, instrument_id
        return None

    def list_by_account(self, account_id: str) -> list[MarginSnapshot]:
        del account_id
        return []

    def get_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> MarginSnapshot | None:
        del account_id, instrument_id, position_version
        return None

    def get_by_accounting_identity(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
        trading_day: date,
        config_hash: str,
    ) -> MarginSnapshot | None:
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
        self.updated: list[Position] = []
        self.margin_updates: list[tuple[str, str, Decimal, int | None]] = []

    def get_by_account_instrument(self, account_id: str, instrument_id: str) -> Position | None:
        if (
            self.live_position is not None
            and self.live_position.account_id == account_id
            and self.live_position.instrument_id == instrument_id
        ):
            return self.live_position
        return None

    def create_or_get_position(self, account_id: str, instrument_id: str) -> Position:
        return Position(id="1", account_id=account_id, instrument_id=instrument_id)

    def update_position(
        self,
        position: Position,
        *,
        expected_version: int | None = None,
    ) -> Position:
        del expected_version
        self.updated.append(position)
        return position

    def update_margin_used(
        self,
        account_id: str,
        instrument_id: str,
        margin_used: Decimal,
        *,
        expected_version: int | None = None,
    ) -> Position:
        self.margin_updates.append((account_id, instrument_id, margin_used, expected_version))
        return Position(
            id="1",
            account_id=account_id,
            instrument_id=instrument_id,
            margin_used=margin_used,
            version=expected_version or 0,
        )

    def list_by_account(self, account_id: str) -> list[Position]:
        del account_id
        return []


class FakeUnitOfWork:
    def __init__(self, live_position: Position | None = None) -> None:
        self.margin_snapshots = FakeMarginSnapshotRepository()
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
