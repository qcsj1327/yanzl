from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from inspect import signature
from typing import Any, cast

from futures_mvp.modules.backtest.costs import FixedCommissionModel
from futures_mvp.modules.backtest.fill_model import NoFillModel
from futures_mvp.modules.backtest.models import (
    BacktestDataSummary,
    BacktestDiagnostics,
    BacktestEquityPoint,
    BacktestRequest,
    BacktestResult,
    BacktestStatus,
    DecisionTranslationResult,
    DecisionTranslationStatus,
    FillModelResult,
    FillModelStatus,
    ResearchPnLPoint,
    ResearchPortfolio,
    ResearchPosition,
    SimulatedOrder,
    SimulatedOrderIntent,
    SimulatedTrade,
)
from futures_mvp.modules.backtest.portfolio import FixedCashAllocation, PortfolioAggregator
from futures_mvp.modules.backtest.sizing import FixedCashSizing, FixedQuantitySizing
from futures_mvp.modules.backtest.translator import DecisionTranslator
from futures_mvp.modules.market_data.consumer import (
    ResolverConsumerContext,
    build_resolver_consumer_context,
)
from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    HistoricalBar,
    HistoricalDataStatus,
    MarketDataSource,
)
from futures_mvp.modules.market_data.models import InstrumentResolveStatus
from futures_mvp.modules.strategy_runtime import (
    NoOpStrategy,
    StrategyContext,
    StrategyDecision,
    StrategyRuntime,
    StrategyRuntimeResult,
    StrategyRuntimeStatus,
)
from futures_mvp.modules.strategy_runtime.strategies import StrategyEvaluator

_STATIC_FIXTURE_SOURCE = "static_historical_fixture"
_DEFAULT_DATA_SOURCE = MarketDataSource.STATIC_FIXTURE.value
_READ_ONLY_ADAPTER_SOURCE = MarketDataSource.READ_ONLY_ADAPTER.value
_NOOP_STRATEGY_NAME = "noop"
_STRATEGY_CONFIG_PLACEHOLDER = {"strategy_runtime_stage": "V.5", "strategy": "noop"}
_PORTFOLIO_SNAPSHOT_SOURCE = "backtest_research_placeholder"


@dataclass(frozen=True)
class _ResearchAccountingResult:
    equity_curve: tuple[BacktestEquityPoint, ...]
    positions: tuple[ResearchPosition, ...]
    pnl_curve: tuple[ResearchPnLPoint, ...]
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class _SymbolBars:
    symbol: str
    trading_day: date
    resolver_context: ResolverConsumerContext
    bars: tuple[HistoricalBar, ...]


