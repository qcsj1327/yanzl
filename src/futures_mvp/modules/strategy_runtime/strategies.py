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
