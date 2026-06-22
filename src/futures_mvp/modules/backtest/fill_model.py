from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

from futures_mvp.modules.backtest.models import (
    FillModelResult,
    FillModelStatus,
    SimulatedOrder,
    SimulatedOrderIntent,
    SimulatedOrderStatus,
    SimulatedTrade,
)
from futures_mvp.modules.market_data.contracts import HistoricalBar


@dataclass(frozen=True)
class NoFillModel:
    reason: str = "no fill model selected"

    def fill(self, order: SimulatedOrder) -> FillModelResult:
        return FillModelResult(
            status=FillModelStatus.NO_FILL,
            simulated_trade=None,
            diagnostics=(
                self.reason,
                "research-only no-fill model",
                "no Trade ledger, Accounting fact, OMS truth, or equity change",
                f"order_id={order.order_id}",
            ),
        )


@dataclass(frozen=True)
class NextBarOpenFillModel:
    supported_side: str = "BUY"

    def fill(
        self,
        order: SimulatedOrder,
        bars: tuple[HistoricalBar, ...],
    ) -> FillModelResult:
        if order.status is not SimulatedOrderStatus.CREATED:
            return FillModelResult(
                status=FillModelStatus.BLOCKED,
                diagnostics=("order status must be CREATED",),
            )
        expected_side = _expected_side_for_intent(
            order.intent,
            entry_side=self.supported_side,
        )
        if expected_side is None:
            return FillModelResult(
                status=FillModelStatus.REJECTED,
                diagnostics=(f"unsupported order intent: {order.intent.value}",),
            )
        if order.side != expected_side:
            return FillModelResult(
                status=FillModelStatus.REJECTED,
                diagnostics=(
                    f"order side {order.side} does not match "
                    f"{order.intent.value} intent",
                ),
            )
        if order.quantity <= Decimal("0"):
            return FillModelResult(
                status=FillModelStatus.BLOCKED,
                diagnostics=("order quantity must be greater than 0",),
            )

        next_bar = _next_matching_bar(order, bars)
        if next_bar is None:
            return FillModelResult(
                status=FillModelStatus.DATA_GAP,
                diagnostics=("next available bar not found",),
            )
        if next_bar.open <= Decimal("0"):
            return FillModelResult(
                status=FillModelStatus.DATA_GAP,
                diagnostics=("next bar open must be greater than 0",),
            )

        trade = SimulatedTrade(
            trade_id=_trade_id(
                order=order,
                fill_bar=next_bar,
                fill_price=next_bar.open,
                fill_qty=order.quantity,
            ),
            order_id=order.order_id,
            fill_price=next_bar.open,
            fill_qty=order.quantity,
            fill_bar_ts=next_bar.bar_ts,
            symbol=order.symbol,
            instrument_id=order.instrument_id,
            trade_instrument_id=order.trade_instrument_id,
            exchange=order.exchange,
            trading_day=order.trading_day,
            resolver_source=order.resolver_source,
            resolver_confidence=order.resolver_confidence,
            resolver_lineage=order.resolver_lineage,
            diagnostics=(
                f"research-only {order.intent.value} next-bar-open simulated trade",
                "not Trade ledger, Accounting fact, OMS truth, broker execution, "
                "or exchange execution",
            ),
            intent=order.intent,
        )
        return FillModelResult(
            status=FillModelStatus.FILLED,
            simulated_trade=trade,
            diagnostics=(
                f"next-bar-open fill generated research-only "
                f"{order.intent.value} simulated trade",
            ),
        )


def _next_matching_bar(
    order: SimulatedOrder,
    bars: tuple[HistoricalBar, ...],
) -> HistoricalBar | None:
    matching_bars = (
        bar
        for bar in sorted(bars, key=lambda item: item.bar_ts)
        if bar.bar_ts > order.created_bar_ts and _bar_matches_order_identity(order, bar)
    )
    return next(matching_bars, None)


def _bar_matches_order_identity(order: SimulatedOrder, bar: HistoricalBar) -> bool:
    return (
        bar.symbol == order.symbol
        and bar.instrument_id == order.instrument_id
        and bar.trade_instrument_id == order.trade_instrument_id
        and bar.exchange == order.exchange
        and bar.trading_day == order.trading_day
    )


def _expected_side_for_intent(
    intent: SimulatedOrderIntent,
    *,
    entry_side: str,
) -> str | None:
    if intent is SimulatedOrderIntent.ENTRY:
        return entry_side
    if intent is SimulatedOrderIntent.EXIT:
        return "CLOSE"
    return None


def _trade_id(
    *,
    order: SimulatedOrder,
    fill_bar: HistoricalBar,
    fill_price: Decimal,
    fill_qty: Decimal,
) -> str:
    raw = "|".join(
        (
            order.order_id,
            fill_bar.bar_ts.isoformat(),
            str(fill_price),
            str(fill_qty),
            order.symbol,
            order.instrument_id,
            order.trade_instrument_id,
            order.exchange,
            order.trading_day.isoformat(),
        )
    )
    return f"sim-trade-{sha256(raw.encode('utf-8')).hexdigest()[:24]}"
