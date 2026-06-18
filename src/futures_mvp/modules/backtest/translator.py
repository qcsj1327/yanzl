from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

from futures_mvp.modules.backtest.models import (
    DecisionTranslationResult,
    DecisionTranslationStatus,
    SimulatedOrder,
    SimulatedOrderIntent,
    SimulatedOrderStatus,
)
from futures_mvp.modules.market_data.consumer import ResolverConsumerContext
from futures_mvp.modules.market_data.contracts import HistoricalBar
from futures_mvp.modules.strategy_runtime.models import (
    StrategyDecision,
    StrategyDecisionType,
)

_DEFAULT_QUANTITY = Decimal("1")
_DEFAULT_ORDER_TYPE = "MARKET"


@dataclass(frozen=True)
class DecisionTranslator:
    quantity: Decimal = _DEFAULT_QUANTITY
    order_type: str = _DEFAULT_ORDER_TYPE

    def translate(
        self,
        *,
        strategy_name: str,
        decision: StrategyDecision,
        resolver_lineage: ResolverConsumerContext | None,
        current_bar: HistoricalBar | None,
    ) -> DecisionTranslationResult:
        if resolver_lineage is None:
            return DecisionTranslationResult(
                status=DecisionTranslationStatus.BLOCKED,
                diagnostics=("resolver lineage is required",),
            )
        if current_bar is None:
            return DecisionTranslationResult(
                status=DecisionTranslationStatus.BLOCKED,
                diagnostics=("current bar is required",),
            )
        if self.quantity <= Decimal("0"):
            return DecisionTranslationResult(
                status=DecisionTranslationStatus.BLOCKED,
                diagnostics=("simulated order quantity must be greater than 0",),
            )

        if decision.decision is StrategyDecisionType.HOLD:
            return DecisionTranslationResult(
                status=DecisionTranslationStatus.SKIPPED,
                diagnostics=("HOLD decision does not create simulated order",),
            )
        if decision.decision is StrategyDecisionType.SELL:
            return DecisionTranslationResult(
                status=DecisionTranslationStatus.REJECTED,
                diagnostics=(
                    "SELL decision translation is not supported by the "
                    "long-only research skeleton",
                ),
            )
        if decision.decision not in (
            StrategyDecisionType.BUY,
            StrategyDecisionType.CLOSE,
        ):
            return DecisionTranslationResult(
                status=DecisionTranslationStatus.ERROR,
                diagnostics=(f"unsupported decision: {decision.decision.value}",),
            )

        expected_price = (
            decision.expected_price
            if decision.expected_price is not None
            else current_bar.close
        )
        if expected_price <= Decimal("0"):
            decision_name = decision.decision.value
            return DecisionTranslationResult(
                status=DecisionTranslationStatus.BLOCKED,
                diagnostics=(
                    f"{decision_name} decision requires a positive expected price",
                ),
            )

        identity = resolver_lineage.identity
        lineage = resolver_lineage.lineage
        order_intent = (
            SimulatedOrderIntent.EXIT
            if decision.decision is StrategyDecisionType.CLOSE
            else SimulatedOrderIntent.ENTRY
        )
        simulated_order = SimulatedOrder(
            order_id=_order_id(
                strategy_name=strategy_name,
                decision=decision,
                resolver_lineage=resolver_lineage,
                current_bar=current_bar,
            ),
            strategy_name=strategy_name,
            symbol=identity.symbol,
            instrument_id=identity.instrument_id,
            trade_instrument_id=identity.trade_instrument_id,
            exchange=identity.exchange,
            trading_day=identity.trading_day,
            side=decision.side,
            quantity=self.quantity,
            expected_price=expected_price,
            order_type=self.order_type,
            created_bar_ts=current_bar.bar_ts,
            resolver_source=lineage.resolver_source,
            resolver_confidence=lineage.resolver_confidence,
            resolver_lineage=resolver_lineage,
            diagnostics=(
                "research-only simulated order",
                "not OMS order, broker order, exchange order, or ledger fact",
                f"intent={order_intent.value}",
            ),
            status=SimulatedOrderStatus.CREATED,
            intent=order_intent,
        )
        return DecisionTranslationResult(
            status=DecisionTranslationStatus.CREATED,
            simulated_order=simulated_order,
            simulated_trades=(),
            diagnostics=(
                f"{decision.decision.value} decision translated to "
                f"CREATED {order_intent.value} simulated order",
            ),
        )


def _order_id(
    *,
    strategy_name: str,
    decision: StrategyDecision,
    resolver_lineage: ResolverConsumerContext,
    current_bar: HistoricalBar,
) -> str:
    identity = resolver_lineage.identity
    raw = "|".join(
        (
            strategy_name,
            current_bar.bar_ts.isoformat(),
            decision.decision.value,
            identity.symbol,
            identity.instrument_id,
            identity.trade_instrument_id,
            identity.exchange,
            identity.trading_day.isoformat(),
        )
    )
    return f"sim-order-{sha256(raw.encode('utf-8')).hexdigest()[:24]}"
