from datetime import datetime
from decimal import Decimal

from futures_mvp.domain.decimal import require_decimal
from futures_mvp.domain.enums import Direction, Offset, PnLPriceBasis, PnLResultStatus
from futures_mvp.domain.models import (
    CloseTradeContext,
    PnLResult,
    Position,
    RealizedPnL,
    Trade,
    UnrealizedPnL,
)

CLOSE_OFFSETS = frozenset({Offset.CLOSE, Offset.CLOSE_TODAY, Offset.CLOSE_YESTERDAY})


def calculate_realized_pnl(
    trade: Trade,
    close_context: CloseTradeContext,
    *,
    calculated_at: datetime,
) -> PnLResult:
    if trade.account_id != close_context.account_id:
        return PnLResult(
            status=PnLResultStatus.ERROR,
            reason="pnl_identity_mismatch: account_id",
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
        )
    if trade.instrument_id != close_context.instrument_id:
        return PnLResult(
            status=PnLResultStatus.ERROR,
            reason="pnl_identity_mismatch: instrument_id",
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
        )
    if trade.offset not in CLOSE_OFFSETS:
        return PnLResult(
            status=PnLResultStatus.DOMAIN_FIELD_UNSUPPORTED,
            reason="open_trade_has_no_realized_pnl",
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
        )
    if trade.quantity > close_context.available_qty:
        return PnLResult(
            status=PnLResultStatus.ERROR,
            reason="close_quantity_exceeds_available_qty",
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
        )

    if trade.direction == Direction.SELL:
        gross_realized_pnl = (
            (trade.price - close_context.avg_cost)
            * trade.quantity
            * close_context.contract_multiplier
        )
    elif trade.direction == Direction.BUY:
        gross_realized_pnl = (
            (close_context.avg_cost - trade.price)
            * trade.quantity
            * close_context.contract_multiplier
        )
    else:
        return PnLResult(
            status=PnLResultStatus.DOMAIN_FIELD_UNSUPPORTED,
            reason="unsupported_close_direction",
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
        )

    net_realized_pnl = (
        None if trade.fee_amount is None else gross_realized_pnl - trade.fee_amount
    )
    realized = RealizedPnL(
        account_id=trade.account_id,
        instrument_id=trade.instrument_id,
        trade_id=trade.id or trade.exchange_trade_id,
        direction=trade.direction,
        offset=trade.offset,
        quantity=trade.quantity,
        close_price=trade.price,
        avg_cost=close_context.avg_cost,
        contract_multiplier=close_context.contract_multiplier,
        gross_realized_pnl=gross_realized_pnl,
        fee_amount=trade.fee_amount,
        net_realized_pnl=net_realized_pnl,
        currency=trade.fee_currency,
        calculated_at=calculated_at,
    )
    return PnLResult(
        status=PnLResultStatus.CALCULATED,
        realized=realized,
        reason="fee_unknown" if trade.fee_amount is None else None,
        account_id=trade.account_id,
        instrument_id=trade.instrument_id,
    )


def calculate_unrealized_pnl(
    position: Position | None,
    *,
    price_basis: PnLPriceBasis,
    mark_price: Decimal | None,
    contract_multiplier: Decimal | None,
) -> PnLResult:
    if position is None:
        return PnLResult(
            status=PnLResultStatus.REJECTED_MISSING_POSITION,
            reason="missing_position",
        )
    resolved_price = _positive_decimal_or_none(mark_price)
    if resolved_price is None:
        return PnLResult(
            status=PnLResultStatus.REJECTED_MISSING_PRICE,
            reason="missing_pnl_price",
            account_id=position.account_id,
            instrument_id=position.instrument_id,
        )
    resolved_multiplier = _positive_decimal_or_none(contract_multiplier)
    if resolved_multiplier is None:
        return PnLResult(
            status=PnLResultStatus.REJECTED_MISSING_MULTIPLIER,
            reason="missing_contract_multiplier",
            account_id=position.account_id,
            instrument_id=position.instrument_id,
        )

    long_qty = position.long_today_qty + position.long_yesterday_qty
    short_qty = position.short_today_qty + position.short_yesterday_qty
    long_unrealized = (
        (resolved_price - position.long_avg_price) * long_qty * resolved_multiplier
    )
    short_unrealized = (
        (position.short_avg_price - resolved_price) * short_qty * resolved_multiplier
    )
    gross_unrealized_pnl = long_unrealized + short_unrealized
    unrealized = UnrealizedPnL(
        account_id=position.account_id,
        instrument_id=position.instrument_id,
        long_qty=long_qty,
        short_qty=short_qty,
        long_avg_price=position.long_avg_price,
        short_avg_price=position.short_avg_price,
        price_basis=price_basis,
        mark_price=resolved_price,
        contract_multiplier=resolved_multiplier,
        gross_unrealized_pnl=gross_unrealized_pnl,
        net_unrealized_pnl=gross_unrealized_pnl,
    )
    return PnLResult(
        status=PnLResultStatus.CALCULATED,
        unrealized=unrealized,
        account_id=position.account_id,
        instrument_id=position.instrument_id,
    )


def _positive_decimal_or_none(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    decimal_value = require_decimal(value)
    if decimal_value <= 0:
        return None
    return decimal_value
