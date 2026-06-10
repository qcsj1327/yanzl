from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from futures_mvp.domain.enums import PnLPriceBasis, SettlementResultStatus
from futures_mvp.domain.models import (
    AccountContext,
    AccountSnapshot,
    MarginSnapshot,
    PnLSnapshot,
    Position,
    SettlementContext,
    SettlementPrice,
    SettlementResult,
    SettlementSnapshot,
    TradingCalendar,
)


@dataclass(frozen=True)
class SettlementPlan:
    snapshot: SettlementSnapshot
    equity_after: Decimal
    available_cash_after: Decimal
    frozen_cash_after: Decimal


class SettlementCalculator:
    def calculate(
        self,
        context: SettlementContext,
        *,
        calendar: TradingCalendar | None = None,
    ) -> SettlementResult:
        if calendar is not None:
            if calendar.trading_day != context.trading_day or not calendar.is_trading_day:
                return _result(
                    SettlementResultStatus.REJECTED_NON_TRADING_DAY,
                    context,
                    "non_trading_day",
                )
        if not context.positions:
            return _result(
                SettlementResultStatus.REJECTED_MISSING_POSITION,
                context,
                "missing_position",
            )

        for position in context.positions:
            if position.account_id != context.account_id:
                return _result(
                    SettlementResultStatus.ERROR,
                    context,
                    "settlement_identity_mismatch: account_id",
                )
            if position.frozen_long_qty > 0 or position.frozen_short_qty > 0:
                return _result(
                    SettlementResultStatus.REJECTED_FROZEN_POSITION,
                    context,
                    "frozen_position",
                )

        prices_by_instrument = {price.instrument_id: price for price in context.settlement_prices}
        pnl_by_position: dict[tuple[str, str, int], PnLSnapshot] = {}
        margin_by_position: dict[tuple[str, str, int], MarginSnapshot] = {}

        for position in context.positions:
            settlement_price = prices_by_instrument.get(position.instrument_id)
            if settlement_price is None or settlement_price.trading_day != context.trading_day:
                return _result(
                    SettlementResultStatus.REJECTED_MISSING_SETTLEMENT_PRICE,
                    context,
                    "missing_settlement_price",
                )

            if _has_pnl_snapshot_identity_mismatch(context, position):
                return _result(
                    SettlementResultStatus.CONFLICT,
                    context,
                    "pnl_snapshot_identity_mismatch",
                )
            pnl_snapshot = _matching_pnl_snapshot(context, position)
            if pnl_snapshot is None:
                return _result(
                    SettlementResultStatus.REJECTED_MISSING_PNL,
                    context,
                    "missing_pnl_snapshot",
                )
            pnl_by_position[_position_fact_key(position)] = pnl_snapshot
            if (
                pnl_snapshot.price_basis is not PnLPriceBasis.SETTLEMENT_PRICE
                or pnl_snapshot.mark_price != settlement_price.price
            ):
                return _result(
                    SettlementResultStatus.REJECTED_MISSING_PNL,
                    context,
                    "pnl_snapshot_not_settlement_compatible",
                )

            if _has_margin_snapshot_identity_mismatch(context, position):
                return _result(
                    SettlementResultStatus.CONFLICT,
                    context,
                    "margin_snapshot_identity_mismatch",
                )
            margin_snapshot = _matching_margin_snapshot(context, position)
            if margin_snapshot is None:
                return _result(
                    SettlementResultStatus.REJECTED_MISSING_MARGIN,
                    context,
                    "missing_margin_snapshot",
                )
            margin_by_position[_position_fact_key(position)] = margin_snapshot

        realized_pnl = sum(
            (
                pnl_by_position[_position_fact_key(position)].realized_pnl
                for position in context.positions
            ),
            Decimal("0"),
        )
        unrealized_pnl = sum(
            (
                pnl_by_position[_position_fact_key(position)].unrealized_pnl
                for position in context.positions
            ),
            Decimal("0"),
        )
        margin_used = sum(
            (
                margin_by_position[_position_fact_key(position)].margin_used
                for position in context.positions
            ),
            Decimal("0"),
        )
        cash_before = _cash_before(context.account_before, margin_used)
        cash_after = cash_before + realized_pnl

        positions_before = tuple(_position_payload(position) for position in context.positions)
        positions_after = tuple(
            _rolled_position_payload(position) for position in context.positions
        )
        snapshot = SettlementSnapshot(
            account_id=context.account_id,
            trading_day=context.trading_day,
            calculation_key=context.calculation_key,
            positions_before=positions_before,
            positions_after=positions_after,
            settlement_prices=tuple(
                _settlement_price_payload(prices_by_instrument[position.instrument_id])
                for position in context.positions
            ),
            pnl_snapshot_ids=tuple(
                _required_id(
                    pnl_by_position[_position_fact_key(position)].id,
                    "pnl_snapshot_id",
                )
                for position in context.positions
            ),
            margin_snapshot_ids=tuple(
                _required_id(
                    margin_by_position[_position_fact_key(position)].id,
                    "margin_snapshot_id",
                )
                for position in context.positions
            ),
            account_snapshot_before_id=getattr(context.account_before, "id", None),
            account_snapshot_after_id=None,
            cash_before=cash_before,
            cash_after=cash_after,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            margin_used=margin_used,
            status=SettlementResultStatus.SETTLED,
            reason=None,
            created_at=context.settled_at,
        )
        return SettlementResult(
            status=SettlementResultStatus.SETTLED,
            snapshot=snapshot,
            reason=None,
            account_id=context.account_id,
            trading_day=context.trading_day,
        )

    def build_plan(
        self,
        context: SettlementContext,
        *,
        calendar: TradingCalendar | None = None,
    ) -> SettlementPlan | SettlementResult:
        result = self.calculate(context, calendar=calendar)
        if result.status is not SettlementResultStatus.SETTLED or result.snapshot is None:
            return result
        return SettlementPlan(
            snapshot=result.snapshot,
            equity_after=result.snapshot.cash_after + result.snapshot.unrealized_pnl,
            available_cash_after=result.snapshot.cash_after - result.snapshot.margin_used,
            frozen_cash_after=_frozen_cash(context.account_before),
        )


