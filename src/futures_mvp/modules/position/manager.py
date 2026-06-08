from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from futures_mvp.domain.enums import Direction, Offset, PositionManagerResultStatus
from futures_mvp.domain.models import (
    Position,
    PositionEvent,
    PositionManagerResult,
    PositionSnapshot,
    Trade,
)
from futures_mvp.interfaces.repositories import (
    OptimisticLockError,
    PositionEventConflictError,
    RepositoryError,
    UnitOfWork,
)

POSITION_EVENT_TYPE_TRADE_APPLIED = "TRADE_APPLIED"


@dataclass(frozen=True)
class PositionReplayResult:
    results: tuple[PositionManagerResult, ...]

    @property
    def has_divergence(self) -> bool:
        return any(
            result.status
            in {
                PositionManagerResultStatus.CONFLICT,
                PositionManagerResultStatus.ERROR,
            }
            for result in self.results
        )


class PositionManager:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def apply_trade(self, trade: Trade) -> PositionManagerResult:
        preflight = _validate_trade_for_position(trade)
        if preflight is not None:
            return preflight

        with self._uow_factory() as uow:
            existing_event = uow.position_events.get_by_trade_key(
                trade.account_id,
                trade.exchange,
                trade.exchange_trade_id,
            )
            if existing_event is not None:
                return _duplicate_result(uow, existing_event, trade)

            if trade.offset is Offset.OPEN:
                position = uow.positions.create_or_get_position(
                    trade.account_id,
                    trade.instrument_id,
                )
            else:
                existing_position = uow.positions.get_by_account_instrument(
                    trade.account_id,
                    trade.instrument_id,
                )
                if existing_position is None:
                    return _missing_position_result(trade)
                position = existing_position

            before_snapshot = PositionSnapshot.from_position(position)
            calculated = _apply_trade_to_position(position, trade)
            if calculated.status is not PositionManagerResultStatus.APPLIED:
                return calculated

            after_position = calculated.position
            if after_position is None:
                return _error_result(trade, "position calculation did not return a position")

            try:
                updated_position = uow.positions.update_position(
                    after_position,
                    expected_version=position.version,
                )
                position_event = PositionEvent(
                    account_id=trade.account_id,
                    instrument_id=trade.instrument_id,
                    exchange=trade.exchange,
                    exchange_trade_id=trade.exchange_trade_id,
                    trade_id=_require_trade_id(trade),
                    position_id=_require_position_id(updated_position),
                    event_type=POSITION_EVENT_TYPE_TRADE_APPLIED,
                    direction=trade.direction,
                    offset=trade.offset,
                    price=trade.price,
                    quantity=trade.quantity,
                    before_snapshot=before_snapshot,
                    after_snapshot=PositionSnapshot.from_position(updated_position),
                    occurred_at=trade.trade_time,
                    created_at=datetime.now(UTC),
                    raw_payload={},
                )
                appended_event = uow.position_events.append_position_event(position_event)
            except PositionEventConflictError as exc:
                uow.rollback()
                return PositionManagerResult(
                    status=PositionManagerResultStatus.CONFLICT,
                    reason=str(exc),
                    trade_id=trade.id,
                    account_id=trade.account_id,
                    instrument_id=trade.instrument_id,
                )
            except (OptimisticLockError, RepositoryError, ValueError) as exc:
                uow.rollback()
                return PositionManagerResult(
                    status=PositionManagerResultStatus.ERROR,
                    reason=str(exc),
                    trade_id=trade.id,
                    account_id=trade.account_id,
                    instrument_id=trade.instrument_id,
                )

            uow.commit()
            return PositionManagerResult(
                status=PositionManagerResultStatus.APPLIED,
                position=updated_position,
                position_event=appended_event,
                trade_id=trade.id,
                account_id=trade.account_id,
                instrument_id=trade.instrument_id,
            )

    def replay_trades(self, trades: Sequence[Trade]) -> PositionReplayResult:
        ordered_trades = sorted(
            trades,
            key=lambda trade: (
                trade.trade_time,
                trade.id or trade.exchange_trade_id,
            ),
        )
        results: list[PositionManagerResult] = []
        for trade in ordered_trades:
            result = self.apply_trade(trade)
            results.append(result)
            if result.status in {
                PositionManagerResultStatus.CONFLICT,
                PositionManagerResultStatus.ERROR,
            }:
                break
        return PositionReplayResult(results=tuple(results))


