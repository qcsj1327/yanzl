from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy.orm import Session

from futures_mvp.db.unit_of_work import SQLAlchemyExecutionReportUnitOfWork, SQLAlchemyUnitOfWork
from futures_mvp.interfaces.repositories import (
    ExecutionGatewayUnitOfWork,
    ExecutionReportUnitOfWork,
    FeatureUnitOfWork,
    MarketDataUnitOfWork,
    StrategySignalUnitOfWork,
    TradeRepository,
    TradingWorkflowUnitOfWork,
    UnitOfWork,
)
from futures_mvp.modules.execution_gateway.adapters import MockExecutionAdapter
from futures_mvp.modules.execution_gateway.protocols import ExecutionAdapter
from futures_mvp.modules.execution_gateway.service import ExecutionGatewayService
from futures_mvp.modules.execution_reports.service import ExecutionReportNormalizer
from futures_mvp.modules.feature.service import FeatureService
from futures_mvp.modules.margin.engine import MarginEngine
from futures_mvp.modules.market.service import MarketDataService
from futures_mvp.modules.oms.service import OMSService
from futures_mvp.modules.oms_bridge.service import OMSBridgeService
from futures_mvp.modules.oms_event_application.service import OMSEventApplicationService
from futures_mvp.modules.oms_to_trade.service import OMSToTradeBridgeService
from futures_mvp.modules.pnl.engine import PnLEngine
from futures_mvp.modules.position.manager import PositionManager
from futures_mvp.modules.runtime.config import RuntimeConfig
from futures_mvp.modules.settlement.engine import SettlementEngine
from futures_mvp.modules.strategy.service import SignalLifecycleService, StrategyService
from futures_mvp.modules.trading_workflow.protocols import RiskEvaluator
from futures_mvp.modules.trading_workflow.service import TradingWorkflowService

UoWFactory = Callable[[], UnitOfWork]
ExecutionReportUoWFactory = Callable[[], ExecutionReportUnitOfWork]


class ServiceGraphError(RuntimeError):
    """Raised when the runtime service graph cannot be wired safely."""


@dataclass(frozen=True)
class RuntimeServiceGraph:
    config: RuntimeConfig
    uow_factory: UoWFactory
    execution_report_uow_factory: ExecutionReportUoWFactory
    market: MarketDataService
    feature: FeatureService
    strategy: StrategyService
    signal_lifecycle: SignalLifecycleService
    trading_workflow: TradingWorkflowService
    oms: OMSService
    oms_bridge: OMSBridgeService
    execution_gateway: ExecutionGatewayService
    execution_reports: ExecutionReportNormalizer
    oms_event_application: OMSEventApplicationService
    oms_to_trade: OMSToTradeBridgeService
    position: PositionManager
    margin: MarginEngine
    pnl: PnLEngine
    settlement: SettlementEngine

    def validate_required_services(self) -> bool:
        return all(getattr(self, field) is not None for field in required_service_names())


def _default_uow_factory() -> UnitOfWork:
    return cast(UnitOfWork, SQLAlchemyUnitOfWork())


def _default_execution_report_uow_factory() -> ExecutionReportUnitOfWork:
    return cast(ExecutionReportUnitOfWork, SQLAlchemyExecutionReportUnitOfWork())


@dataclass(frozen=True)
class ServiceGraphDependencies:
    risk_evaluator: RiskEvaluator
    trade_repository: TradeRepository
    uow_factory: UoWFactory = _default_uow_factory
    execution_report_uow_factory: ExecutionReportUoWFactory = (
        _default_execution_report_uow_factory
    )
    execution_adapter: ExecutionAdapter | None = None


class RuntimeServiceGraphBuilder:
    def __init__(
        self,
        config: RuntimeConfig,
        dependencies: ServiceGraphDependencies,
    ) -> None:
        self._config = config
        self._dependencies = dependencies

    def build(self) -> RuntimeServiceGraph:
        deps = self._dependencies
        adapter = deps.execution_adapter or MockExecutionAdapter()

        def clock() -> datetime:
            return datetime.now(UTC)

        uow_factory = deps.uow_factory
        market_uow_factory = cast(Callable[[], MarketDataUnitOfWork], uow_factory)
        feature_uow_factory = cast(Callable[[], FeatureUnitOfWork], uow_factory)
        strategy_uow_factory = cast(Callable[[], StrategySignalUnitOfWork], uow_factory)
        workflow_uow_factory = cast(Callable[[], TradingWorkflowUnitOfWork], uow_factory)
        execution_gateway_uow_factory = cast(
            Callable[[], ExecutionGatewayUnitOfWork],
            uow_factory,
        )
        execution_report_uow_factory = deps.execution_report_uow_factory
        oms = OMSService(uow_factory, clock=clock)
        graph = RuntimeServiceGraph(
            config=self._config,
            uow_factory=uow_factory,
            execution_report_uow_factory=execution_report_uow_factory,
            market=MarketDataService(market_uow_factory),
            feature=FeatureService(feature_uow_factory),
            strategy=StrategyService(strategy_uow_factory),
            signal_lifecycle=SignalLifecycleService(strategy_uow_factory),
            trading_workflow=TradingWorkflowService(workflow_uow_factory, deps.risk_evaluator),
            oms=oms,
            oms_bridge=OMSBridgeService(oms),
            execution_gateway=ExecutionGatewayService(execution_gateway_uow_factory, adapter),
            execution_reports=ExecutionReportNormalizer(execution_report_uow_factory),
            oms_event_application=OMSEventApplicationService(oms_applier=oms),
            oms_to_trade=OMSToTradeBridgeService(deps.trade_repository),
            position=PositionManager(uow_factory),
            margin=MarginEngine(uow_factory),
            pnl=PnLEngine(uow_factory),
            settlement=SettlementEngine(uow_factory),
        )
        if not graph.validate_required_services():
            raise ServiceGraphError("runtime service graph is missing required services")
        return graph


def required_service_names() -> tuple[str, ...]:
    return (
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


def db_reachable(session_factory: Callable[[], Session]) -> bool:
    try:
        session = session_factory()
    except Exception:
        return False
    try:
        session.connection()
    except Exception:
        return False
    finally:
        session.close()
    return True
