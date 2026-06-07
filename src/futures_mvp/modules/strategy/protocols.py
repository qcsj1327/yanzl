from typing import Protocol

from futures_mvp.domain.models import SignalDecision, StrategyContext, StrategyResult


class Strategy(Protocol):
    def generate_signal(self, context: StrategyContext) -> SignalDecision | StrategyResult: ...