def _validate_trade_for_position(trade: Trade) -> PositionManagerResult | None:
    required_fields = {
        "id": trade.id,
        "account_id": trade.account_id,
        "exchange": trade.exchange,
        "exchange_trade_id": trade.exchange_trade_id,
        "instrument_id": trade.instrument_id,
        "trade_time": trade.trade_time,
    }
    for field_name, value in required_fields.items():
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return _error_result(trade, f"{field_name} is required to apply position")
    if trade.price <= 0:
        return _error_result(trade, "trade.price must be positive to apply position")
    if trade.quantity <= 0:
        return _error_result(trade, "trade.quantity must be positive to apply position")
    return None


def _apply_trade_to_position(position: Position, trade: Trade) -> PositionManagerResult:
    if trade.offset is Offset.OPEN and trade.direction is Direction.BUY:
        return _applied_result(
            trade,
            position.model_copy(
                update={
                    "long_today_qty": position.long_today_qty + trade.quantity,
                    "long_avg_price": _weighted_average(
                        position.long_today_qty + position.long_yesterday_qty,
                        position.long_avg_price,
                        trade.quantity,
                        trade.price,
                    ),
                }
            ),
        )
    if trade.offset is Offset.OPEN and trade.direction is Direction.SELL:
        return _applied_result(
            trade,
            position.model_copy(
                update={
                    "short_today_qty": position.short_today_qty + trade.quantity,
                    "short_avg_price": _weighted_average(
                        position.short_today_qty + position.short_yesterday_qty,
                        position.short_avg_price,
                        trade.quantity,
                        trade.price,
                    ),
                }
            ),
        )
    if trade.offset is Offset.CLOSE_TODAY and trade.direction is Direction.SELL:
        return _close_bucket(
            trade,
            position,
            bucket_name="long_today_qty",
            current_qty=position.long_today_qty,
            side_total_qty=position.long_today_qty + position.long_yesterday_qty,
            frozen_qty=position.frozen_long_qty,
        )
    if trade.offset is Offset.CLOSE_YESTERDAY and trade.direction is Direction.SELL:
        return _close_bucket(
            trade,
            position,
            bucket_name="long_yesterday_qty",
            current_qty=position.long_yesterday_qty,
            side_total_qty=position.long_today_qty + position.long_yesterday_qty,
            frozen_qty=position.frozen_long_qty,
        )
    if trade.offset is Offset.CLOSE_TODAY and trade.direction is Direction.BUY:
        return _close_bucket(
            trade,
            position,
            bucket_name="short_today_qty",
            current_qty=position.short_today_qty,
            side_total_qty=position.short_today_qty + position.short_yesterday_qty,
            frozen_qty=position.frozen_short_qty,
        )
    if trade.offset is Offset.CLOSE_YESTERDAY and trade.direction is Direction.BUY:
        return _close_bucket(
            trade,
            position,
            bucket_name="short_yesterday_qty",
            current_qty=position.short_yesterday_qty,
            side_total_qty=position.short_today_qty + position.short_yesterday_qty,
            frozen_qty=position.frozen_short_qty,
        )
    return PositionManagerResult(
        status=PositionManagerResultStatus.ERROR,
        reason=f"unsupported position offset/direction: {trade.direction}/{trade.offset}",
        trade_id=trade.id,
        account_id=trade.account_id,
        instrument_id=trade.instrument_id,
    )