class LocalBacktestEngine:
    def __init__(
        self,
        strategy_runtime: Any | None = None,
        strategy: StrategyEvaluator | None = None,
        decision_translator: Any | None = None,
        fill_model: Any | None = None,
        commission_model: Any | None = None,
        slippage_model: Any | None = None,
    ) -> None:
        self._strategy = strategy or NoOpStrategy()
        self._strategy_runtime = strategy_runtime or StrategyRuntime(self._strategy)
        self._decision_translator = decision_translator or DecisionTranslator()
        self._fill_model: Any = fill_model or NoFillModel()
        self._commission_model = commission_model
        self._slippage_model = slippage_model

    def run(self, request: BacktestRequest) -> BacktestResult:
        validation_error = _validate_request(request)
        if validation_error is not None:
            return _result(
                BacktestStatus.INVALID_INPUT,
                messages=(validation_error,),
            )
        resolver = request.resolver
        data_provider = request.data_provider
        data_source = _request_data_source(request)
        if resolver is None:
            return _result(
                BacktestStatus.INVALID_INPUT,
                messages=("resolver is required",),
            )
        if data_provider is None:
            if data_source == _READ_ONLY_ADAPTER_SOURCE:
                return BacktestResult(
                    status=BacktestStatus.BLOCKED,
                    diagnostics=BacktestDiagnostics(
                        messages=(
                            "只读行情适配器未配置",
                            f"data_source={_READ_ONLY_ADAPTER_SOURCE}",
                            "不会访问网络，不连接 Broker、CTP、SimNow，不启用实盘或执行目标",
                        ),
                        data_statuses=(f"data_source:{_READ_ONLY_ADAPTER_SOURCE}:BLOCKED",),
                    ),
                    data_source_summary=BacktestDataSummary(
                        source=_READ_ONLY_ADAPTER_SOURCE,
                        timeframe=request.timeframe.strip().lower(),
                        start_trading_day=request.start_trading_day,
                        end_trading_day=request.end_trading_day,
                        bars_consumed_count=0,
                        trading_days_consumed=(),
                        diagnostics_summary="只读行情适配器未配置",
                    ),
                )
            return _result(
                BacktestStatus.INVALID_INPUT,
                messages=("data provider is required",),
            )

        try:
            timeframe = BarTimeframe(request.timeframe.strip().lower())
            symbols = _request_symbols(request)
            allocation = FixedCashAllocation(
                initial_cash=request.initial_cash,
                symbols=symbols,
                allocation_per_symbol_override=request.allocation_per_symbol,
            )
            contexts: list[ResolverConsumerContext] = []
            symbol_bars: list[_SymbolBars] = []
            strategy_runtime_results: list[StrategyRuntimeResult] = []
            strategy_decisions: list[StrategyDecision] = []
            decision_translation_results: list[DecisionTranslationResult] = []
            fill_model_results: list[FillModelResult] = []
            simulated_orders: list[SimulatedOrder] = []
            simulated_trades: list[SimulatedTrade] = []
            lifecycle_closed_by_symbol = {symbol: False for symbol in symbols}
            resolver_statuses: list[str] = []
            data_statuses: list[str] = []
            gap_report: list[str] = []
            data_diagnostics: list[str] = []

            for symbol in symbols:
                for trading_day in _trading_days(
                    request.start_trading_day,
                    request.end_trading_day,
                ):
                    resolution = resolver.resolve(symbol, trading_day)
                    resolver_statuses.append(
                        f"{symbol}:{trading_day}:{resolution.status.value}"
                    )
                    if resolution.status is not InstrumentResolveStatus.RESOLVED:
                        return _result(
                            BacktestStatus.BLOCKED,
                            messages=(
                                "resolver did not return RESOLVED",
                                f"symbol={symbol}",
                                f"trading_day={trading_day}",
                                f"resolver_status={resolution.status.value}",
                                *_as_tuple(resolution.diagnostics),
                            ),
                            resolver_statuses=tuple(resolver_statuses),
                        )

                    context_result = build_resolver_consumer_context(resolution)
                    if context_result.blocked or context_result.context is None:
                        return _result(
                            BacktestStatus.BLOCKED,
                            messages=(
                                context_result.reason
                                or "resolver consumer context blocked",
                                f"symbol={symbol}",
                                f"trading_day={trading_day}",
                            ),
                            resolver_statuses=tuple(resolver_statuses),
                        )
                    contexts.append(context_result.context)

                    if data_source == _READ_ONLY_ADAPTER_SOURCE:
                        bars_result = data_provider.get_bars(
                            context_result.context,
                            timeframe,
                        )
                    else:
                        bars_result = data_provider.get_bars(
                            symbol,
                            trading_day,
                            timeframe,
                        )
                    data_statuses.append(f"{symbol}:{trading_day}:{bars_result.status.value}")
                    data_diagnostics.extend(bars_result.diagnostics)
                    if bars_result.status is HistoricalDataStatus.INVALID_INPUT:
                        return _result(
                            BacktestStatus.INVALID_INPUT,
                            messages=(
                                "historical data provider rejected request",
                                f"symbol={symbol}",
                                f"trading_day={trading_day}",
                                *bars_result.diagnostics,
                            ),
                            resolver_statuses=tuple(resolver_statuses),
                            data_statuses=tuple(data_statuses),
                            resolver_lineage=tuple(contexts),
                        )
                    if bars_result.status is not HistoricalDataStatus.OK:
                        gap_report.append(
                            _symbol_day_message(
                                symbol=symbol,
                                trading_day=trading_day,
                                message=(
                                    "bars unavailable, "
                                    f"status={bars_result.status.value}"
                                ),
                                include_symbol=len(symbols) > 1,
                            )
                        )
                        return _data_gap_result(
                            request,
                            contexts=tuple(contexts),
                            resolver_statuses=tuple(resolver_statuses),
                            data_statuses=tuple(data_statuses),
                            gap_report=tuple(gap_report),
                            data_diagnostics=tuple(data_diagnostics),
                        )
                    if not bars_result.bars:
                        gap_report.append(
                            _symbol_day_message(
                                symbol=symbol,
                                trading_day=trading_day,
                                message="bars empty",
                                include_symbol=len(symbols) > 1,
                            )
                        )
                        return _data_gap_result(
                            request,
                            contexts=tuple(contexts),
                            resolver_statuses=tuple(resolver_statuses),
                            data_statuses=tuple(data_statuses),
                            gap_report=tuple(gap_report),
                            data_diagnostics=tuple(data_diagnostics),
                        )
                    symbol_bars.append(
                        _SymbolBars(
                            symbol=symbol,
                            trading_day=trading_day,
                            resolver_context=context_result.context,
                            bars=bars_result.bars,
                        )
                    )

            all_bars = tuple(bar for item in symbol_bars for bar in item.bars)
            data_summary = _data_summary(
                request,
                bars_consumed_count=len(all_bars),
                trading_days_consumed=tuple(
                    dict.fromkeys(item.trading_day for item in symbol_bars)
                ),
                diagnostics=tuple(data_diagnostics),
            )
            for item in symbol_bars:
                context = item.resolver_context
                bars = item.bars
                for index, bar in enumerate(bars):
                    if lifecycle_closed_by_symbol[item.symbol]:
                        break
                    runtime_result = self._run_strategy(
                        request=request,
                        allocation=allocation,
                        resolver_context=context,
                        data_summary=data_summary,
                        current_bar=bar,
                        historical_bars=bars[: index + 1],
                    )
                    strategy_runtime_results.append(runtime_result)
                    if runtime_result.status is StrategyRuntimeStatus.BLOCKED:
                        return BacktestResult(
                            status=BacktestStatus.BLOCKED,
                            diagnostics=BacktestDiagnostics(
                                messages=(
                                    "strategy runtime blocked",
                                    *runtime_result.diagnostics,
                                ),
                                resolver_statuses=tuple(resolver_statuses),
                                data_statuses=tuple(data_statuses),
                            ),
                            resolver_lineage=tuple(contexts),
                            data_source_summary=data_summary,
                            bars_consumed_count=len(all_bars),
                            strategy_runtime_results=tuple(strategy_runtime_results),
                            strategy_decisions=tuple(strategy_decisions),
                            decision_translation_results=tuple(
                                decision_translation_results
                            ),
                            fill_model_results=tuple(fill_model_results),
                            simulated_orders=tuple(simulated_orders),
                            simulated_trades=tuple(simulated_trades),
                        )
                    if runtime_result.status is not StrategyRuntimeStatus.COMPLETED:
                        return BacktestResult(
                            status=BacktestStatus.ERROR,
                            diagnostics=BacktestDiagnostics(
                                messages=(
                                    "strategy runtime failed",
                                    *runtime_result.diagnostics,
                                ),
                                resolver_statuses=tuple(resolver_statuses),
                                data_statuses=tuple(data_statuses),
                            ),
                            resolver_lineage=tuple(contexts),
                            data_source_summary=data_summary,
                            bars_consumed_count=len(all_bars),
                            strategy_runtime_results=tuple(strategy_runtime_results),
                            strategy_decisions=tuple(strategy_decisions),
                            decision_translation_results=tuple(
                                decision_translation_results
                            ),
                            fill_model_results=tuple(fill_model_results),
                            simulated_orders=tuple(simulated_orders),
                            simulated_trades=tuple(simulated_trades),
                        )
                    if runtime_result.decision is None:
                        return BacktestResult(
                            status=BacktestStatus.ERROR,
                            diagnostics=BacktestDiagnostics(
                                messages=("strategy runtime completed without decision",),
                                resolver_statuses=tuple(resolver_statuses),
                                data_statuses=tuple(data_statuses),
                            ),
                            resolver_lineage=tuple(contexts),
                            data_source_summary=data_summary,
                            bars_consumed_count=len(all_bars),
                            strategy_runtime_results=tuple(strategy_runtime_results),
                            strategy_decisions=tuple(strategy_decisions),
                            decision_translation_results=tuple(
                                decision_translation_results
                            ),
                            fill_model_results=tuple(fill_model_results),
                            simulated_orders=tuple(simulated_orders),
                            simulated_trades=tuple(simulated_trades),
                        )
                    strategy_decisions.append(runtime_result.decision)
                    translation_result = self._translate_decision(
                        request=request,
                        decision=runtime_result.decision,
                        resolver_context=context,
                        current_bar=bar,
                        allocation=allocation,
                    )
                    decision_translation_results.append(translation_result)
                    if translation_result.status is DecisionTranslationStatus.BLOCKED:
                        return BacktestResult(
                            status=BacktestStatus.BLOCKED,
                            diagnostics=BacktestDiagnostics(
                                messages=(
                                    "decision translator blocked",
                                    *translation_result.diagnostics,
                                ),
                                resolver_statuses=tuple(resolver_statuses),
                                data_statuses=tuple(data_statuses),
                            ),
                            resolver_lineage=tuple(contexts),
                            data_source_summary=data_summary,
                            bars_consumed_count=len(all_bars),
                            strategy_runtime_results=tuple(strategy_runtime_results),
                            strategy_decisions=tuple(strategy_decisions),
                            decision_translation_results=tuple(
                                decision_translation_results
                            ),
                            fill_model_results=tuple(fill_model_results),
                            simulated_orders=tuple(simulated_orders),
                            simulated_trades=tuple(simulated_trades),
                        )
                    if translation_result.status is DecisionTranslationStatus.ERROR:
                        return BacktestResult(
                            status=BacktestStatus.ERROR,
                            diagnostics=BacktestDiagnostics(
                                messages=(
                                    "decision translator failed",
                                    *translation_result.diagnostics,
                                ),
                                resolver_statuses=tuple(resolver_statuses),
                                data_statuses=tuple(data_statuses),
                            ),
                            resolver_lineage=tuple(contexts),
                            data_source_summary=data_summary,
                            bars_consumed_count=len(all_bars),
                            strategy_runtime_results=tuple(strategy_runtime_results),
                            strategy_decisions=tuple(strategy_decisions),
                            decision_translation_results=tuple(
                                decision_translation_results
                            ),
                            fill_model_results=tuple(fill_model_results),
                            simulated_orders=tuple(simulated_orders),
                            simulated_trades=tuple(simulated_trades),
                        )
                    if translation_result.simulated_trades:
                        return BacktestResult(
                            status=BacktestStatus.ERROR,
                            diagnostics=BacktestDiagnostics(
                                messages=(
                                    "decision translator generated simulated trades "
                                    "before fill model",
                                ),
                                resolver_statuses=tuple(resolver_statuses),
                                data_statuses=tuple(data_statuses),
                            ),
                            resolver_lineage=tuple(contexts),
                            data_source_summary=data_summary,
                            bars_consumed_count=len(all_bars),
                            strategy_runtime_results=tuple(strategy_runtime_results),
                            strategy_decisions=tuple(strategy_decisions),
                            decision_translation_results=tuple(
                                decision_translation_results
                            ),
                            fill_model_results=tuple(fill_model_results),
                            simulated_orders=tuple(simulated_orders),
                            simulated_trades=tuple(simulated_trades),
                        )
                    if translation_result.status is DecisionTranslationStatus.CREATED:
                        if translation_result.simulated_order is None:
                            return BacktestResult(
                                status=BacktestStatus.ERROR,
                                diagnostics=BacktestDiagnostics(
                                    messages=(
                                        "decision translator created result "
                                        "without simulated order",
                                    ),
                                    resolver_statuses=tuple(resolver_statuses),
                                    data_statuses=tuple(data_statuses),
                                ),
                                resolver_lineage=tuple(contexts),
                                data_source_summary=data_summary,
                                bars_consumed_count=len(all_bars),
                                strategy_runtime_results=tuple(
                                    strategy_runtime_results
                                ),
                                strategy_decisions=tuple(strategy_decisions),
                                decision_translation_results=tuple(
                                    decision_translation_results
                                ),
                                fill_model_results=tuple(fill_model_results),
                                simulated_orders=tuple(simulated_orders),
                                simulated_trades=tuple(simulated_trades),
                            )
                        simulated_order = translation_result.simulated_order
                        simulated_orders.append(simulated_order)
                        fill_result = self._fill_order(
                            request=request,
                            order=simulated_order,
                            bars=bars,
                        )
                        fill_model_results.append(fill_result)
                        if fill_result.status is FillModelStatus.FILLED:
                            if fill_result.simulated_trade is None:
                                return BacktestResult(
                                    status=BacktestStatus.ERROR,
                                    diagnostics=BacktestDiagnostics(
                                        messages=(
                                            "fill model returned FILLED without simulated trade",
                                        ),
                                        resolver_statuses=tuple(resolver_statuses),
                                        data_statuses=tuple(data_statuses),
                                    ),
                                    resolver_lineage=tuple(contexts),
                                    data_source_summary=data_summary,
                                    bars_consumed_count=len(all_bars),
                                    strategy_runtime_results=tuple(
                                        strategy_runtime_results
                                    ),
                                    strategy_decisions=tuple(strategy_decisions),
                                    decision_translation_results=tuple(
                                        decision_translation_results
                                    ),
                                    fill_model_results=tuple(fill_model_results),
                                    simulated_orders=tuple(simulated_orders),
                                    simulated_trades=tuple(simulated_trades),
                                )
                            trade = self._apply_commission(
                                request=request,
                                trade=fill_result.simulated_trade,
                            )
                            if isinstance(trade, FillModelResult):
                                fill_model_results[-1] = trade
                                return BacktestResult(
                                    status=BacktestStatus.BLOCKED,
                                    diagnostics=BacktestDiagnostics(
                                        messages=(
                                            "commission model blocked",
                                            *trade.diagnostics,
                                        ),
                                        resolver_statuses=tuple(resolver_statuses),
                                        data_statuses=tuple(data_statuses),
                                    ),
                                    resolver_lineage=tuple(contexts),
                                    data_source_summary=data_summary,
                                    bars_consumed_count=len(all_bars),
                                    strategy_runtime_results=tuple(
                                        strategy_runtime_results
                                    ),
                                    strategy_decisions=tuple(strategy_decisions),
                                    decision_translation_results=tuple(
                                        decision_translation_results
                                    ),
                                    fill_model_results=tuple(fill_model_results),
                                    simulated_orders=tuple(simulated_orders),
                                    simulated_trades=tuple(simulated_trades),
                                )
                            fill_model_results[-1] = replace(
                                fill_result,
                                simulated_trade=trade,
                            )
                            simulated_trades.append(trade)
                            if (
                                trade.intent
                                is SimulatedOrderIntent.EXIT
                            ):
                                lifecycle_closed_by_symbol[item.symbol] = True
                            continue
                        if fill_result.simulated_trade is not None:
                            return BacktestResult(
                                status=BacktestStatus.ERROR,
                                diagnostics=BacktestDiagnostics(
                                    messages=(
                                        "fill model generated simulated trade with "
                                        "non-FILLED status",
                                    ),
                                    resolver_statuses=tuple(resolver_statuses),
                                    data_statuses=tuple(data_statuses),
                                ),
                                resolver_lineage=tuple(contexts),
                                data_source_summary=data_summary,
                                bars_consumed_count=len(all_bars),
                                strategy_runtime_results=tuple(
                                    strategy_runtime_results
                                ),
                                strategy_decisions=tuple(strategy_decisions),
                                decision_translation_results=tuple(
                                    decision_translation_results
                                ),
                                fill_model_results=tuple(fill_model_results),
                                simulated_orders=tuple(simulated_orders),
                                simulated_trades=tuple(simulated_trades),
                            )
                        if fill_result.status is FillModelStatus.BLOCKED:
                            return BacktestResult(
                                status=BacktestStatus.BLOCKED,
                                diagnostics=BacktestDiagnostics(
                                    messages=(
                                        "fill model blocked",
                                        *fill_result.diagnostics,
                                    ),
                                    resolver_statuses=tuple(resolver_statuses),
                                    data_statuses=tuple(data_statuses),
                                ),
                                resolver_lineage=tuple(contexts),
                                data_source_summary=data_summary,
                                bars_consumed_count=len(all_bars),
                                strategy_runtime_results=tuple(
                                    strategy_runtime_results
                                ),
                                strategy_decisions=tuple(strategy_decisions),
                                decision_translation_results=tuple(
                                    decision_translation_results
                                ),
                                fill_model_results=tuple(fill_model_results),
                                simulated_orders=tuple(simulated_orders),
                                simulated_trades=tuple(simulated_trades),
                            )
                        if fill_result.status is FillModelStatus.ERROR:
                            return BacktestResult(
                                status=BacktestStatus.ERROR,
                                diagnostics=BacktestDiagnostics(
                                    messages=(
                                        "fill model failed",
                                        *fill_result.diagnostics,
                                    ),
                                    resolver_statuses=tuple(resolver_statuses),
                                    data_statuses=tuple(data_statuses),
                                ),
                                resolver_lineage=tuple(contexts),
                                data_source_summary=data_summary,
                                bars_consumed_count=len(all_bars),
                                strategy_runtime_results=tuple(
                                    strategy_runtime_results
                                ),
                                strategy_decisions=tuple(strategy_decisions),
                                decision_translation_results=tuple(
                                    decision_translation_results
                                ),
                                fill_model_results=tuple(fill_model_results),
                                simulated_orders=tuple(simulated_orders),
                                simulated_trades=tuple(simulated_trades),
                            )
                        if fill_result.status is FillModelStatus.DATA_GAP:
                            return BacktestResult(
                                status=BacktestStatus.DATA_GAP,
                                diagnostics=BacktestDiagnostics(
                                    messages=(
                                        "fill model data gap",
                                        *fill_result.diagnostics,
                                    ),
                                    resolver_statuses=tuple(resolver_statuses),
                                    data_statuses=tuple(data_statuses),
                                ),
                                resolver_lineage=tuple(contexts),
                                data_source_summary=data_summary,
                                bars_consumed_count=len(all_bars),
                                strategy_runtime_results=tuple(
                                    strategy_runtime_results
                                ),
                                strategy_decisions=tuple(strategy_decisions),
                                decision_translation_results=tuple(
                                    decision_translation_results
                                ),
                                fill_model_results=tuple(fill_model_results),
                                simulated_orders=tuple(simulated_orders),
                                simulated_trades=tuple(simulated_trades),
                                gap_report=tuple(fill_result.diagnostics),
                            )
                        if fill_result.status is not FillModelStatus.NO_FILL:
                            return BacktestResult(
                                status=BacktestStatus.ERROR,
                                diagnostics=BacktestDiagnostics(
                                    messages=(
                                        "fill model status is not supported before "
                                        "trade generation stage",
                                        f"fill_status={fill_result.status.value}",
                                    ),
                                    resolver_statuses=tuple(resolver_statuses),
                                    data_statuses=tuple(data_statuses),
                                ),
                                resolver_lineage=tuple(contexts),
                                data_source_summary=data_summary,
                                bars_consumed_count=len(all_bars),
                                strategy_runtime_results=tuple(
                                    strategy_runtime_results
                                ),
                                strategy_decisions=tuple(strategy_decisions),
                                decision_translation_results=tuple(
                                    decision_translation_results
                                ),
                                fill_model_results=tuple(fill_model_results),
                                simulated_orders=tuple(simulated_orders),
                                simulated_trades=tuple(simulated_trades),
                            )
            accounting_result = _research_position_pnl_and_equity(
                bars=all_bars,
                trades=tuple(simulated_trades),
                initial_cash=request.initial_cash,
            )
            if accounting_result.diagnostics:
                return BacktestResult(
                    status=BacktestStatus.BLOCKED,
                    diagnostics=BacktestDiagnostics(
                        messages=(
                            "research trade pairing failed closed",
                            *accounting_result.diagnostics,
                        ),
                        resolver_statuses=tuple(resolver_statuses),
                        data_statuses=tuple(data_statuses),
                    ),
                    resolver_lineage=tuple(contexts),
                    data_source_summary=data_summary,
                    bars_consumed_count=len(all_bars),
                    equity_curve=accounting_result.equity_curve,
                    strategy_runtime_results=tuple(strategy_runtime_results),
                    strategy_decisions=tuple(strategy_decisions),
                    decision_translation_results=tuple(decision_translation_results),
                    fill_model_results=tuple(fill_model_results),
                    simulated_orders=tuple(simulated_orders),
                    simulated_trades=tuple(simulated_trades),
                    research_positions=(),
                    research_pnl_curve=(),
                    research_portfolio=None,
                )
            equity_curve = accounting_result.equity_curve
            research_positions = accounting_result.positions
            research_pnl_curve = accounting_result.pnl_curve
            research_portfolio = _research_portfolio(
                request=request,
                positions=research_positions,
                pnl_points=research_pnl_curve,
                equity_curve=equity_curve,
            )
            return BacktestResult(
                status=BacktestStatus.COMPLETED,
                diagnostics=BacktestDiagnostics(
                    messages=(
                        "deterministic local research-only backtest completed",
                        "no OMS/Trade/Position/Accounting mutation",
                        "no DB write, broker, CTP, SimNow, live feed, or execution target",
                    ),
                    resolver_statuses=tuple(resolver_statuses),
                    data_statuses=tuple(data_statuses),
                ),
                resolver_lineage=tuple(contexts),
                data_source_summary=data_summary,
                bars_consumed_count=len(all_bars),
                equity_curve=equity_curve,
                strategy_runtime_results=tuple(strategy_runtime_results),
                strategy_decisions=tuple(strategy_decisions),
                decision_translation_results=tuple(decision_translation_results),
                fill_model_results=tuple(fill_model_results),
                simulated_orders=tuple(simulated_orders),
                simulated_trades=tuple(simulated_trades),
                research_positions=research_positions,
                research_pnl_curve=research_pnl_curve,
                research_portfolio=research_portfolio,
                gap_report=(),
            )
        except Exception as exc:  # pragma: no cover - defensive fail-closed wrapper
            return _result(
                BacktestStatus.ERROR,
                messages=(f"unexpected backtest error: {type(exc).__name__}: {exc}",),
            )

    def _run_strategy(
        self,
        *,
        request: BacktestRequest,
        allocation: FixedCashAllocation,
        resolver_context: ResolverConsumerContext,
        data_summary: BacktestDataSummary,
        current_bar: HistoricalBar,
        historical_bars: tuple[HistoricalBar, ...],
    ) -> StrategyRuntimeResult:
        runtime = request.strategy_runtime or self._strategy_runtime
        strategy = request.strategy or self._strategy
        context = StrategyContext(
            strategy_name=request.strategy_name,
            symbol=resolver_context.identity.symbol,
            instrument_id=resolver_context.identity.instrument_id,
            trade_instrument_id=resolver_context.identity.trade_instrument_id,
            exchange=resolver_context.identity.exchange,
            trading_day=current_bar.trading_day,
            timeframe=current_bar.timeframe,
            current_bar=current_bar,
            historical_bars=historical_bars,
            resolver_lineage=resolver_context,
            data_source_summary={
                "source": data_summary.source,
                "timeframe": data_summary.timeframe,
                "bars_consumed_count": data_summary.bars_consumed_count,
                "diagnostics_summary": data_summary.diagnostics_summary,
            },
            portfolio_snapshot=_portfolio_snapshot(allocation),
            config=_STRATEGY_CONFIG_PLACEHOLDER,
        )
        if hasattr(runtime, "run_with_strategy"):
            return cast(StrategyRuntimeResult, runtime.run_with_strategy(strategy, context))
        if request.strategy is not None and request.strategy_runtime is None:
            return StrategyRuntime(strategy).run(context)
        return cast(StrategyRuntimeResult, runtime.run(context))

    def _translate_decision(
        self,
        *,
        request: BacktestRequest,
        decision: StrategyDecision,
        resolver_context: ResolverConsumerContext,
        current_bar: HistoricalBar,
        allocation: FixedCashAllocation,
    ) -> DecisionTranslationResult:
        translator = request.decision_translator or self._decision_translator
        quantity_result = _order_quantity(
            request=request,
            allocation=allocation,
            expected_price=(
                decision.expected_price
                if decision.expected_price is not None
                else current_bar.close
            ),
        )
        if isinstance(quantity_result, str):
            return DecisionTranslationResult(
                status=DecisionTranslationStatus.BLOCKED,
                diagnostics=(quantity_result,),
            )
        quantity = quantity_result
        if isinstance(translator, DecisionTranslator):
            return translator.translate(
                strategy_name=request.strategy_name,
                decision=decision,
                resolver_lineage=resolver_context,
                current_bar=current_bar,
                quantity=quantity,
            )
        return cast(
            DecisionTranslationResult,
            translator.translate(
                strategy_name=request.strategy_name,
                decision=decision,
                resolver_lineage=resolver_context,
                current_bar=current_bar,
                quantity=quantity,
            ),
        )

    def _fill_order(
        self,
        *,
        request: BacktestRequest,
        order: SimulatedOrder,
        bars: tuple[HistoricalBar, ...],
    ) -> FillModelResult:
        fill_model = request.fill_model or self._fill_model
        slippage_model = request.slippage_model or self._slippage_model
        fill = fill_model.fill
        if len(signature(fill).parameters) >= 3:
            return cast(FillModelResult, fill(order, bars, slippage_model))
        if len(signature(fill).parameters) >= 2:
            return cast(FillModelResult, fill(order, bars))
        return cast(FillModelResult, fill(order))

    def _apply_commission(
        self,
        *,
        request: BacktestRequest,
        trade: SimulatedTrade,
    ) -> SimulatedTrade | FillModelResult:
        commission_model = request.commission_model or self._commission_model
        if commission_model is None:
            return trade
        if isinstance(commission_model, FixedCommissionModel):
            if commission_model.commission_rate < Decimal("0"):
                return FillModelResult(
                    status=FillModelStatus.BLOCKED,
                    diagnostics=("commission_rate must be non-negative",),
                )
            commission = commission_model.commission(
                fill_price=trade.fill_price,
                fill_qty=trade.fill_qty,
            )
        else:
            commission = cast(
                Decimal,
                commission_model.commission(
                    fill_price=trade.fill_price,
                    fill_qty=trade.fill_qty,
                ),
            )
            if commission < Decimal("0"):
                return FillModelResult(
                    status=FillModelStatus.BLOCKED,
                    diagnostics=("commission must be non-negative",),
                )
        return replace(
            trade,
            commission=commission,
            diagnostics=(
                *trade.diagnostics,
                f"commission={commission}",
            ),
        )


