from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from futures_mvp.domain.enums import MarginResultStatus
from futures_mvp.domain.models import (
    AccountContext,
    MarginResult,
    MarginRule,
    MarginSnapshot,
    Position,
)
from futures_mvp.interfaces.repositories import (
    MarginSnapshotConflictError,
    OptimisticLockError,
    RepositoryError,
    UnitOfWork,
)
from futures_mvp.modules.margin.calculator import MarginCalculator, resolve_margin_prices


class MarginEngine:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        calculator: MarginCalculator | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._calculator = calculator or MarginCalculator()

    def calculate_margin(
        self,
        position: Position | None,
        rule: MarginRule | None,
        account: AccountContext,
        *,
        calculation_key: str,
        calculated_at: datetime,
        latest_price: Decimal | None = None,
        settlement_price: Decimal | None = None,
    ) -> MarginResult:
        if not calculation_key:
            return MarginResult(
                status=MarginResultStatus.ERROR,
                reason="calculation_key is required",
                account_id=position.account_id if position else account.account_id,
                instrument_id=position.instrument_id if position else None,
            )
        with self._uow_factory() as uow:
            return self._calculate_and_persist(
                uow,
                position,
                rule,
                account,
                calculation_key=calculation_key,
                calculated_at=calculated_at,
                latest_price=latest_price,
                settlement_price=settlement_price,
                replay=False,
            )

    def replay_margin(
        self,
        position: Position | None,
        rule: MarginRule | None,
        account: AccountContext,
        *,
        calculation_key: str,
        calculated_at: datetime,
        latest_price: Decimal | None = None,
        settlement_price: Decimal | None = None,
    ) -> MarginResult:
        if not calculation_key:
            return MarginResult(
                status=MarginResultStatus.ERROR,
                reason="calculation_key is required",
                account_id=position.account_id if position else account.account_id,
                instrument_id=position.instrument_id if position else None,
            )
        with self._uow_factory() as uow:
            return self._calculate_and_persist(
                uow,
                position,
                rule,
                account,
                calculation_key=calculation_key,
                calculated_at=calculated_at,
                latest_price=latest_price,
                settlement_price=settlement_price,
                replay=True,
            )

    def _calculate_and_persist(
        self,
        uow: UnitOfWork,
        position: Position | None,
        rule: MarginRule | None,
        account: AccountContext,
        *,
        calculation_key: str,
        calculated_at: datetime,
        latest_price: Decimal | None,
        settlement_price: Decimal | None,
        replay: bool,
    ) -> MarginResult:
        calculated = self._calculator.calculate(
            position,
            rule,
            account,
            latest_price=latest_price,
            settlement_price=settlement_price,
        )
        if calculated.status is not MarginResultStatus.CALCULATED:
            return calculated
        if position is None or rule is None or calculated.requirement is None:
            return MarginResult(
                status=MarginResultStatus.ERROR,
                reason="margin calculation returned incomplete calculated result",
                account_id=calculated.account_id,
                instrument_id=calculated.instrument_id,
            )

        snapshot = _build_snapshot(
            position,
            rule,
            account,
            calculated.requirement.margin_used,
            calculated.requirement.total_maintenance_margin,
            calculation_key=calculation_key,
            calculated_at=calculated_at,
            latest_price=latest_price,
            settlement_price=settlement_price,
        )
        if snapshot is None:
            return MarginResult(
                status=MarginResultStatus.REJECTED_MISSING_PRICE,
                reason="missing_margin_price",
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )

        existing_snapshot = uow.margin_snapshots.get_by_position_version(
            snapshot.account_id,
            snapshot.instrument_id,
            snapshot.position_version,
        )
        if existing_snapshot is not None:
            if not _same_snapshot_position_version_facts(existing_snapshot, snapshot):
                reason = (
                    "margin_snapshot_replay_diverged"
                    if replay
                    else "margin_snapshot_position_version_diverged"
                )
                return _conflict_result(position, existing_snapshot, reason)
            if replay and position.margin_used != existing_snapshot.margin_used:
                return _conflict_result(
                    position,
                    existing_snapshot,
                    "position_margin_used_diverged_from_snapshot",
                )
            return MarginResult(
                status=MarginResultStatus.CALCULATED,
                requirement=calculated.requirement,
                snapshot=existing_snapshot,
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )

        try:
            appended_snapshot = uow.margin_snapshots.append_margin_snapshot(snapshot)
            uow.positions.update_margin_used(
                position.account_id,
                position.instrument_id,
                appended_snapshot.margin_used,
                expected_version=position.version,
            )
        except MarginSnapshotConflictError as exc:
            uow.rollback()
            return MarginResult(
                status=MarginResultStatus.CONFLICT,
                requirement=calculated.requirement,
                reason=str(exc),
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )
        except (OptimisticLockError, RepositoryError, ValueError) as exc:
            uow.rollback()
            return MarginResult(
                status=MarginResultStatus.ERROR,
                requirement=calculated.requirement,
                reason=str(exc),
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )

        uow.commit()
        return MarginResult(
            status=MarginResultStatus.CALCULATED,
            requirement=calculated.requirement,
            snapshot=appended_snapshot,
            account_id=position.account_id,
            instrument_id=position.instrument_id,
        )


def _build_snapshot(
    position: Position,
    rule: MarginRule,
    account: AccountContext,
    initial_margin: Decimal,
    maintenance_margin: Decimal,
    *,
    calculation_key: str,
    calculated_at: datetime,
    latest_price: Decimal | None,
    settlement_price: Decimal | None,
) -> MarginSnapshot | None:
    prices = resolve_margin_prices(
        position,
        rule,
        latest_price=latest_price,
        settlement_price=settlement_price,
    )
    if prices is None:
        return None
    return MarginSnapshot(
        account_id=position.account_id,
        instrument_id=position.instrument_id,
        position_version=position.version,
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        calculation_key=calculation_key,
        long_qty=position.long_today_qty + position.long_yesterday_qty,
        short_qty=position.short_today_qty + position.short_yesterday_qty,
        price=prices.snapshot_price,
        contract_multiplier=rule.contract_multiplier,
        initial_margin=initial_margin,
        maintenance_margin=maintenance_margin,
        margin_used=initial_margin,
        available_cash=account.available_cash,
        equity=account.equity,
        calculated_at=calculated_at,
    )


def _same_snapshot_position_version_facts(left: MarginSnapshot, right: MarginSnapshot) -> bool:
    return (
        left.account_id,
        left.instrument_id,
        left.position_version,
        left.rule_id,
        left.rule_version,
        left.long_qty,
        left.short_qty,
        left.price,
        left.contract_multiplier,
        left.initial_margin,
        left.maintenance_margin,
        left.margin_used,
        left.available_cash,
        left.equity,
    ) == (
        right.account_id,
        right.instrument_id,
        right.position_version,
        right.rule_id,
        right.rule_version,
        right.long_qty,
        right.short_qty,
        right.price,
        right.contract_multiplier,
        right.initial_margin,
        right.maintenance_margin,
        right.margin_used,
        right.available_cash,
        right.equity,
    )


def _conflict_result(
    position: Position,
    snapshot: MarginSnapshot,
    reason: str,
) -> MarginResult:
    return MarginResult(
        status=MarginResultStatus.CONFLICT,
        snapshot=snapshot,
        reason=reason,
        account_id=position.account_id,
        instrument_id=position.instrument_id,
    )
