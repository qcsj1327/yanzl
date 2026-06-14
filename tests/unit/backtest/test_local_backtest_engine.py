from __future__ import annotations

from datetime import date
from decimal import Decimal

from futures_mvp.modules.backtest import (
    BacktestRequest,
    BacktestStatus,
    LocalBacktestEngine,
)
from futures_mvp.modules.market_data.contracts import HistoricalBarsResult, HistoricalDataStatus
from futures_mvp.modules.market_data.fixtures import StaticHistoricalDataFixtureProvider
from futures_mvp.modules.market_data.models import (
    ContractRole,
    InstrumentContract,
    InstrumentMetadata,
)
from futures_mvp.modules.market_data.registry import InstrumentRegistry
from futures_mvp.modules.market_data.resolver import InstrumentResolver
from futures_mvp.modules.strategy_runtime import (
    StrategyContext,
    StrategyDecision,
    StrategyDecisionType,
    StrategyRuntimeResult,
    StrategyRuntimeStatus,
)


def _request(
    *,
    symbol: str = "ao",
    timeframe: str = "1m",
    resolver: object | None = None,
    data_provider: object | None = None,
) -> BacktestRequest:
    actual_resolver = resolver if resolver is not None else InstrumentResolver()
    actual_provider = (
        data_provider
        if data_provider is not None
        else StaticHistoricalDataFixtureProvider(actual_resolver)  # type: ignore[arg-type]
    )
    return BacktestRequest(
        strategy_name="noop",
        symbol=symbol,
        start_trading_day=date(2026, 6, 12),
        end_trading_day=date(2026, 6, 12),
        timeframe=timeframe,
        initial_cash=Decimal("100000"),
        resolver=actual_resolver,
        data_provider=actual_provider,
    )


def test_valid_request_returns_completed_with_flat_noop_outputs() -> None:
    result = LocalBacktestEngine().run(_request())

    assert result.status is BacktestStatus.COMPLETED
    assert result.bars_consumed_count == 3
    assert len(result.strategy_runtime_results) == 3
    assert len(result.strategy_decisions) == 3
    assert all(
        decision.decision is StrategyDecisionType.HOLD
        for decision in result.strategy_decisions
    )
    assert result.data_source_summary is not None
    assert result.data_source_summary.source == "static_historical_fixture"
    assert result.data_source_summary.bars_consumed_count == 3
    assert result.gap_report == ()
    assert result.simulated_orders == ()
    assert result.simulated_trades == ()
    assert tuple(point.equity for point in result.equity_curve) == (
        Decimal("100000"),
        Decimal("100000"),
        Decimal("100000"),
    )
    assert tuple(point.cash for point in result.equity_curve) == (
        Decimal("100000"),
        Decimal("100000"),
        Decimal("100000"),
    )


def test_equity_curve_is_deterministic() -> None:
    request = _request()

    first = LocalBacktestEngine().run(request)
    second = LocalBacktestEngine().run(request)

    assert first.equity_curve == second.equity_curve
    assert first.bars_consumed_count == second.bars_consumed_count
    assert first.simulated_orders == second.simulated_orders == ()
    assert first.simulated_trades == second.simulated_trades == ()
    assert first.strategy_decisions == second.strategy_decisions


def test_valid_backtest_calls_strategy_once_per_bar_without_lookahead() -> None:
    class RecordingStrategy:
        def __init__(self) -> None:
            self.contexts: list[StrategyContext] = []

        def evaluate(self, context: StrategyContext) -> StrategyDecision:
            self.contexts.append(context)
            return StrategyDecision(
                decision=StrategyDecisionType.HOLD,
                side="NONE",
                confidence=Decimal("1"),
                reason="recorded",
            )

    strategy = RecordingStrategy()
    result = LocalBacktestEngine(strategy=strategy).run(_request())

    assert result.status is BacktestStatus.COMPLETED
    assert len(strategy.contexts) == 3
    assert len(result.strategy_runtime_results) == 3
    assert len(result.strategy_decisions) == 3
    for index, context in enumerate(strategy.contexts):
        assert context.current_bar is not None
        assert len(context.historical_bars) == index + 1
        assert context.historical_bars[-1] == context.current_bar
        assert all(bar.bar_ts <= context.current_bar.bar_ts for bar in context.historical_bars)
        assert context.resolver_lineage is not None
        assert context.data_source_summary["source"] == "static_historical_fixture"
        assert context.portfolio_snapshot is not None
        assert context.config["strategy"] == "noop"


def test_strategy_exception_returns_backtest_error() -> None:
    class FailingStrategy:
        def evaluate(self, context: StrategyContext) -> StrategyDecision:
            raise RuntimeError("boom")

    result = LocalBacktestEngine(strategy=FailingStrategy()).run(_request())

    assert result.status is BacktestStatus.ERROR
    assert result.diagnostics.messages[0] == "strategy runtime failed"
    assert result.diagnostics.messages[1] == "strategy exception: RuntimeError: boom"
    assert result.strategy_decisions == ()
    assert len(result.strategy_runtime_results) == 1
    assert result.simulated_orders == ()
    assert result.simulated_trades == ()


