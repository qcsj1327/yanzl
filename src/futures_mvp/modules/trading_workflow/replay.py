from collections.abc import Iterable

from futures_mvp.domain.models import TradingWorkflowContext, TradingWorkflowResult
from futures_mvp.modules.trading_workflow.service import TradingWorkflowService


class TradingWorkflowReplay:
    def __init__(self, service: TradingWorkflowService) -> None:
        self._service = service

    def replay(
        self,
        contexts: Iterable[TradingWorkflowContext],
    ) -> list[TradingWorkflowResult]:
        ordered = sorted(
            contexts,
            key=lambda context: (
                context.signal_decision.exchange,
                context.signal_decision.instrument_id,
                context.signal_decision.timeframe.value,
                context.signal_decision.bar_ts,
                context.signal_decision.signal_id,
                context.risk_config_hash,
            ),
        )
        return [self._service.run(context) for context in ordered]
