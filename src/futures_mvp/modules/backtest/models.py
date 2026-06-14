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
class BacktestSimulatedOrder:
    simulated_order_id: str
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    side: str
    quantity: Decimal
    source: str = "backtest_simulated_research_only"


@dataclass(frozen=True)
class BacktestSimulatedTrade:
    simulated_trade_id: str
    simulated_order_id: str
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    price: Decimal
    quantity: Decimal
    source: str = "backtest_simulated_research_only"


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
    simulated_orders: tuple[BacktestSimulatedOrder, ...] = ()
    simulated_trades: tuple[BacktestSimulatedTrade, ...] = ()
    gap_report: tuple[str, ...] = ()
