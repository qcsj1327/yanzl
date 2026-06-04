from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from futures_mvp.domain.enums import PnLPriceBasis, SettlementResultStatus
from futures_mvp.domain.models import (
    AccountContext,
    AccountSnapshot,
    MarginSnapshot,
    PnLSnapshot,
    Position,
    SettlementContext,
    SettlementPrice,
)
from futures_mvp.modules.settlement.calculator import SettlementCalculator, SettlementPlan
from futures_mvp.modules.settlement.engine import SettlementEngine


def _position(*, frozen: bool = False, version: int = 1) -> Position:
    return Position(
        id="1",
        account_id="acct-1",
        instrument_id="rb2610",
        long_today_qty=Decimal("2"),
        long_yesterday_qty=Decimal("3"),
        short_today_qty=Decimal("1"),
        short_yesterday_qty=Decimal("4"),
        frozen_long_qty=Decimal("1") if frozen else Decimal("0"),
        long_avg_price=Decimal("3000"),
        short_avg_price=Decimal("3100"),
        realized_pnl=Decimal("10"),
        unrealized_pnl=Decimal("20"),
        margin_used=Decimal("500"),
        version=version,
    )


def _pnl_snapshot(
    *,
    snapshot_id: str = "1",
    account_id: str = "acct-1",
    position_version: int = 1,
) -> PnLSnapshot:
    return PnLSnapshot(
        id=snapshot_id,
        account_id=account_id,
        instrument_id="rb2610",
        position_version=position_version,
        margin_snapshot_id="1",
        calculation_key="pnl-key",
        price_basis=PnLPriceBasis.SETTLEMENT_PRICE,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        realized_pnl=Decimal("100"),
        unrealized_pnl=Decimal("50"),
        total_pnl=Decimal("150"),
        calculated_at=datetime(2026, 6, 4, 15, tzinfo=UTC),
    )


def _margin_snapshot(
    *,
    snapshot_id: str = "1",
    account_id: str = "acct-1",
    position_version: int = 1,
) -> MarginSnapshot:
    return MarginSnapshot(
        id=snapshot_id,
        account_id=account_id,
        instrument_id="rb2610",
        position_version=position_version,
        calculation_key="margin-key",
        long_qty=Decimal("5"),
        short_qty=Decimal("5"),
        price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        initial_margin=Decimal("3500"),
        maintenance_margin=Decimal("2000"),
        margin_used=Decimal("3500"),
        available_cash=Decimal("10000"),
        equity=Decimal("20000"),
        calculated_at=datetime(2026, 6, 4, 15, tzinfo=UTC),
    )


def _context(
    *,
    position: Position | None = None,
    pnl_snapshots: tuple[PnLSnapshot, ...] | None = None,
    margin_snapshots: tuple[MarginSnapshot, ...] | None = None,
) -> SettlementContext:
    return SettlementContext(
        account_id="acct-1",
        trading_day=date(2026, 6, 4),
        account_before=AccountContext(
            account_id="acct-1",
            equity=Decimal("10000"),
            available_cash=Decimal("6500"),
            frozen_cash=Decimal("0"),
            snapshot_time=datetime(2026, 6, 4, 14, tzinfo=UTC),
        ),
        positions=(position or _position(),),
        pnl_snapshots=pnl_snapshots if pnl_snapshots is not None else (_pnl_snapshot(),),
        margin_snapshots=margin_snapshots
        if margin_snapshots is not None
        else (_margin_snapshot(),),
        settlement_prices=(
            SettlementPrice(
                instrument_id="rb2610",
                exchange="SHFE",
                trading_day=date(2026, 6, 4),
                price=Decimal("3500"),
                received_at=datetime(2026, 6, 4, 14, tzinfo=UTC),
            ),
        ),
        calculation_key="acct-1:2026-06-04:settlement",
        settled_at=datetime(2026, 6, 4, 15, tzinfo=UTC),
    )