def test_strategy_runtime_blocked_returns_backtest_blocked() -> None:
    class BlockingRuntime:
        def run(self, context: StrategyContext) -> StrategyRuntimeResult:
            return StrategyRuntimeResult(
                status=StrategyRuntimeStatus.BLOCKED,
                diagnostics=("blocked for test",),
            )

    result = LocalBacktestEngine(strategy_runtime=BlockingRuntime()).run(_request())

    assert result.status is BacktestStatus.BLOCKED
    assert result.diagnostics.messages == (
        "strategy runtime blocked",
        "blocked for test",
    )
    assert len(result.strategy_runtime_results) == 1
    assert result.strategy_decisions == ()
    assert result.simulated_orders == ()
    assert result.simulated_trades == ()


def test_unknown_symbol_blocks_before_market_data_consumption() -> None:
    result = LocalBacktestEngine().run(_request(symbol="zz"))

    assert result.status is BacktestStatus.BLOCKED
    assert result.bars_consumed_count == 0
    assert result.equity_curve == ()
    assert result.resolver_lineage == ()
    assert any("resolver_status=NOT_FOUND" == message for message in result.diagnostics.messages)


def test_metadata_invalid_blocks_before_market_data_consumption() -> None:
    bad_metadata = InstrumentMetadata(
        product_name="",
        tick_size=Decimal("0"),
        contract_multiplier=Decimal("20"),
        min_order_qty=Decimal("1"),
        price_limit_ref="static_fixture_price_limit_placeholder",
        trading_session_ref="static_fixture_day_night_session_placeholder",
    )
    contracts = (
        InstrumentContract(
            symbol="ao",
            instrument_id="ao9999",
            exchange="SHFE",
            role=ContractRole.CONTINUOUS_MAIN,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31),
            metadata=bad_metadata,
        ),
        InstrumentContract(
            symbol="ao",
            instrument_id="ao2609",
            exchange="SHFE",
            role=ContractRole.TRADE_CONTRACT,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31),
            metadata=bad_metadata,
        ),
    )
    resolver = InstrumentResolver(InstrumentRegistry.from_contracts(contracts))

    result = LocalBacktestEngine().run(_request(resolver=resolver))

    assert result.status is BacktestStatus.BLOCKED
    assert any(
        "resolver_status=METADATA_INVALID" == message
        for message in result.diagnostics.messages
    )
    assert result.resolver_lineage == ()
    assert result.simulated_orders == ()
    assert result.simulated_trades == ()


def test_unsupported_timeframe_returns_invalid_input() -> None:
    result = LocalBacktestEngine().run(_request(timeframe="30m"))

    assert result.status is BacktestStatus.INVALID_INPUT
    assert result.diagnostics.messages == ("unsupported timeframe",)
    assert result.bars_consumed_count == 0


def test_missing_bars_returns_data_gap() -> None:
    class EmptyBarsProvider:
        def get_bars(
            self,
            symbol: str,
            trading_day: date,
            timeframe: object,
        ) -> HistoricalBarsResult:
            return HistoricalBarsResult(
                status=HistoricalDataStatus.OK,
                bars=(),
                diagnostics=("static_historical_fixture", "empty fixture"),
            )

    result = LocalBacktestEngine().run(_request(data_provider=EmptyBarsProvider()))

    assert result.status is BacktestStatus.DATA_GAP
    assert result.gap_report == ("2026-06-12: bars empty",)
    assert result.bars_consumed_count == 0
    assert result.equity_curve == ()
    assert result.simulated_orders == ()
    assert result.simulated_trades == ()


def test_result_carries_resolver_lineage() -> None:
    result = LocalBacktestEngine().run(_request())

    assert result.status is BacktestStatus.COMPLETED
    assert len(result.resolver_lineage) == 1
    context = result.resolver_lineage[0]
    assert context.identity.symbol == "ao"
    assert context.identity.instrument_id == "ao9999"
    assert context.identity.trade_instrument_id == "ao2609"
    assert context.identity.exchange == "SHFE"
    assert context.lineage.resolver_source == "static_fixture"
    assert context.lineage.resolver_confidence == "static_fixture"
    assert "static fixture only, not live market source" in (
        context.lineage.resolver_diagnostics_summary
    )


def test_result_is_research_only_not_business_truth() -> None:
    result = LocalBacktestEngine().run(_request())

    assert "research/observability only" in result.diagnostics.source_of_truth_notice
    assert "OMS" in result.diagnostics.source_of_truth_notice
    assert "Accounting" in result.diagnostics.source_of_truth_notice
