from collections.abc import Callable
from decimal import Decimal
from typing import Any

from futures_mvp.domain.enums import SettlementResultStatus
from futures_mvp.domain.models import (
    AccountSnapshot,
    Position,
    SettlementContext,
    SettlementResult,
    SettlementSnapshot,
    TradingCalendar,
)
from futures_mvp.interfaces.repositories import (
    OptimisticLockError,
    RepositoryError,
    SettlementSnapshotConflictError,
    UnitOfWork,
)
from futures_mvp.modules.settlement.calculator import SettlementCalculator, SettlementPlan


class SettlementEngine:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        calculator: SettlementCalculator | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._calculator = calculator or SettlementCalculator()

    def settle(
        self,
        context: SettlementContext,
        *,
        calendar: TradingCalendar | None = None,
    ) -> SettlementResult:
        return self._settle(context, calendar=calendar, replay=False)

    def replay_settlement(
        self,
        context: SettlementContext,
        *,
        calendar: TradingCalendar | None = None,
    ) -> SettlementResult:
        return self._settle(context, calendar=calendar, replay=True)

    def _settle(
        self,
        context: SettlementContext,
        *,
        calendar: TradingCalendar | None,
        replay: bool,
    ) -> SettlementResult:
        planned = self._calculator.build_plan(context, calendar=calendar)
        if isinstance(planned, SettlementResult):
            return planned

        with self._uow_factory() as uow:
            existing = uow.settlement_snapshots.get_by_account_trading_day(
                planned.snapshot.account_id,
                planned.snapshot.trading_day,
            )
            if existing is not None:
                if not _same_snapshot_canonical(existing, planned.snapshot):
                    return SettlementResult(
                        status=SettlementResultStatus.CONFLICT,
                        snapshot=existing,
                        reason="settlement_snapshot_diverged",
                        account_id=context.account_id,
                        trading_day=context.trading_day,
                    )
                if replay:
                    divergence_reason = _live_divergence_reason(uow, existing)
                    if divergence_reason is not None:
                        return SettlementResult(
                            status=SettlementResultStatus.CONFLICT,
                            snapshot=existing,
                            reason=divergence_reason,
                            account_id=context.account_id,
                            trading_day=context.trading_day,
                        )
                return SettlementResult(
                    status=SettlementResultStatus.DUPLICATE,
                    snapshot=existing,
                    reason=None,
                    account_id=context.account_id,
                    trading_day=context.trading_day,
                )

            live_positions = _load_live_positions(uow, context)
            if live_positions is None:
                return SettlementResult(
                    status=SettlementResultStatus.REJECTED_MISSING_POSITION,
                    reason="missing_live_position",
                    account_id=context.account_id,
                    trading_day=context.trading_day,
                )
            for live_position, context_position in zip(
                live_positions,
                context.positions,
                strict=True,
            ):
                if _position_payload(live_position) != _position_payload(context_position):
                    return SettlementResult(
                        status=SettlementResultStatus.CONFLICT,
                        reason="live_position_diverged_from_context",
                        account_id=context.account_id,
                        trading_day=context.trading_day,
                    )

            try:
                account_before = _ensure_account_before_snapshot(uow, context, planned)
                account_after = uow.account_snapshots.append_account_snapshot(
                    AccountSnapshot(
                        account_id=context.account_id,
                        equity=planned.equity_after,
                        available_cash=planned.available_cash_after,
                        margin_used=planned.snapshot.margin_used,
                        frozen_margin=planned.frozen_cash_after,
                        realized_pnl=planned.snapshot.realized_pnl,
                        unrealized_pnl=planned.snapshot.unrealized_pnl,
                        snapshot_time=context.settled_at,
                    )
                )
                snapshot = planned.snapshot.model_copy(
                    update={
                        "account_snapshot_before_id": account_before.id,
                        "account_snapshot_after_id": account_after.id,
                    }
                )
                appended_snapshot = uow.settlement_snapshots.append_settlement_snapshot(snapshot)
                for position in live_positions:
                    uow.positions.roll_today_to_yesterday_for_settlement(
                        position.account_id,
                        position.instrument_id,
                        expected_version=position.version,
                    )
            except SettlementSnapshotConflictError as exc:
                uow.rollback()
                return SettlementResult(
                    status=SettlementResultStatus.CONFLICT,
                    reason=str(exc),
                    account_id=context.account_id,
                    trading_day=context.trading_day,
                )
            except (OptimisticLockError, RepositoryError, ValueError) as exc:
                uow.rollback()
                return SettlementResult(
                    status=SettlementResultStatus.ERROR,
                    reason=str(exc),
                    account_id=context.account_id,
                    trading_day=context.trading_day,
                )

            uow.commit()
            return SettlementResult(
                status=SettlementResultStatus.SETTLED,
                snapshot=appended_snapshot,
                reason=None,
                account_id=context.account_id,
                trading_day=context.trading_day,
            )


