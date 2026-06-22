from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from futures_mvp.modules.market_data.consumer import ResolverConsumerContext
from futures_mvp.modules.strategy_runtime.models import (
    StrategyDecision,
    StrategyRuntimeResult,
)


class BacktestStatus(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    DATA_GAP = "DATA_GAP"
    INVALID_INPUT = "INVALID_INPUT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class BacktestRequest:
    strategy_name: str
    symbol: str
    start_trading_day: date
    end_trading_day: date
    timeframe: str
    initial_cash: Decimal
    resolver: Any | None
    data_provider: Any | None
    strategy_runtime: Any | None = None
    strategy: Any | None = None
    decision_translator: Any | None = None
    fill_model: Any | None = None


@dataclass(frozen=True)
class BacktestDiagnostics:
    messages: tuple[str, ...] = ()
    resolver_statuses: tuple[str, ...] = ()
    data_statuses: tuple[str, ...] = ()
    source_of_truth_notice: str = (
        "BacktestResult is research/observability only and is not OMS, Trade, "
        "Position, Accounting, broker, live execution, or real account truth."
    )


@dataclass(frozen=True)
class BacktestDataSummary:
    source: str
    timeframe: str
    start_trading_day: date
    end_trading_day: date
    bars_consumed_count: int
    trading_days_consumed: tuple[date, ...]
    diagnostics_summary: str


@dataclass(frozen=True)
class BacktestEquityPoint:
    trading_day: date
    ts: datetime
    equity: Decimal
    cash: Decimal


@dataclass(frozen=True)
class ResearchPosition:
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    side: str
    quantity: Decimal
    avg_price: Decimal
    resolver_lineage: ResolverConsumerContext
    market_value: Decimal = Decimal("0")
    source: str = "backtest_research_only_position"


@dataclass(frozen=True)
class ResearchPnLPoint:
    trading_day: date
    ts: datetime
    cash: Decimal
    position_quantity: Decimal
    avg_price: Decimal
    mark_price: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    equity: Decimal
    source: str = "backtest_research_only_pnl"


@dataclass(frozen=True)
class ResearchPortfolio:
    portfolio_id: str
    strategy_name: str
    initial_cash: Decimal
    cash: Decimal
    total_market_value: Decimal
    total_equity: Decimal
    positions: tuple[ResearchPosition, ...]
    pnl_points: tuple[ResearchPnLPoint, ...]
    diagnostics: tuple[str, ...]


class SimulatedOrderStatus(StrEnum):
    CREATED = "CREATED"
    REJECTED = "REJECTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class SimulatedOrderIntent(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class DecisionTranslationStatus(StrEnum):
    CREATED = "CREATED"
    SKIPPED = "SKIPPED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class FillModelStatus(StrEnum):
    NO_FILL = "NO_FILL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    DATA_GAP = "DATA_GAP"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class SimulatedOrder:
    order_id: str
    strategy_name: str
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    side: str
    quantity: Decimal
    expected_price: Decimal
    order_type: str
    created_bar_ts: datetime
    resolver_source: str
    resolver_confidence: str
    resolver_lineage: ResolverConsumerContext
    diagnostics: tuple[str, ...] = ()
    status: SimulatedOrderStatus = SimulatedOrderStatus.CREATED
    intent: SimulatedOrderIntent = SimulatedOrderIntent.ENTRY
    source: str = "backtest_research_only_simulated_order"


@dataclass(frozen=True)
class SimulatedTrade:
    trade_id: str
    order_id: str
    fill_price: Decimal
    fill_qty: Decimal
    fill_bar_ts: datetime
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    resolver_source: str
    resolver_confidence: str
    resolver_lineage: ResolverConsumerContext
    diagnostics: tuple[str, ...] = ()
    intent: SimulatedOrderIntent = SimulatedOrderIntent.ENTRY
    source: str = "backtest_research_only_simulated_trade"


@dataclass(frozen=True)
class DecisionTranslationResult:
    status: DecisionTranslationStatus
    simulated_order: SimulatedOrder | None = None
    simulated_trades: tuple[SimulatedTrade, ...] = ()
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class FillModelResult:
    status: FillModelStatus
    simulated_trade: SimulatedTrade | None = None
    diagnostics: tuple[str, ...] = ()


BacktestSimulatedOrder = SimulatedOrder
BacktestSimulatedTrade = SimulatedTrade


@dataclass(frozen=True)
class BacktestResult:
    status: BacktestStatus
    diagnostics: BacktestDiagnostics
    resolver_lineage: tuple[ResolverConsumerContext, ...] = ()
    data_source_summary: BacktestDataSummary | None = None
    bars_consumed_count: int = 0
    equity_curve: tuple[BacktestEquityPoint, ...] = ()
    strategy_runtime_results: tuple[StrategyRuntimeResult, ...] = ()
    strategy_decisions: tuple[StrategyDecision, ...] = ()
    decision_translation_results: tuple[DecisionTranslationResult, ...] = ()
    fill_model_results: tuple[FillModelResult, ...] = ()
    simulated_orders: tuple[SimulatedOrder, ...] = ()
    simulated_trades: tuple[SimulatedTrade, ...] = ()
    research_positions: tuple[ResearchPosition, ...] = ()
    research_pnl_curve: tuple[ResearchPnLPoint, ...] = ()
    research_portfolio: ResearchPortfolio | None = None
    gap_report: tuple[str, ...] = ()