def _duplicate_result(
    uow: UnitOfWork,
    existing_event: PositionEvent,
    trade: Trade,
) -> PositionManagerResult:
    if not _same_trade_event(existing_event, trade):
        return PositionManagerResult(
            status=PositionManagerResultStatus.CONFLICT,
            position_event=existing_event,
            reason="position event trade key conflict",
            trade_id=trade.id,
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
        )

    current_position = uow.positions.get_by_account_instrument(
        existing_event.account_id,
        existing_event.instrument_id,
    )
    if (
        current_position is None
        or PositionSnapshot.from_position(current_position) != existing_event.after_snapshot
    ):
        return PositionManagerResult(
            status=PositionManagerResultStatus.CONFLICT,
            position=current_position,
            position_event=existing_event,
            reason="position_projection_diverged_from_event_snapshot",
            trade_id=trade.id,
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
        )

    return PositionManagerResult(
        status=PositionManagerResultStatus.DUPLICATE_IGNORED,
        position=current_position,
        position_event=existing_event,
        trade_id=trade.id,
        account_id=trade.account_id,
        instrument_id=trade.instrument_id,
    )


def _missing_position_result(trade: Trade) -> PositionManagerResult:
    if trade.offset in {Offset.CLOSE_TODAY, Offset.CLOSE_YESTERDAY}:
        return PositionManagerResult(
            status=PositionManagerResultStatus.REJECTED_INSUFFICIENT_POSITION,
            reason="insufficient position: position does not exist",
            trade_id=trade.id,
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
        )
    return _error_result(
        trade,
        f"unsupported position offset/direction: {trade.direction}/{trade.offset}",
    )


def _close_bucket(
    trade: Trade,
    position: Position,
    *,
    bucket_name: str,
    current_qty: Decimal,
    side_total_qty: Decimal,
    frozen_qty: Decimal,
) -> PositionManagerResult:
    if current_qty < trade.quantity:
        return PositionManagerResult(
            status=PositionManagerResultStatus.REJECTED_INSUFFICIENT_POSITION,
            position=position,
            reason=f"insufficient {bucket_name}: {current_qty} < {trade.quantity}",
            trade_id=trade.id,
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
        )
    if side_total_qty - trade.quantity < frozen_qty:
        return PositionManagerResult(
            status=PositionManagerResultStatus.REJECTED_INSUFFICIENT_POSITION,
            position=position,
            reason=(
                f"insufficient unfrozen position: "
                f"{side_total_qty} - {trade.quantity} < {frozen_qty}"
            ),
            trade_id=trade.id,
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
        )
    return _applied_result(
        trade,
        position.model_copy(update={bucket_name: current_qty - trade.quantity}),
    )


def _weighted_average(
    existing_qty: Decimal,
    existing_avg_price: Decimal,
    added_qty: Decimal,
    added_price: Decimal,
) -> Decimal:
    total_qty = existing_qty + added_qty
    if total_qty == 0:
        return added_price
    return ((existing_qty * existing_avg_price) + (added_qty * added_price)) / total_qty


def _applied_result(trade: Trade, position: Position) -> PositionManagerResult:
    return PositionManagerResult(
        status=PositionManagerResultStatus.APPLIED,
        position=position,
        trade_id=trade.id,
        account_id=trade.account_id,
        instrument_id=trade.instrument_id,
    )


def _error_result(trade: Trade, reason: str) -> PositionManagerResult:
    return PositionManagerResult(
        status=PositionManagerResultStatus.ERROR,
        reason=reason,
        trade_id=trade.id,
        account_id=trade.account_id,
        instrument_id=trade.instrument_id,
    )


def _same_trade_event(event: PositionEvent, trade: Trade) -> bool:
    return (
        event.account_id == trade.account_id
        and event.instrument_id == trade.instrument_id
        and event.exchange == trade.exchange
        and event.exchange_trade_id == trade.exchange_trade_id
        and event.trade_id == trade.id
        and event.direction == trade.direction
        and event.offset == trade.offset
        and event.price == trade.price
        and event.quantity == trade.quantity
        and event.occurred_at == trade.trade_time
    )


def _require_trade_id(trade: Trade) -> str:
    if trade.id is None:
        raise ValueError("trade.id is required to apply position")
    return trade.id


def _require_position_id(position: Position) -> str:
    if position.id is None:
        raise ValueError("position.id is required to append position event")
    return position.id
