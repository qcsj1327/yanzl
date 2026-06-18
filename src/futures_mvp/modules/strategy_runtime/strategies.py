from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from futures_mvp.modules.strategy_runtime.models import (
    StrategyContext,
    StrategyDecision,
    StrategyDecisionType,
)


class StrategyEvaluator(Protocol):
    def evaluate(self, context: StrategyContext) -> StrategyDecision: ...


class NoOpStrategy:
    def evaluate(self, context: StrategyContext) -> StrategyDecision:
        return StrategyDecision(
            decision=StrategyDecisionType.HOLD,
            side="NONE",
            confidence=Decimal("1"),
            reason="noop strategy holds deterministically",
            expected_price=None,
            tags=("noop",),
            diagnostics=(
                "no orders",
                "no trades",
                "no side effects",
            ),
        )


class BuyAndHoldStrategy:
    def evaluate(self, context: StrategyContext) -> StrategyDecision:
        if len(context.historical_bars) == 1:
            return StrategyDecision(
                decision=StrategyDecisionType.BUY,
                side="BUY",
                confidence=Decimal("1"),
                reason="first eligible bar buy",
                expected_price=context.current_bar.close if context.current_bar else None,
                tags=("buy_and_hold",),
                diagnostics=(
                    "decision only",
                    "no orders",
                    "no trades",
                    "no side effects",
                ),
            )
        return StrategyDecision(
            decision=StrategyDecisionType.HOLD,
            side="NONE",
            confidence=Decimal("1"),
            reason="already entered hold",
            expected_price=None,
            tags=("buy_and_hold",),
            diagnostics=(
                "decision only",
                "no orders",
                "no trades",
                "no side effects",
            ),
        )


class ExitReferenceStrategy:
    def evaluate(self, context: StrategyContext) -> StrategyDecision:
        if len(context.historical_bars) == 1:
            return StrategyDecision(
                decision=StrategyDecisionType.BUY,
                side="BUY",
                confidence=Decimal("1"),
                reason="first eligible bar buy before exit reference",
                expected_price=context.current_bar.close if context.current_bar else None,
                tags=("exit_reference",),
                diagnostics=(
                    "decision only",
                    "research-only entry order skeleton",
                    "no trades",
                    "no side effects",
                ),
            )
        return StrategyDecision(
            decision=StrategyDecisionType.CLOSE,
            side="CLOSE",
            confidence=Decimal("1"),
            reason="exit reference closes after first bar",
            expected_price=context.current_bar.close if context.current_bar else None,
            tags=("exit_reference",),
            diagnostics=(
                "decision only",
                "research-only exit order skeleton",
                "no exit fill",
                "no realized pnl",
                "no cash return",
            ),
        )
