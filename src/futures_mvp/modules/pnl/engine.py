from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from futures_mvp.domain.enums import PnLPriceBasis, PnLResultStatus
from futures_mvp.domain.models import (
    CloseTradeContext,
    PnLResult,
    PnLSnapshot,
    Position,
    Trade,
)
from futures_mvp.interfaces.repositories import (
    OptimisticLockError,
    PnLSnapshotConflictError,
    RepositoryError,
    UnitOfWork,
)
from futures_mvp.modules.pnl.calculator import (
    calculate_realized_pnl,
    calculate_unrealized_pnl,
)


class PnLEngine:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def calculate_pnl(
        self,
        position: Position | None,
        *,
        price_basis: PnLPriceBasis,
        mark_price: Decimal | None,
        contract_multiplier: Decimal | None,
        calculation_key: str,
        calculated_at: datetime,
        trade: Trade | None = None,
        close_context: CloseTradeContext | None = None,
        margin_snapshot_id: str | None = None,
    ) -> PnLResult:
        if not calculation_key:
            return PnLResult(
                status=PnLResultStatus.ERROR,
                reason="calculation_key is required",
                account_id=position.account_id if position else None,
                instrument_id=position.instrument_id if position else None,
            )
        with self._uow_factory() as uow:
            return self._calculate_and_persist(
                uow,
                position,
                trade=trade,
                close_context=close_context,
                price_basis=price_basis,
                mark_price=mark_price,
                contract_multiplier=contract_multiplier,
                calculation_key=calculation_key,
                calculated_at=calculated_at,
                margin_snapshot_id=margin_snapshot_id,
                replay=False,
            )

    def replay_pnl(
        self,
        position: Position | None,
        *,
        price_basis: PnLPriceBasis,
        mark_price: Decimal | None,
        contract_multiplier: Decimal | None,
        calculation_key: str,
        calculated_at: datetime,
        trade: Trade | None = None,
        close_context: CloseTradeContext | None = None,
        margin_snapshot_id: str | None = None,
    ) -> PnLResult:
        if not calculation_key:
            return PnLResult(
                status=PnLResultStatus.ERROR,
                reason="calculation_key is required",
                account_id=position.account_id if position else None,
                instrument_id=position.instrument_id if position else None,
            )
        with self._uow_factory() as uow:
            return self._calculate_and_persist(
                uow,
                position,
                trade=trade,
                close_context=close_context,
                price_basis=price_basis,
                mark_price=mark_price,
                contract_multiplier=contract_multiplier,
                calculation_key=calculation_key,
                calculated_at=calculated_at,
                margin_snapshot_id=margin_snapshot_id,
                replay=True,
            )

    def _calculate_and_persist(
        self,
        uow: UnitOfWork,
        position: Position | None,
        *,
        trade: Trade | None,
        close_context: CloseTradeContext | None,
        price_basis: PnLPriceBasis,
        mark_price: Decimal | None,
        contract_multiplier: Decimal | None,
        calculation_key: str,
        calculated_at: datetime,
        margin_snapshot_id: str | None,
        replay: bool,
    ) -> PnLResult:
        unrealized_result = calculate_unrealized_pnl(
            position,
            price_basis=price_basis,
            mark_price=mark_price,
            contract_multiplier=contract_multiplier,
        )
        if unrealized_result.status is not PnLResultStatus.CALCULATED:
            return unrealized_result
        if position is None or unrealized_result.unrealized is None:
            return PnLResult(
                status=PnLResultStatus.ERROR,
                reason="pnl calculation returned incomplete unrealized result",
            )

        realized_result: PnLResult | None = None
        if trade is not None:
            if close_context is None:
                return PnLResult(
                    status=PnLResultStatus.REJECTED_MISSING_POSITION,
                    reason="missing_close_trade_context",
                    account_id=trade.account_id,
                    instrument_id=trade.instrument_id,
                )
            realized_result = calculate_realized_pnl(
                trade,
                close_context,
                calculated_at=calculated_at,
            )
            if realized_result.status is not PnLResultStatus.CALCULATED:
                return realized_result
            if (
                realized_result.realized is not None
                and realized_result.realized.net_realized_pnl is None
            ):
                return PnLResult(
                    status=PnLResultStatus.REJECTED_MISSING_FEE,
                    realized=realized_result.realized,
                    unrealized=unrealized_result.unrealized,
                    reason=realized_result.reason or "fee_unknown",
                    account_id=trade.account_id,
                    instrument_id=trade.instrument_id,
                )

        realized_delta = _realized_delta(realized_result)
        realized_pnl = position.realized_pnl + realized_delta
        unrealized_pnl = unrealized_result.unrealized.net_unrealized_pnl
        snapshot = PnLSnapshot(
            account_id=position.account_id,
            instrument_id=position.instrument_id,
            position_version=position.version,
            trade_id=realized_result.realized.trade_id
            if realized_result and realized_result.realized
            else None,
            margin_snapshot_id=margin_snapshot_id,
            calculation_key=calculation_key,
            price_basis=price_basis,
            mark_price=unrealized_result.unrealized.mark_price,
            contract_multiplier=unrealized_result.unrealized.contract_multiplier,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=realized_pnl + unrealized_pnl,
            fee_amount=realized_result.realized.fee_amount
            if realized_result and realized_result.realized
            else None,
            calculated_at=calculated_at,
        )

        existing_snapshot = uow.pnl_snapshots.get_by_calculation_key(
            snapshot.account_id,
            snapshot.instrument_id,
            snapshot.calculation_key,
        )
        if existing_snapshot is None:
            existing_snapshot = uow.pnl_snapshots.get_by_position_version(
                snapshot.account_id,
                snapshot.instrument_id,
                snapshot.position_version,
            )

        if existing_snapshot is not None:
            if not _same_snapshot_canonical(
                existing_snapshot,
                snapshot,
            ) and not _same_snapshot_position_version_facts(existing_snapshot, snapshot):
                return _conflict_result(
                    position,
                    existing_snapshot,
                    "pnl_snapshot_replay_diverged" if replay else "pnl_snapshot_diverged",
                    realized_result,
                    unrealized_result,
                )
            if replay:
                live_position = uow.positions.get_by_account_instrument(
                    position.account_id,
                    position.instrument_id,
                )
                if live_position is None:
                    return _conflict_result(
                        position,
                        existing_snapshot,
                        "live_position_missing_for_replay",
                        realized_result,
                        unrealized_result,
                    )
                if (
                    live_position.realized_pnl != existing_snapshot.realized_pnl
                    or live_position.unrealized_pnl != existing_snapshot.unrealized_pnl
                ):
                    return _conflict_result(
                        position,
                        existing_snapshot,
                        "live_pnl_diverged_from_snapshot",
                        realized_result,
                        unrealized_result,
                    )
            return PnLResult(
                status=PnLResultStatus.CALCULATED,
                realized=realized_result.realized if realized_result else None,
                unrealized=unrealized_result.unrealized,
                snapshot=existing_snapshot,
                reason=realized_result.reason if realized_result else None,
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )

        try:
            appended_snapshot = uow.pnl_snapshots.append_pnl_snapshot(snapshot)
            uow.positions.update_pnl(
                position.account_id,
                position.instrument_id,
                appended_snapshot.realized_pnl,
                appended_snapshot.unrealized_pnl,
                expected_version=position.version,
            )
        except PnLSnapshotConflictError as exc:
            uow.rollback()
            return PnLResult(
                status=PnLResultStatus.CONFLICT,
                realized=realized_result.realized if realized_result else None,
                unrealized=unrealized_result.unrealized,
                reason=str(exc),
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )
        except (OptimisticLockError, RepositoryError, ValueError) as exc:
            uow.rollback()
            return PnLResult(
                status=PnLResultStatus.ERROR,
                realized=realized_result.realized if realized_result else None,
                unrealized=unrealized_result.unrealized,
                reason=str(exc),
                account_id=position.account_id,
                instrument_id=position.instrument_id,
            )

        uow.commit()
        return PnLResult(
            status=PnLResultStatus.CALCULATED,
            realized=realized_result.realized if realized_result else None,
            unrealized=unrealized_result.unrealized,
            snapshot=appended_snapshot,
            reason=realized_result.reason if realized_result else None,
            account_id=position.account_id,
            instrument_id=position.instrument_id,
        )