class FakePositions:
    def __init__(self, position: Position) -> None:
        self.position = position
        self.roll_count = 0

    def get_by_account_instrument(self, account_id: str, instrument_id: str) -> Position | None:
        if self.position.account_id == account_id and self.position.instrument_id == instrument_id:
            return self.position
        return None

    def roll_today_to_yesterday_for_settlement(
        self,
        account_id: str,
        instrument_id: str,
        *,
        expected_version: int,
    ) -> Position:
        assert self.position.account_id == account_id
        assert self.position.instrument_id == instrument_id
        assert self.position.version == expected_version
        self.roll_count += 1
        self.position = self.position.model_copy(
            update={
                "long_yesterday_qty": self.position.long_yesterday_qty
                + self.position.long_today_qty,
                "short_yesterday_qty": self.position.short_yesterday_qty
                + self.position.short_today_qty,
                "long_today_qty": Decimal("0"),
                "short_today_qty": Decimal("0"),
                "version": self.position.version + 1,
            }
        )
        return self.position


class FakeAccounts:
    def __init__(self) -> None:
        self.snapshots: list[AccountSnapshot] = []

    def append_account_snapshot(self, snapshot: AccountSnapshot) -> AccountSnapshot:
        saved = snapshot.model_copy(update={"id": str(len(self.snapshots) + 1)})
        self.snapshots.append(saved)
        return saved

    def get_by_id(self, snapshot_id: str) -> AccountSnapshot | None:
        return next((snapshot for snapshot in self.snapshots if snapshot.id == snapshot_id), None)

    def get_latest(self, account_id: str) -> AccountSnapshot | None:
        matches = [snapshot for snapshot in self.snapshots if snapshot.account_id == account_id]
        return matches[-1] if matches else None


class FakeSettlements:
    def __init__(self) -> None:
        self.snapshot = None
        self.append_count = 0

    def append_settlement_snapshot(self, snapshot):
        self.append_count += 1
        self.snapshot = snapshot
        return snapshot

    def get_by_account_trading_day(self, account_id, trading_day):
        del account_id, trading_day
        return self.snapshot


class FakeUow:
    def __init__(self, position: Position) -> None:
        self.positions = FakePositions(position)
        self.account_snapshots = FakeAccounts()
        self.settlement_snapshots = FakeSettlements()
        self.commit_count = 0
        self.rollback_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return None

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


def test_settlement_calculator_account_formula_and_today_roll() -> None:
    planned = SettlementCalculator().build_plan(_context())

    assert isinstance(planned, SettlementPlan)
    assert planned.snapshot.cash_before == Decimal("10000")
    assert planned.snapshot.cash_after == Decimal("10100")
    assert planned.equity_after == Decimal("10150")
    assert planned.available_cash_after == Decimal("6600")
    assert planned.snapshot.positions_after[0]["long_today_qty"] == "0"
    assert planned.snapshot.positions_after[0]["long_yesterday_qty"] == "5"
    assert planned.snapshot.positions_after[0]["short_today_qty"] == "0"
    assert planned.snapshot.positions_after[0]["short_yesterday_qty"] == "5"
    assert planned.snapshot.positions_after[0]["long_avg_price"] == "3000"
    assert planned.snapshot.positions_after[0]["realized_pnl"] == "10"
    assert planned.snapshot.positions_after[0]["margin_used"] == "500"


def test_settlement_calculator_rejects_frozen_qty_without_snapshot() -> None:
    result = SettlementCalculator().build_plan(_context(position=_position(frozen=True)))

    assert not isinstance(result, SettlementPlan)
    assert result.status == SettlementResultStatus.REJECTED_FROZEN_POSITION
    assert result.snapshot is None


def test_settlement_calculator_rejects_missing_pnl_and_margin() -> None:
    missing_pnl = SettlementCalculator().build_plan(_context(pnl_snapshots=()))
    missing_margin = SettlementCalculator().build_plan(_context(margin_snapshots=()))

    assert not isinstance(missing_pnl, SettlementPlan)
    assert missing_pnl.status == SettlementResultStatus.REJECTED_MISSING_PNL
    assert missing_pnl.snapshot is None
    assert not isinstance(missing_margin, SettlementPlan)
    assert missing_margin.status == SettlementResultStatus.REJECTED_MISSING_MARGIN
    assert missing_margin.snapshot is None


