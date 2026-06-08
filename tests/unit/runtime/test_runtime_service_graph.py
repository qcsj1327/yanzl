from futures_mvp.domain.enums import RiskResultStatus
from futures_mvp.domain.models import (
    Trade,
    TradingRiskResult,
    TradingWorkflowContext,
)
from futures_mvp.modules.runtime import (
    RuntimeConfig,
    RuntimeServiceGraphBuilder,
    ServiceGraphDependencies,
    required_service_names,
)


class FakeRiskEvaluator:
    def evaluate(self, context: TradingWorkflowContext) -> TradingRiskResult:
        return TradingRiskResult(
            risk_result_id="risk-1",
            signal_id=context.signal_decision.signal_id,
            status=RiskResultStatus.ACCEPTED,
            rule_name="fake",
            reason=None,
            checked_at=context.signal_decision.bar_ts,
            raw_payload={},
        )


class FakeTradeRepository:
    def __init__(self) -> None:
        self.trades: list[Trade] = []

    def append_trade(self, trade: Trade) -> Trade:
        self.trades.append(trade)
        return trade

    def create_or_get_trade(self, trade: Trade) -> Trade:
        self.trades.append(trade)
        return trade

    def get_by_exchange_trade_id(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None:
        del account_id, exchange, exchange_trade_id
        return None

    def get_by_trade_identity(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None:
        del account_id, exchange, exchange_trade_id
        return None

    def list_by_order_id(self, order_id: str) -> list[Trade]:
        del order_id
        return []


def test_service_graph_builds_required_slots() -> None:
    graph = RuntimeServiceGraphBuilder(
        RuntimeConfig(runtime_id="runtime-1", environment="test"),
        ServiceGraphDependencies(
            risk_evaluator=FakeRiskEvaluator(),
            trade_repository=FakeTradeRepository(),
        ),
    ).build()

    assert graph.validate_required_services()
    assert all(getattr(graph, name) is not None for name in required_service_names())


def test_required_service_names_include_full_business_chain() -> None:
    assert required_service_names() == (
        "market",
        "feature",
        "strategy",
        "signal_lifecycle",
        "trading_workflow",
        "oms",
        "oms_bridge",
        "execution_gateway",
        "execution_reports",
        "oms_event_application",
        "oms_to_trade",
        "position",
        "margin",
        "pnl",
        "settlement",
    )
