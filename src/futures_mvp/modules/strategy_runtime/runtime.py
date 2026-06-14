from __future__ import annotations

from futures_mvp.modules.strategy_runtime.models import (
    StrategyContext,
    StrategyRuntimeResult,
    StrategyRuntimeStatus,
)
from futures_mvp.modules.strategy_runtime.strategies import StrategyEvaluator


class StrategyRuntime:
    def __init__(self, strategy: StrategyEvaluator) -> None:
        self._strategy = strategy

    def run(self, context: StrategyContext) -> StrategyRuntimeResult:
        frozen_context = context.frozen_copy()
        blocked_reason = _blocked_reason(frozen_context)
        if blocked_reason is not None:
            return StrategyRuntimeResult(
                status=StrategyRuntimeStatus.BLOCKED,
                diagnostics=(blocked_reason,),
            )

        try:
            decision = self._strategy.evaluate(frozen_context)
        except Exception as exc:  # pragma: no cover - defensive runtime boundary
            return StrategyRuntimeResult(
                status=StrategyRuntimeStatus.ERROR,
                diagnostics=(f"strategy exception: {type(exc).__name__}: {exc}",),
            )
        return StrategyRuntimeResult(
            status=StrategyRuntimeStatus.COMPLETED,
            decision=decision,
            diagnostics=("strategy evaluated without side effects",),
        )


def _blocked_reason(context: StrategyContext) -> str | None:
    if context.resolver_lineage is None:
        return "resolver lineage is required"
    if context.current_bar is None:
        return "current bar is required"
    if not context.historical_bars:
        return "historical bars are required"
    if not context.symbol.strip():
        return "symbol is required"
    if context.trading_day is None:
        return "trading_day is required"
    future_bars = tuple(
        bar for bar in context.historical_bars if bar.bar_ts > context.current_bar.bar_ts
    )
    if future_bars:
        return "historical bars must not include bars after current_bar"
    if context.current_bar not in context.historical_bars:
        return "historical bars must include current_bar"
    return None