def run_backtest(request: BacktestRequest) -> BacktestResult:
    return LocalBacktestEngine().run(request)


def _validate_request(request: BacktestRequest) -> str | None:
    if not request.strategy_name.strip():
        return "strategy_name is required"
    if request.strategy_name != _NOOP_STRATEGY_NAME:
        return "only deterministic noop strategy is supported in Stage V.2"
    symbols = _request_symbols(request)
    if not symbols:
        return "symbol is required"
    if any(not symbol.strip() for symbol in symbols):
        return "symbols must be non-empty"
    if len(set(symbols)) != len(symbols):
        return "symbols must be unique"
    if request.quantity_mode not in ("fixed_quantity", "fixed_cash"):
        return "unknown sizing mode"
    if request.fixed_quantity <= Decimal("0"):
        return "fixed_quantity must be greater than 0"
    if request.allocation_mode not in ("equal_weight", "fixed_cash"):
        return "unknown allocation mode"
    if (
        request.allocation_per_symbol is not None
        and request.allocation_per_symbol <= Decimal("0")
    ):
        return "allocation_per_symbol must be greater than 0"
    if not isinstance(request.start_trading_day, date):
        return "start_trading_day is required"
    if not isinstance(request.end_trading_day, date):
        return "end_trading_day is required"
    if request.start_trading_day > request.end_trading_day:
        return "start_trading_day must be on or before end_trading_day"
    if not request.timeframe.strip():
        return "timeframe is required"
    try:
        BarTimeframe(request.timeframe.strip().lower())
    except ValueError:
        return "unsupported timeframe"
    if _request_data_source(request) not in (
        _DEFAULT_DATA_SOURCE,
        _READ_ONLY_ADAPTER_SOURCE,
    ):
        return "unsupported data_source"
    if request.initial_cash <= Decimal("0"):
        return "initial_cash must be greater than 0"
    if request.resolver is None:
        return "resolver is required"
    if not hasattr(request.resolver, "resolve"):
        return "resolver must provide resolve(symbol, trading_day)"
    if request.data_provider is None and _request_data_source(request) != (
        _READ_ONLY_ADAPTER_SOURCE
    ):
        return "data provider is required"
    if request.data_provider is not None and not hasattr(request.data_provider, "get_bars"):
        return "data provider must provide get_bars(symbol, trading_day, timeframe)"
    return None