def test_settlement_calculator_conflicts_on_pnl_account_mismatch() -> None:
    result = SettlementCalculator().build_plan(
        _context(pnl_snapshots=(_pnl_snapshot(account_id="acct-2"),))
    )

    assert not isinstance(result, SettlementPlan)
    assert result.status == SettlementResultStatus.CONFLICT
    assert result.reason == "pnl_snapshot_identity_mismatch"
    assert result.snapshot is None


def test_settlement_calculator_conflicts_on_margin_account_mismatch() -> None:
    result = SettlementCalculator().build_plan(
        _context(margin_snapshots=(_margin_snapshot(account_id="acct-2"),))
    )

    assert not isinstance(result, SettlementPlan)
    assert result.status == SettlementResultStatus.CONFLICT
    assert result.reason == "margin_snapshot_identity_mismatch"
    assert result.snapshot is None


def test_settlement_calculator_conflicts_on_pnl_position_version_mismatch() -> None:
    result = SettlementCalculator().build_plan(
        _context(pnl_snapshots=(_pnl_snapshot(position_version=0),))
    )

    assert not isinstance(result, SettlementPlan)
    assert result.status == SettlementResultStatus.CONFLICT
    assert result.reason == "pnl_snapshot_identity_mismatch"
    assert result.snapshot is None


def test_settlement_calculator_conflicts_on_margin_position_version_mismatch() -> None:
    result = SettlementCalculator().build_plan(
        _context(margin_snapshots=(_margin_snapshot(position_version=0),))
    )

    assert not isinstance(result, SettlementPlan)
    assert result.status == SettlementResultStatus.CONFLICT
    assert result.reason == "margin_snapshot_identity_mismatch"
    assert result.snapshot is None


def test_settlement_calculator_conflicts_when_extra_same_instrument_fact_mismatches() -> None:
    result = SettlementCalculator().build_plan(
        _context(
            pnl_snapshots=(
                _pnl_snapshot(),
                _pnl_snapshot(snapshot_id="2", account_id="acct-2"),
            )
        )
    )

    assert not isinstance(result, SettlementPlan)
    assert result.status == SettlementResultStatus.CONFLICT
    assert result.reason == "pnl_snapshot_identity_mismatch"
    assert result.snapshot is None


@pytest.mark.parametrize(
    "context",
    [
        _context(pnl_snapshots=(_pnl_snapshot(account_id="acct-2"),)),
        _context(margin_snapshots=(_margin_snapshot(account_id="acct-2"),)),
        _context(pnl_snapshots=(_pnl_snapshot(position_version=0),)),
        _context(margin_snapshots=(_margin_snapshot(position_version=0),)),
    ],
)
def test_settlement_engine_identity_conflict_has_no_persistence(
    context: SettlementContext,
) -> None:
    uow = FakeUow(_position())
    engine = SettlementEngine(lambda: uow)

    result = engine.settle(context)

    assert result.status == SettlementResultStatus.CONFLICT
    assert result.snapshot is None
    assert uow.settlement_snapshots.append_count == 0
    assert uow.positions.roll_count == 0
    assert uow.account_snapshots.snapshots == []
    assert uow.commit_count == 0


def test_settlement_engine_duplicate_same_canonical_no_op() -> None:
    context = _context()
    uow = FakeUow(_position())
    engine = SettlementEngine(lambda: uow)

    first = engine.settle(context)
    second = engine.settle(context)

    assert first.status == SettlementResultStatus.SETTLED
    assert second.status == SettlementResultStatus.DUPLICATE
    assert uow.settlement_snapshots.append_count == 1
    assert uow.positions.roll_count == 1
    assert uow.commit_count == 1


def test_settlement_engine_replay_detects_live_position_divergence() -> None:
    context = _context()
    uow = FakeUow(_position())
    engine = SettlementEngine(lambda: uow)

    assert engine.settle(context).status == SettlementResultStatus.SETTLED
    uow.positions.position = uow.positions.position.model_copy(
        update={"long_yesterday_qty": Decimal("999")}
    )
    replay = engine.replay_settlement(context)

    assert replay.status == SettlementResultStatus.CONFLICT
    assert replay.reason == "live_position_diverged_from_settlement_snapshot"
    assert uow.settlement_snapshots.append_count == 1