def _result(
    status: SettlementResultStatus,
    context: SettlementContext,
    reason: str,
) -> SettlementResult:
    return SettlementResult(
        status=status,
        reason=reason,
        account_id=context.account_id,
        trading_day=context.trading_day,
    )


def _cash_before(account: AccountContext | AccountSnapshot, margin_used: Decimal) -> Decimal:
    if isinstance(account, AccountSnapshot):
        return account.available_cash + account.margin_used
    return account.available_cash + margin_used


def _frozen_cash(account: AccountContext | AccountSnapshot) -> Decimal:
    if isinstance(account, AccountSnapshot):
        return account.frozen_margin
    return account.frozen_cash


def _position_fact_key(position: Position) -> tuple[str, str, int]:
    return (position.account_id, position.instrument_id, position.version)


def _matching_pnl_snapshot(
    context: SettlementContext,
    position: Position,
) -> PnLSnapshot | None:
    return next(
        (
            snapshot
            for snapshot in context.pnl_snapshots
            if snapshot.account_id == context.account_id
            and snapshot.instrument_id == position.instrument_id
            and snapshot.position_version == position.version
            and snapshot.trading_day == context.trading_day
        ),
        None,
    )


def _matching_margin_snapshot(
    context: SettlementContext,
    position: Position,
) -> MarginSnapshot | None:
    return next(
        (
            snapshot
            for snapshot in context.margin_snapshots
            if snapshot.account_id == context.account_id
            and snapshot.instrument_id == position.instrument_id
            and snapshot.position_version == position.version
            and snapshot.trading_day == context.trading_day
        ),
        None,
    )


def _has_pnl_snapshot_identity_mismatch(
    context: SettlementContext,
    position: Position,
) -> bool:
    return any(
        snapshot.instrument_id == position.instrument_id
        and (
            snapshot.account_id != context.account_id
            or snapshot.position_version != position.version
            or snapshot.trading_day != context.trading_day
        )
        for snapshot in context.pnl_snapshots
    )


def _has_margin_snapshot_identity_mismatch(
    context: SettlementContext,
    position: Position,
) -> bool:
    return any(
        snapshot.instrument_id == position.instrument_id
        and (
            snapshot.account_id != context.account_id
            or snapshot.position_version != position.version
            or snapshot.trading_day != context.trading_day
        )
        for snapshot in context.margin_snapshots
    )


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


def _rolled_position_payload(position: Position) -> dict[str, Any]:
    payload = _position_payload(position)
    payload["long_yesterday_qty"] = _decimal_payload(
        position.long_yesterday_qty + position.long_today_qty
    )
    payload["short_yesterday_qty"] = _decimal_payload(
        position.short_yesterday_qty + position.short_today_qty
    )
    payload["long_today_qty"] = "0"
    payload["short_today_qty"] = "0"
    payload["version"] = position.version + 1
    return payload


def _decimal_payload(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _settlement_price_payload(price: SettlementPrice) -> dict[str, Any]:
    return price.model_dump(mode="json")


def _required_id(value: str | None, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required for settlement")
    return value