def _load_live_positions(
    uow: UnitOfWork,
    context: SettlementContext,
) -> list[Position] | None:
    live_positions: list[Position] = []
    for position in context.positions:
        live_position = uow.positions.get_by_account_instrument(
            position.account_id,
            position.instrument_id,
        )
        if live_position is None:
            return None
        live_positions.append(live_position)
    return live_positions


def _ensure_account_before_snapshot(
    uow: UnitOfWork,
    context: SettlementContext,
    plan: SettlementPlan,
) -> AccountSnapshot:
    if isinstance(context.account_before, AccountSnapshot):
        if context.account_before.id is not None:
            return context.account_before
        return uow.account_snapshots.append_account_snapshot(context.account_before)
    return uow.account_snapshots.append_account_snapshot(
        AccountSnapshot(
            account_id=context.account_id,
            equity=context.account_before.equity,
            available_cash=context.account_before.available_cash,
            margin_used=plan.snapshot.margin_used,
            frozen_margin=context.account_before.frozen_cash,
            realized_pnl=plan.snapshot.realized_pnl,
            unrealized_pnl=plan.snapshot.unrealized_pnl,
            snapshot_time=context.account_before.snapshot_time,
        )
    )


def _live_divergence_reason(
    uow: UnitOfWork,
    snapshot: SettlementSnapshot,
) -> str | None:
    for expected_position in snapshot.positions_after:
        account_id = str(expected_position["account_id"])
        instrument_id = str(expected_position["instrument_id"])
        live_position = uow.positions.get_by_account_instrument(account_id, instrument_id)
        if live_position is None:
            return "live_position_missing_for_replay"
        if _position_payload(live_position) != expected_position:
            return "live_position_diverged_from_settlement_snapshot"

    if snapshot.account_snapshot_after_id is None:
        return "settlement_account_snapshot_after_missing"
    live_account = uow.account_snapshots.get_latest(snapshot.account_id)
    expected_account = uow.account_snapshots.get_by_id(snapshot.account_snapshot_after_id)
    if live_account is None or expected_account is None:
        return "live_account_missing_for_replay"
    if _account_projection(live_account) != _account_projection(expected_account):
        return "live_account_diverged_from_settlement_snapshot"
    return None


def _same_snapshot_canonical(left: SettlementSnapshot, right: SettlementSnapshot) -> bool:
    return (
        left.account_id,
        left.trading_day,
        left.calculation_key,
        _payload_tuple(left.positions_before),
        _payload_tuple(left.positions_after),
        _payload_tuple(left.settlement_prices),
        left.pnl_snapshot_ids,
        left.margin_snapshot_ids,
        left.cash_before,
        left.cash_after,
        left.realized_pnl,
        left.unrealized_pnl,
        left.margin_used,
        left.status,
    ) == (
        right.account_id,
        right.trading_day,
        right.calculation_key,
        _payload_tuple(right.positions_before),
        _payload_tuple(right.positions_after),
        _payload_tuple(right.settlement_prices),
        right.pnl_snapshot_ids,
        right.margin_snapshot_ids,
        right.cash_before,
        right.cash_after,
        right.realized_pnl,
        right.unrealized_pnl,
        right.margin_used,
        right.status,
    )


def _payload_tuple(payload: tuple[dict[str, Any], ...]) -> tuple[object, ...]:
    return tuple(tuple(sorted(item.items())) for item in payload)


def _position_payload(position: Position) -> dict[str, Any]:
    return {
        "id": position.id,
        "account_id": position.account_id,
        "instrument_id": position.instrument_id,
        "long_today_qty": _decimal_payload(position.long_today_qty),
        "long_yesterday_qty": _decimal_payload(position.long_yesterday_qty),
        "short_today_qty": _decimal_payload(position.short_today_qty),
        "short_yesterday_qty": _decimal_payload(position.short_yesterday_qty),
        "frozen_long_qty": _decimal_payload(position.frozen_long_qty),
        "frozen_short_qty": _decimal_payload(position.frozen_short_qty),
        "long_avg_price": _decimal_payload(position.long_avg_price),
        "short_avg_price": _decimal_payload(position.short_avg_price),
        "settlement_price": _decimal_payload(position.settlement_price),
        "last_price": _decimal_payload(position.last_price),
        "realized_pnl": _decimal_payload(position.realized_pnl),
        "unrealized_pnl": _decimal_payload(position.unrealized_pnl),
        "margin_used": _decimal_payload(position.margin_used),
        "version": position.version,
    }


def _decimal_payload(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _account_projection(snapshot: AccountSnapshot) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return (
        snapshot.equity,
        snapshot.available_cash,
        snapshot.margin_used,
        snapshot.frozen_margin,
    )