def _realized_delta(result: PnLResult | None) -> Decimal:
    if result is None or result.realized is None:
        return Decimal("0")
    if result.realized.net_realized_pnl is None:
        raise ValueError("net_realized_pnl is required for persistent PnL projection")
    return result.realized.net_realized_pnl


def _same_snapshot_canonical(left: PnLSnapshot, right: PnLSnapshot) -> bool:
    return (
        left.account_id,
        left.instrument_id,
        left.position_version,
        left.trade_id,
        left.margin_snapshot_id,
        left.calculation_key,
        left.price_basis,
        left.mark_price,
        left.contract_multiplier,
        left.realized_pnl,
        left.unrealized_pnl,
        left.total_pnl,
        left.fee_amount,
    ) == (
        right.account_id,
        right.instrument_id,
        right.position_version,
        right.trade_id,
        right.margin_snapshot_id,
        right.calculation_key,
        right.price_basis,
        right.mark_price,
        right.contract_multiplier,
        right.realized_pnl,
        right.unrealized_pnl,
        right.total_pnl,
        right.fee_amount,
    )


def _same_snapshot_position_version_facts(left: PnLSnapshot, right: PnLSnapshot) -> bool:
    return (
        left.account_id,
        left.instrument_id,
        left.position_version,
        left.trade_id,
        left.margin_snapshot_id,
        left.price_basis,
        left.mark_price,
        left.contract_multiplier,
        left.realized_pnl,
        left.unrealized_pnl,
        left.total_pnl,
        left.fee_amount,
    ) == (
        right.account_id,
        right.instrument_id,
        right.position_version,
        right.trade_id,
        right.margin_snapshot_id,
        right.price_basis,
        right.mark_price,
        right.contract_multiplier,
        right.realized_pnl,
        right.unrealized_pnl,
        right.total_pnl,
        right.fee_amount,
    )


def _conflict_result(
    position: Position,
    snapshot: PnLSnapshot,
    reason: str,
    realized_result: PnLResult | None,
    unrealized_result: PnLResult,
) -> PnLResult:
    return PnLResult(
        status=PnLResultStatus.CONFLICT,
        realized=realized_result.realized if realized_result else None,
        unrealized=unrealized_result.unrealized,
        snapshot=snapshot,
        reason=reason,
        account_id=position.account_id,
        instrument_id=position.instrument_id,
    )
