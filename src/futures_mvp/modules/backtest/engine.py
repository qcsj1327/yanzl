from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from inspect import signature
from typing import Any, cast

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
from futures_mvp.modules.backtest.portfolio import PortfolioAggregator
from futures_mvp.modules.backtest.translator import DecisionTranslator
from futures_mvp.modules.market_data.consumer import (
    ResolverConsumerContext,
    build_resolver_consumer_context,
)
from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    HistoricalBar,
    HistoricalDataStatus,
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
_NOOP_STRATEGY_NAME = "noop"
_STRATEGY_CONFIG_PLACEHOLDER = {"strategy_runtime_stage": "V.5", "strategy": "noop"}
_PORTFOLIO_SNAPSHOT_PLACEHOLDER = {
    "source": "backtest_research_placeholder",
    "positions": (),
    "cash_mode": "flat_initial_cash",
}


@dataclass(frozen=True)
class _ResearchAccountingResult:
    equity_curve: tuple[BacktestEquityPoint, ...]
    positions: tuple[ResearchPosition, ...]
    pnl_curve: tuple[ResearchPnLPoint, ...]
    diagnostics: tuple[str, ...] = ()


class LocalBacktestEngine:
    def __init__(
        self,
        strategy_runtime: Any | None = None,
        strategy: StrategyEvaluator | None = None,
        decision_translator: Any | None = None,
        fill_model: Any | None = None,
    ) -> None:
        self._strategy = strategy or NoOpStrategy()
        self._strategy_runtime = strategy_runtime or StrategyRuntime(self._strategy)
        self._decision_translator = decision_translator or DecisionTranslator()
        self._fill_model: Any = fill_model or NoFillModel()

    def run(self, request: BacktestRequest) -> BacktestResult:
        validation_error = _validate_request(request)
        if validation_error is not None:
            return _result(
                BacktestStatus.INVALID_INPUT,
                messages=(validation_error,),
            )
        resolver = request.resolver
        data_provider = request.data_provider
        if resolver is None or data_provider is None:
            return _result(
                BacktestStatus.INVALID_INPUT,
                messages=("resolver and data provider are required",),
            )

        try:
            timeframe = BarTimeframe(request.timeframe.strip().lower())
            contexts: list[ResolverConsumerContext] = []
            bars_by_day: list[tuple[date, tuple[HistoricalBar, ...]]] = []
            strategy_runtime_results: list[StrategyRuntimeResult] = []
            strategy_decisions: list[StrategyDecision] = []
            decision_translation_results: list[DecisionTranslationResult] = []
            fill_model_results: list[FillModelResult] = []
            simulated_orders: list[SimulatedOrder] = []
            simulated_trades: list[SimulatedTrade] = []
            lifecycle_closed = False
            resolver_statuses: list[str] = []
            data_statuses: list[str] = []
            gap_report: list[str] = []
            data_diagnostics: list[str] = []

            for trading_day in _trading_days(
                request.start_trading_day,
                request.end_trading_day,
            ):
                resolution = resolver.resolve(request.symbol, trading_day)
                resolver_statuses.append(f"{trading_day}:{resolution.status.value}")
                if resolution.status is not InstrumentResolveStatus.RESOLVED:
                    return _result(
                        BacktestStatus.BLOCKED,
                        messages=(
                            "resolver did not return RESOLVED",
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
                            context_result.reason or "resolver consumer context blocked",
                            f"trading_day={trading_day}",
                        ),
                        resolver_statuses=tuple(resolver_statuses),
                    )
                contexts.append(context_result.context)

                bars_result = data_provider.get_bars(
                    request.symbol,
                    trading_day,
                    timeframe,
                )
                data_statuses.append(f"{trading_day}:{bars_result.status.value}")
                data_diagnostics.extend(bars_result.diagnostics)
                if bars_result.status is HistoricalDataStatus.INVALID_INPUT:
                    return _result(
                        BacktestStatus.INVALID_INPUT,
                        messages=(
                            "historical data provider rejected request",
                            f"trading_day={trading_day}",
                            *bars_result.diagnostics,
                        ),
                        resolver_statuses=tuple(resolver_statuses),
                        data_statuses=tuple(data_statuses),
                        resolver_lineage=tuple(contexts),
                    )
                if bars_result.status is not HistoricalDataStatus.OK:
                    gap_report.append(
                        f"{trading_day}: bars unavailable, status={bars_result.status.value}"
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
                    gap_report.append(f"{trading_day}: bars empty")
                    return _data_gap_result(
                        request,
                        contexts=tuple(contexts),
                        resolver_statuses=tuple(resolver_statuses),
                        data_statuses=tuple(data_statuses),
                        gap_report=tuple(gap_report),
                        data_diagnostics=tuple(data_diagnostics),
                    )
                bars_by_day.append((trading_day, bars_result.bars))

            all_bars = tuple(bar for _, bars in bars_by_day for bar in bars)
            data_summary = _data_summary(
                request,
                bars_consumed_count=len(all_bars),
                trading_days_consumed=tuple(day for day, _ in bars_by_day),
                diagnostics=tuple(data_diagnostics),
            )
            for context, (_, bars) in zip(contexts, bars_by_day, strict=True):
                for index, bar in enumerate(bars):
                    if lifecycle_closed:
                        break
                    runtime_result = self._run_strategy(
                        request=request,
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
                            simulated_trades.append(fill_result.simulated_trade)
                            if (
                                fill_result.simulated_trade.intent
                                is SimulatedOrderIntent.EXIT
                            ):
                                lifecycle_closed = True
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
            portfolio_snapshot=_PORTFOLIO_SNAPSHOT_PLACEHOLDER,
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
    ) -> DecisionTranslationResult:
        translator = request.decision_translator or self._decision_translator
        return cast(
            DecisionTranslationResult,
            translator.translate(
                strategy_name=request.strategy_name,
                decision=decision,
                resolver_lineage=resolver_context,
                current_bar=current_bar,
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
        fill = fill_model.fill
        if len(signature(fill).parameters) >= 2:
            return cast(FillModelResult, fill(order, bars))
        return cast(FillModelResult, fill(order))


def run_backtest(request: BacktestRequest) -> BacktestResult:
    return LocalBacktestEngine().run(request)


def _validate_request(request: BacktestRequest) -> str | None:
    if not request.strategy_name.strip():
        return "strategy_name is required"
    if request.strategy_name != _NOOP_STRATEGY_NAME:
        return "only deterministic noop strategy is supported in Stage V.2"
    if not request.symbol.strip():
        return "symbol is required"
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
    if request.initial_cash <= Decimal("0"):
        return "initial_cash must be greater than 0"
    if request.resolver is None:
        return "resolver is required"
    if not hasattr(request.resolver, "resolve"):
        return "resolver must provide resolve(symbol, trading_day)"
    if request.data_provider is None:
        return "data provider is required"
    if not hasattr(request.data_provider, "get_bars"):
        return "data provider must provide get_bars(symbol, trading_day, timeframe)"
    return None


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
    pairing_error = _validate_long_only_trade_pair(ordered_trades)
    if pairing_error is not None:
        return _ResearchAccountingResult(
            _flat_equity_curve(bars, initial_cash),
            (),
            (),
            diagnostics=(pairing_error,),
        )

    cash = initial_cash
    quantity = Decimal("0")
    cost_basis = Decimal("0")
    realized_pnl = Decimal("0")
    position: ResearchPosition | None = None
    pnl_points: list[ResearchPnLPoint] = []
    equity_points: list[BacktestEquityPoint] = []

    for bar in sorted(bars, key=lambda item: item.bar_ts):
        for trade in ordered_trades:
            if trade.fill_bar_ts == bar.bar_ts:
                notional = trade.fill_price * trade.fill_qty
                if trade.intent is SimulatedOrderIntent.ENTRY:
                    cash -= notional
                    quantity += trade.fill_qty
                    cost_basis += notional
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
                    cash += notional
                    realized_pnl = (trade.fill_price - entry_price) * trade.fill_qty
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

        avg_price = position.avg_price if position is not None else Decimal("0")
        market_value = quantity * bar.close
        if position is not None:
            position = ResearchPosition(
                symbol=position.symbol,
                instrument_id=position.instrument_id,
                trade_instrument_id=position.trade_instrument_id,
                exchange=position.exchange,
                trading_day=position.trading_day,
                side=position.side,
                quantity=quantity,
                avg_price=position.avg_price,
                resolver_lineage=position.resolver_lineage,
                market_value=market_value,
            )
        unrealized_pnl = (bar.close - avg_price) * quantity if quantity else Decimal("0")
        equity = cash + market_value
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
                position_quantity=quantity,
                avg_price=avg_price,
                mark_price=bar.close,
                market_value=market_value,
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl,
                equity=equity,
            )
        )

    positions = (position,) if position is not None else ()
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


def _research_portfolio(
    *,
    request: BacktestRequest,
    positions: tuple[ResearchPosition, ...],
    pnl_points: tuple[ResearchPnLPoint, ...],
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
    return BacktestResult(
        status=BacktestStatus.DATA_GAP,
        diagnostics=BacktestDiagnostics(
            messages=("missing bars fail closed before strategy evaluation",),
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
        source=_STATIC_FIXTURE_SOURCE,
        timeframe=request.timeframe.strip().lower(),
        start_trading_day=request.start_trading_day,
        end_trading_day=request.end_trading_day,
        bars_consumed_count=bars_consumed_count,
        trading_days_consumed=trading_days_consumed,
        diagnostics_summary="; ".join(dict.fromkeys(diagnostics)),
    )


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
