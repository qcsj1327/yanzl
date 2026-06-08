from typing import Protocol

from futures_mvp.domain.models import TradingRiskResult, TradingWorkflowContext


class RiskEvaluator(Protocol):
    def evaluate(self, context: TradingWorkflowContext) -> TradingRiskResult: ...
