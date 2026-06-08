from collections.abc import Iterable

from futures_mvp.domain.models import TradeBridgeContext, TradeBridgeResult
from futures_mvp.modules.oms_to_trade.service import OMSToTradeBridgeService


def replay_oms_to_trade(
    contexts: Iterable[TradeBridgeContext],
    *,
    service: OMSToTradeBridgeService,
) -> list[TradeBridgeResult]:
    ordered_contexts = sorted(
        contexts,
        key=lambda context: (
            context.normalized_report.report_ts,
            context.normalized_report.report_id,
        ),
    )
    return [service.create_trade(context) for context in ordered_contexts]
