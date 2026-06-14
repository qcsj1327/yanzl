from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from futures_mvp.modules.backtest.models import (
    BacktestDataSummary,
    BacktestDiagnostics,
    BacktestEquityPoint,
    BacktestRequest,
    BacktestResult,
    BacktestStatus,
)
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


class LocalBacktestEngine:
    def __init__(
        self,
        strategy_runtime: Any | None = None,
        strategy: StrategyEvaluator | None = None,
    ) -> None:
        self._strategy = strategy or NoOpStrategy()
        self._strategy_runtime = strategy_runtime or StrategyRuntime(self._strategy)

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
                            simulated_orders=(),
                            simulated_trades=(),
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
                            simulated_orders=(),
                            simulated_trades=(),
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
                            simulated_orders=(),
                            simulated_trades=(),
                        )
                    strategy_decisions.append(runtime_result.decision)
            return BacktestResult(
                status=BacktestStatus.COMPLETED,
                diagnostics=BacktestDiagnostics(
                    messages=(
                        "deterministic local no-op backtest completed",
                        "no OMS/Trade/Position/Accounting mutation",
                        "no DB write, broker, CTP, SimNow, live feed, or execution target",
                    ),
                    resolver_statuses=tuple(resolver_statuses),
                    data_statuses=tuple(data_statuses),
                ),
                resolver_lineage=tuple(contexts),
                data_source_summary=data_summary,
                bars_consumed_count=len(all_bars),
                equity_curve=_flat_equity_curve(all_bars, request.initial_cash),
                strategy_runtime_results=tuple(strategy_runtime_results),
                strategy_decisions=tuple(strategy_decisions),
                simulated_orders=(),
                simulated_trades=(),
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
        simulated_orders=(),
        simulated_trades=(),
    )


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, tuple):
        return tuple(str(item) for item in value)
    return (str(value),)