def _order_quantity(
    *,
    request: BacktestRequest,
    allocation: FixedCashAllocation,
    expected_price: Decimal,
) -> Decimal | str:
    if expected_price <= Decimal("0"):
        return "sizing expected price must be greater than 0"
    if request.quantity_mode == "fixed_quantity":
        quantity = FixedQuantitySizing(request.fixed_quantity).quantity_for_price(
            expected_price
        )
    elif request.quantity_mode == "fixed_cash":
        quantity = FixedCashSizing(
            allocation.allocation_per_symbol()
        ).quantity_for_price(expected_price)
    else:
        return "unknown sizing mode"
    if quantity <= Decimal("0"):
        return "sized quantity must be greater than 0"
    return quantity


def _request_symbols(request: BacktestRequest) -> tuple[str, ...]:
    if request.symbols:
        return tuple(symbol.strip().lower() for symbol in request.symbols)
    return (request.symbol.strip().lower(),)


def _portfolio_snapshot(allocation: FixedCashAllocation) -> dict[str, object]:
    allocations = allocation.allocations()
    return {
        "source": _PORTFOLIO_SNAPSHOT_SOURCE,
        "positions": (),
        "cash_mode": "fixed_cash_allocation",
        "symbols": allocation.symbols,
        "allocation_per_symbol": allocation.allocation_per_symbol(),
        "allocations": allocations,
    }


def _symbol_day_message(
    *,
    symbol: str,
    trading_day: date,
    message: str,
    include_symbol: bool,
) -> str:
    if include_symbol:
        return f"{symbol}:{trading_day}: {message}"
    return f"{trading_day}: {message}"


def _trading_days(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def _flat_equity_curve(
    bars: tuple[HistoricalBar, ...],
    initial_cash: Decimal,
) -> tuple[BacktestEquityPoint, ...]:
    return tuple(
        BacktestEquityPoint(
            trading_day=bar.trading_day,
            ts=bar.bar_ts,
            equity=initial_cash,
            cash=initial_cash,
        )
        for bar in bars
    )


def _research_position_pnl_and_equity(
    *,
    bars: tuple[HistoricalBar, ...],
    trades: tuple[SimulatedTrade, ...],
    initial_cash: Decimal,
) -> _ResearchAccountingResult:
    if not trades:
        return _ResearchAccountingResult(_flat_equity_curve(bars, initial_cash), (), ())

    ordered_trades = tuple(sorted(trades, key=lambda trade: trade.fill_bar_ts))
    trades_by_identity: dict[tuple[str, str, str, str, date], list[SimulatedTrade]] = {}
    for trade in ordered_trades:
        trades_by_identity.setdefault(_research_trade_identity(trade), []).append(trade)
    for identity_trades in trades_by_identity.values():
        pairing_error = _validate_long_only_trade_pair(tuple(identity_trades))
        if pairing_error is not None:
            return _ResearchAccountingResult(
                _flat_equity_curve(bars, initial_cash),
                (),
                (),
                diagnostics=(pairing_error,),
            )

    cash = initial_cash
    quantities: dict[tuple[str, str, str, str, date], Decimal] = {}
    cost_basis_by_identity: dict[tuple[str, str, str, str, date], Decimal] = {}
    commission_by_identity: dict[tuple[str, str, str, str, date], Decimal] = {}
    realized_pnl_by_identity: dict[tuple[str, str, str, str, date], Decimal] = {}
    positions_by_identity: dict[tuple[str, str, str, str, date], ResearchPosition] = {}
    pnl_points: list[ResearchPnLPoint] = []
    equity_points: list[BacktestEquityPoint] = []

    for bar in sorted(bars, key=lambda item: item.bar_ts):
        for trade in ordered_trades:
            if trade.fill_bar_ts != bar.bar_ts or not _bar_matches_trade(bar, trade):
                continue
            identity = _research_trade_identity(trade)
            notional = trade.fill_price * trade.fill_qty
            quantity = quantities.get(identity, Decimal("0"))
            cost_basis = cost_basis_by_identity.get(identity, Decimal("0"))
            commission = commission_by_identity.get(identity, Decimal("0"))
            if trade.intent is SimulatedOrderIntent.ENTRY:
                cash -= notional + trade.commission
                if cash < Decimal("0"):
                    return _ResearchAccountingResult(
                        _flat_equity_curve(bars, initial_cash),
                        (),
                        (),
                        diagnostics=("negative cash after entry",),
                    )
                quantity += trade.fill_qty
                cost_basis += notional
                commission += trade.commission
                avg_price = cost_basis / quantity
                position = ResearchPosition(
                    symbol=trade.symbol,
                    instrument_id=trade.instrument_id,
                    trade_instrument_id=trade.trade_instrument_id,
                    exchange=trade.exchange,
                    trading_day=trade.trading_day,
                    side="LONG",
                    quantity=quantity,
                    avg_price=avg_price,
                    resolver_lineage=trade.resolver_lineage,
                )
            else:
                entry_price = cost_basis / quantity
                cash += notional - trade.commission
                if cash < Decimal("0"):
                    return _ResearchAccountingResult(
                        _flat_equity_curve(bars, initial_cash),
                        (),
                        (),
                        diagnostics=("negative cash after exit",),
                    )
                commission += trade.commission
                realized_pnl_by_identity[identity] = (
                    trade.fill_price - entry_price
                ) * trade.fill_qty - commission
                quantity -= trade.fill_qty
                cost_basis = Decimal("0")
                position = ResearchPosition(
                    symbol=trade.symbol,
                    instrument_id=trade.instrument_id,
                    trade_instrument_id=trade.trade_instrument_id,
                    exchange=trade.exchange,
                    trading_day=trade.trading_day,
                    side="FLAT",
                    quantity=Decimal("0"),
                    avg_price=Decimal("0"),
                    resolver_lineage=trade.resolver_lineage,
                )
            quantities[identity] = quantity
            cost_basis_by_identity[identity] = cost_basis
            commission_by_identity[identity] = commission
            positions_by_identity[identity] = position

        current_identity = _bar_identity(bar)
        current_position = positions_by_identity.get(current_identity)
        current_quantity = quantities.get(current_identity, Decimal("0"))
        avg_price = (
            current_position.avg_price
            if current_position is not None
            else Decimal("0")
        )
        current_market_value = current_quantity * bar.close
        if current_position is not None:
            positions_by_identity[current_identity] = ResearchPosition(
                symbol=current_position.symbol,
                instrument_id=current_position.instrument_id,
                trade_instrument_id=current_position.trade_instrument_id,
                exchange=current_position.exchange,
                trading_day=current_position.trading_day,
                side=current_position.side,
                quantity=current_quantity,
                avg_price=current_position.avg_price,
                resolver_lineage=current_position.resolver_lineage,
                market_value=current_market_value,
            )
        unrealized_pnl = (
            (bar.close - avg_price) * current_quantity
            if current_quantity
            else Decimal("0")
        )
        total_market_value = sum(
            (position.market_value for position in positions_by_identity.values()),
            Decimal("0"),
        )
        equity = cash + total_market_value
        equity_points.append(
            BacktestEquityPoint(
                trading_day=bar.trading_day,
                ts=bar.bar_ts,
                equity=equity,
                cash=cash,
            )
        )
        pnl_points.append(
            ResearchPnLPoint(
                trading_day=bar.trading_day,
                ts=bar.bar_ts,
                cash=cash,
                position_quantity=current_quantity,
                avg_price=avg_price,
                mark_price=bar.close,
                market_value=current_market_value,
                realized_pnl=realized_pnl_by_identity.get(
                    current_identity,
                    Decimal("0"),
                ),
                unrealized_pnl=unrealized_pnl,
                equity=equity,
                symbol=bar.symbol,
                commission=commission_by_identity.get(
                    current_identity,
                    Decimal("0"),
                ),
            )
        )

    positions = tuple(
        positions_by_identity[key] for key in sorted(positions_by_identity)
    )
    return _ResearchAccountingResult(tuple(equity_points), positions, tuple(pnl_points))


def _validate_long_only_trade_pair(trades: tuple[SimulatedTrade, ...]) -> str | None:
    entries = tuple(
        trade for trade in trades if trade.intent is SimulatedOrderIntent.ENTRY
    )
    exits = tuple(trade for trade in trades if trade.intent is SimulatedOrderIntent.EXIT)
    unsupported = tuple(
        trade
        for trade in trades
        if trade.intent
        not in (SimulatedOrderIntent.ENTRY, SimulatedOrderIntent.EXIT)
    )
    if unsupported:
        return "unsupported trade intent"
    if not entries:
        return "missing entry trade"
    if len(entries) > 1:
        return "duplicate entry trade"
    if len(exits) > 1:
        return "duplicate exit trade"
    if not exits:
        return None

    entry = entries[0]
    exit_trade = exits[0]
    if exit_trade.fill_bar_ts < entry.fill_bar_ts:
        return "exit before entry"
    if not _same_research_trade_identity(entry, exit_trade):
        return "mismatched identity"
    if exit_trade.fill_qty != entry.fill_qty:
        return "mismatched quantity"
    return None


def _same_research_trade_identity(
    entry: SimulatedTrade,
    exit_trade: SimulatedTrade,
) -> bool:
    return (
        entry.symbol == exit_trade.symbol
        and entry.instrument_id == exit_trade.instrument_id
        and entry.trade_instrument_id == exit_trade.trade_instrument_id
        and entry.exchange == exit_trade.exchange
        and entry.trading_day == exit_trade.trading_day
        and entry.resolver_lineage == exit_trade.resolver_lineage
    )


def _research_trade_identity(
    trade: SimulatedTrade,
) -> tuple[str, str, str, str, date]:
    return (
        trade.symbol,
        trade.instrument_id,
        trade.trade_instrument_id,
        trade.exchange,
        trade.trading_day,
    )


def _bar_identity(bar: HistoricalBar) -> tuple[str, str, str, str, date]:
    return (
        bar.symbol,
        bar.instrument_id,
        bar.trade_instrument_id,
        bar.exchange,
        bar.trading_day,
    )


def _bar_matches_trade(bar: HistoricalBar, trade: SimulatedTrade) -> bool:
    return _bar_identity(bar) == _research_trade_identity(trade)


def _research_portfolio(
    *,
    request: BacktestRequest,
    positions: tuple[ResearchPosition, ...],
    pnl_points: tuple[ResearchPnLPoint, ...],
    equity_curve: tuple[BacktestEquityPoint, ...],
) -> ResearchPortfolio | None:
    if not positions:
        return None
    cash = pnl_points[-1].cash if pnl_points else request.initial_cash
    return PortfolioAggregator(
        strategy_name=request.strategy_name,
        initial_cash=request.initial_cash,
    ).aggregate(
        positions=positions,
        pnl_points=pnl_points,
        cash=cash,
        portfolio_equity_curve=equity_curve,
        diagnostics=("aggregated from LocalBacktestEngine research outputs",),
    )


def _data_gap_result(
    request: BacktestRequest,
    *,
    contexts: tuple[ResolverConsumerContext, ...],
    resolver_statuses: tuple[str, ...],
    data_statuses: tuple[str, ...],
    gap_report: tuple[str, ...],
    data_diagnostics: tuple[str, ...],
) -> BacktestResult:
    data_source = _request_data_source(request)
    status = (
        BacktestStatus.BLOCKED
        if data_source == _READ_ONLY_ADAPTER_SOURCE
        else BacktestStatus.DATA_GAP
    )
    message = (
        "真实行情不可用，回测失败关闭"
        if status is BacktestStatus.BLOCKED
        else "missing bars fail closed before strategy evaluation"
    )
    return BacktestResult(
        status=status,
        diagnostics=BacktestDiagnostics(
            messages=(message,),
            resolver_statuses=resolver_statuses,
            data_statuses=data_statuses,
        ),
        resolver_lineage=contexts,
        data_source_summary=_data_summary(
            request,
            bars_consumed_count=0,
            trading_days_consumed=(),
            diagnostics=data_diagnostics,
        ),
        bars_consumed_count=0,
        equity_curve=(),
        strategy_runtime_results=(),
        strategy_decisions=(),
        decision_translation_results=(),
        fill_model_results=(),
        simulated_orders=(),
        simulated_trades=(),
        gap_report=gap_report,
    )


def _data_summary(
    request: BacktestRequest,
    *,
    bars_consumed_count: int,
    trading_days_consumed: tuple[date, ...],
    diagnostics: tuple[str, ...],
) -> BacktestDataSummary:
    return BacktestDataSummary(
        source=(
            _READ_ONLY_ADAPTER_SOURCE
            if _request_data_source(request) == _READ_ONLY_ADAPTER_SOURCE
            else _STATIC_FIXTURE_SOURCE
        ),
        timeframe=request.timeframe.strip().lower(),
        start_trading_day=request.start_trading_day,
        end_trading_day=request.end_trading_day,
        bars_consumed_count=bars_consumed_count,
        trading_days_consumed=trading_days_consumed,
        diagnostics_summary="; ".join(dict.fromkeys(diagnostics)),
    )


def _request_data_source(request: BacktestRequest) -> str:
    return request.data_source.strip() or _DEFAULT_DATA_SOURCE


def _result(
    status: BacktestStatus,
    *,
    messages: tuple[str, ...],
    resolver_statuses: tuple[str, ...] = (),
    data_statuses: tuple[str, ...] = (),
    resolver_lineage: tuple[ResolverConsumerContext, ...] = (),
) -> BacktestResult:
    return BacktestResult(
        status=status,
        diagnostics=BacktestDiagnostics(
            messages=messages,
            resolver_statuses=resolver_statuses,
            data_statuses=data_statuses,
        ),
        resolver_lineage=resolver_lineage,
        strategy_runtime_results=(),
        strategy_decisions=(),
        decision_translation_results=(),
        fill_model_results=(),
        simulated_orders=(),
        simulated_trades=(),
    )


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, tuple):
        return tuple(str(item) for item in value)
    return (str(value),)
