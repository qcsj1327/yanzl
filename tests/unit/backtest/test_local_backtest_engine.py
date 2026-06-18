from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pytest

from futures_mvp.modules.backtest import (
    BacktestRequest,
    BacktestStatus,
    DecisionTranslationResult,
    DecisionTranslationStatus,
    FillModelResult,
    FillModelStatus,
    LocalBacktestEngine,
    NextBarOpenFillModel,
    SimulatedOrder,
    SimulatedOrderIntent,
    SimulatedOrderStatus,
    SimulatedTrade,
)
from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    HistoricalBarsResult,
    HistoricalDataStatus,
)
from futures_mvp.modules.market_data.fixtures import StaticHistoricalDataFixtureProvider
from futures_mvp.modules.market_data.models import (
    ContractRole,
    InstrumentContract,
    InstrumentMetadata,
)
from futures_mvp.modules.market_data.registry import InstrumentRegistry
from futures_mvp.modules.market_data.resolver import InstrumentResolver
from futures_mvp.modules.strategy_runtime import (
    BuyAndHoldStrategy,
    ExitReferenceStrategy,
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
    assert len(result.decision_translation_results) == 3
    assert all(
        translation.status is DecisionTranslationStatus.SKIPPED
        for translation in result.decision_translation_results
    )
    assert result.fill_model_results == ()
    assert result.gap_report == ()
    assert result.simulated_orders == ()
    assert result.simulated_trades == ()
    assert result.research_positions == ()
    assert result.research_pnl_curve == ()
    assert result.research_portfolio is None
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
    assert first.research_positions == second.research_positions == ()
    assert first.research_pnl_curve == second.research_pnl_curve == ()
    assert first.research_portfolio is None
    assert second.research_portfolio is None
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


def test_buy_and_hold_backtest_records_buy_then_hold_with_one_created_order() -> None:
    result = LocalBacktestEngine(strategy=BuyAndHoldStrategy()).run(_request())

    assert result.status is BacktestStatus.COMPLETED
    assert tuple(decision.decision for decision in result.strategy_decisions) == (
        StrategyDecisionType.BUY,
        StrategyDecisionType.HOLD,
        StrategyDecisionType.HOLD,
    )
    assert tuple(decision.side for decision in result.strategy_decisions) == (
        "BUY",
        "NONE",
        "NONE",
    )
    assert result.strategy_decisions[0].reason == "first eligible bar buy"
    assert result.strategy_decisions[1].reason == "already entered hold"
    assert result.strategy_decisions[2].reason == "already entered hold"
    assert tuple(
        translation.status for translation in result.decision_translation_results
    ) == (
        DecisionTranslationStatus.CREATED,
        DecisionTranslationStatus.SKIPPED,
        DecisionTranslationStatus.SKIPPED,
    )
    assert len(result.simulated_orders) == 1
    order = result.simulated_orders[0]
    assert order.status is SimulatedOrderStatus.CREATED
    assert order.side == "BUY"
    assert order.quantity == Decimal("1")
    assert order.symbol == "ao"
    assert order.instrument_id == "ao9999"
    assert order.trade_instrument_id == "ao2609"
    assert order.exchange == "SHFE"
    assert order.resolver_source == "static_fixture"
    assert order.resolver_confidence == "static_fixture"
    assert order.order_type == "MARKET"
    assert len(result.fill_model_results) == 1
    fill_result = result.fill_model_results[0]
    assert fill_result.status is FillModelStatus.NO_FILL
    assert fill_result.simulated_trade is None
    assert fill_result.diagnostics[0] == "no fill model selected"
    assert result.simulated_trades == ()
    assert result.research_positions == ()
    assert result.research_pnl_curve == ()
    assert result.research_portfolio is None
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


def test_exit_reference_backtest_generates_exit_orders_without_trade_or_cash_change() -> None:
    result = LocalBacktestEngine(strategy=ExitReferenceStrategy()).run(_request())

    assert result.status is BacktestStatus.COMPLETED
    assert tuple(decision.decision for decision in result.strategy_decisions) == (
        StrategyDecisionType.BUY,
        StrategyDecisionType.CLOSE,
        StrategyDecisionType.CLOSE,
    )
    assert tuple(decision.side for decision in result.strategy_decisions) == (
        "BUY",
        "CLOSE",
        "CLOSE",
    )
    assert tuple(
        translation.status for translation in result.decision_translation_results
    ) == (
        DecisionTranslationStatus.CREATED,
        DecisionTranslationStatus.CREATED,
        DecisionTranslationStatus.CREATED,
    )
    assert len(result.simulated_orders) == 3
    assert tuple(order.side for order in result.simulated_orders) == (
        "BUY",
        "CLOSE",
        "CLOSE",
    )
    assert tuple(order.intent for order in result.simulated_orders) == (
        SimulatedOrderIntent.ENTRY,
        SimulatedOrderIntent.EXIT,
        SimulatedOrderIntent.EXIT,
    )
    assert all(
        order.status is SimulatedOrderStatus.CREATED
        for order in result.simulated_orders
    )
    assert len(result.fill_model_results) == 3
    assert all(
        fill_result.status is FillModelStatus.NO_FILL
        for fill_result in result.fill_model_results
    )
    assert result.simulated_trades == ()
    assert result.research_positions == ()
    assert result.research_pnl_curve == ()
    assert result.research_portfolio is None
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


def test_buy_and_hold_order_id_is_deterministic() -> None:
    request = _request()

    first = LocalBacktestEngine(strategy=BuyAndHoldStrategy()).run(request)
    second = LocalBacktestEngine(strategy=BuyAndHoldStrategy()).run(request)

    assert first.status is BacktestStatus.COMPLETED
    assert second.status is BacktestStatus.COMPLETED
    assert len(first.simulated_orders) == 1
    assert len(second.simulated_orders) == 1
    assert len(first.fill_model_results) == 1
    assert len(second.fill_model_results) == 1
    assert first.simulated_orders[0].order_id == second.simulated_orders[0].order_id
    assert first.fill_model_results == second.fill_model_results
    assert first.simulated_trades == second.simulated_trades == ()
    assert first.research_positions == second.research_positions == ()
    assert first.research_pnl_curve == second.research_pnl_curve == ()
    assert first.research_portfolio is None
    assert second.research_portfolio is None
    assert first.equity_curve == second.equity_curve


def test_buy_and_hold_with_next_bar_open_fill_marks_research_equity_to_close() -> None:
    resolver = InstrumentResolver()
    data_provider = StaticHistoricalDataFixtureProvider(resolver)
    result = LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        fill_model=NextBarOpenFillModel(),
    ).run(_request(resolver=resolver, data_provider=data_provider))
    bars = data_provider.get_bars("ao", date(2026, 6, 12), BarTimeframe.M1).bars

    assert result.status is BacktestStatus.COMPLETED
    assert len(result.simulated_orders) == 1
    assert len(result.fill_model_results) == 1
    assert result.fill_model_results[0].status is FillModelStatus.FILLED
    assert len(result.simulated_trades) == 1
    order = result.simulated_orders[0]
    trade = result.simulated_trades[0]
    assert trade.order_id == order.order_id
    assert trade.fill_bar_ts == bars[1].bar_ts
    assert trade.fill_bar_ts != order.created_bar_ts
    assert trade.fill_price == bars[1].open
    assert trade.fill_qty == order.quantity
    assert trade.symbol == order.symbol
    assert trade.instrument_id == order.instrument_id
    assert trade.trade_instrument_id == order.trade_instrument_id
    assert trade.exchange == order.exchange
    assert trade.trading_day == order.trading_day
    assert trade.resolver_source == order.resolver_source
    assert trade.resolver_confidence == order.resolver_confidence
    assert trade.resolver_lineage == order.resolver_lineage

    assert len(result.research_positions) == 1
    position = result.research_positions[0]
    assert position.source == "backtest_research_only_position"
    assert position.symbol == trade.symbol
    assert position.instrument_id == trade.instrument_id
    assert position.trade_instrument_id == trade.trade_instrument_id
    assert position.exchange == trade.exchange
    assert position.trading_day == trade.trading_day
    assert position.side == "LONG"
    assert position.quantity == Decimal("1")
    assert position.avg_price == bars[1].open
    assert position.market_value == bars[2].close
    assert position.resolver_lineage == trade.resolver_lineage

    assert tuple(point.equity for point in result.equity_curve) == (
        Decimal("100000"),
        Decimal("100001"),
        Decimal("100002"),
    )
    assert tuple(point.cash for point in result.equity_curve) == (
        Decimal("100000"),
        Decimal("96799"),
        Decimal("96799"),
    )
    assert len(result.research_pnl_curve) == 3
    assert tuple(point.market_value for point in result.research_pnl_curve) == (
        Decimal("0"),
        bars[1].close,
        bars[2].close,
    )
    assert tuple(point.unrealized_pnl for point in result.research_pnl_curve) == (
        Decimal("0"),
        Decimal("1"),
        Decimal("2"),
    )
    assert tuple(point.realized_pnl for point in result.research_pnl_curve) == (
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
    )
    assert tuple(point.equity for point in result.research_pnl_curve) == (
        Decimal("100000"),
        Decimal("100001"),
        Decimal("100002"),
    )
    assert result.research_portfolio is not None
    assert result.research_portfolio.positions == result.research_positions
    assert result.research_portfolio.pnl_points == result.research_pnl_curve
    assert result.research_portfolio.cash == result.research_pnl_curve[-1].cash
    assert result.research_portfolio.total_market_value == sum(
        (position.market_value for position in result.research_positions),
        Decimal("0"),
    )
    assert result.research_portfolio.total_equity == (
        result.research_portfolio.cash
        + result.research_portfolio.total_market_value
    )
    assert result.research_portfolio.total_equity == result.equity_curve[-1].equity
    assert "research/observability only" in result.research_portfolio.diagnostics[-1]


def test_research_portfolio_id_is_deterministic_for_filled_backtest() -> None:
    resolver = InstrumentResolver()
    data_provider = StaticHistoricalDataFixtureProvider(resolver)
    request = _request(resolver=resolver, data_provider=data_provider)

    first = LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        fill_model=NextBarOpenFillModel(),
    ).run(request)
    second = LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        fill_model=NextBarOpenFillModel(),
    ).run(request)

    assert first.research_portfolio is not None
    assert second.research_portfolio is not None
    assert first.research_portfolio == second.research_portfolio
    assert first.research_portfolio.portfolio_id == second.research_portfolio.portfolio_id


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


def test_decision_translator_blocked_returns_backtest_blocked() -> None:
    class BlockingTranslator:
        def translate(self, **kwargs: object) -> DecisionTranslationResult:
            return DecisionTranslationResult(
                status=DecisionTranslationStatus.BLOCKED,
                diagnostics=("blocked for test",),
            )

    result = LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        decision_translator=BlockingTranslator(),
    ).run(_request())

    assert result.status is BacktestStatus.BLOCKED
    assert result.diagnostics.messages == (
        "decision translator blocked",
        "blocked for test",
    )
    assert len(result.strategy_decisions) == 1
    assert len(result.decision_translation_results) == 1
    assert result.simulated_orders == ()
    assert result.simulated_trades == ()
    assert result.equity_curve == ()


def test_decision_translator_error_returns_backtest_error() -> None:
    class ErrorTranslator:
        def translate(self, **kwargs: object) -> DecisionTranslationResult:
            return DecisionTranslationResult(
                status=DecisionTranslationStatus.ERROR,
                diagnostics=("error for test",),
            )

    result = LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        decision_translator=ErrorTranslator(),
    ).run(_request())

    assert result.status is BacktestStatus.ERROR
    assert result.diagnostics.messages == (
        "decision translator failed",
        "error for test",
    )
    assert len(result.strategy_decisions) == 1
    assert len(result.decision_translation_results) == 1
    assert result.simulated_orders == ()
    assert result.simulated_trades == ()
    assert result.equity_curve == ()


def test_fill_model_blocked_returns_backtest_blocked() -> None:
    class BlockingFillModel:
        def fill(self, order: object) -> FillModelResult:
            return FillModelResult(
                status=FillModelStatus.BLOCKED,
                diagnostics=("fill blocked for test",),
            )

    result = LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        fill_model=BlockingFillModel(),
    ).run(_request())

    assert result.status is BacktestStatus.BLOCKED
    assert result.diagnostics.messages == (
        "fill model blocked",
        "fill blocked for test",
    )
    assert len(result.simulated_orders) == 1
    assert len(result.fill_model_results) == 1
    assert result.fill_model_results[0].status is FillModelStatus.BLOCKED
    assert result.simulated_trades == ()
    assert result.equity_curve == ()


def test_fill_model_error_returns_backtest_error() -> None:
    class ErrorFillModel:
        def fill(self, order: object) -> FillModelResult:
            return FillModelResult(
                status=FillModelStatus.ERROR,
                diagnostics=("fill error for test",),
            )

    result = LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        fill_model=ErrorFillModel(),
    ).run(_request())

    assert result.status is BacktestStatus.ERROR
    assert result.diagnostics.messages == (
        "fill model failed",
        "fill error for test",
    )
    assert len(result.simulated_orders) == 1
    assert len(result.fill_model_results) == 1
    assert result.fill_model_results[0].status is FillModelStatus.ERROR
    assert result.simulated_trades == ()
    assert result.equity_curve == ()


def test_fill_model_generated_trade_with_non_filled_status_returns_backtest_error() -> None:
    class RejectedTradingFillModel:
        def fill(self, order: object) -> FillModelResult:
            simulated_order = cast(SimulatedOrder, order)
            trade = SimulatedTrade(
                trade_id="unexpected-trade",
                order_id=simulated_order.order_id,
                fill_price=Decimal("101"),
                fill_qty=Decimal("1"),
                fill_bar_ts=simulated_order.created_bar_ts,
                symbol=simulated_order.symbol,
                instrument_id=simulated_order.instrument_id,
                trade_instrument_id=simulated_order.trade_instrument_id,
                exchange=simulated_order.exchange,
                trading_day=simulated_order.trading_day,
                resolver_source=simulated_order.resolver_source,
                resolver_confidence=simulated_order.resolver_confidence,
                resolver_lineage=simulated_order.resolver_lineage,
            )
            return FillModelResult(
                status=FillModelStatus.REJECTED,
                simulated_trade=trade,
                diagnostics=("unexpected trade for test",),
            )

    result = LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        fill_model=RejectedTradingFillModel(),
    ).run(_request())

    assert result.status is BacktestStatus.ERROR
    assert result.diagnostics.messages == (
        "fill model generated simulated trade with non-FILLED status",
    )
    assert len(result.simulated_orders) == 1
    assert len(result.fill_model_results) == 1
    assert result.simulated_trades == ()
    assert result.equity_curve == ()


@pytest.mark.parametrize(
    "fill_status",
    (
        FillModelStatus.REJECTED,
    ),
)
def test_fill_like_status_without_trade_returns_backtest_error(
    fill_status: FillModelStatus,
) -> None:
    class FillLikeStatusModel:
        def fill(self, order: object) -> FillModelResult:
            return FillModelResult(
                status=fill_status,
                simulated_trade=None,
                diagnostics=("fill-like status for test",),
            )

    result = LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        fill_model=FillLikeStatusModel(),
    ).run(_request())

    assert result.status is BacktestStatus.ERROR
    assert result.diagnostics.messages == (
        "fill model status is not supported before trade generation stage",
        f"fill_status={fill_status.value}",
    )
    assert len(result.simulated_orders) == 1
    assert len(result.fill_model_results) == 1
    assert result.fill_model_results[0].status is fill_status
    assert result.fill_model_results[0].simulated_trade is None
    assert result.simulated_trades == ()
    assert result.equity_curve == ()


def test_fill_model_data_gap_returns_backtest_data_gap() -> None:
    class DataGapFillModel:
        def fill(self, order: object) -> FillModelResult:
            return FillModelResult(
                status=FillModelStatus.DATA_GAP,
                simulated_trade=None,
                diagnostics=("missing next bar for test",),
            )

    result = LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        fill_model=DataGapFillModel(),
    ).run(_request())

    assert result.status is BacktestStatus.DATA_GAP
    assert result.diagnostics.messages == (
        "fill model data gap",
        "missing next bar for test",
    )
    assert result.gap_report == ("missing next bar for test",)
    assert len(result.simulated_orders) == 1
    assert len(result.fill_model_results) == 1
    assert result.simulated_trades == ()
    assert result.equity_curve == ()


def test_fill_model_filled_without_trade_returns_backtest_error() -> None:
    class FilledWithoutTradeModel:
        def fill(self, order: object) -> FillModelResult:
            return FillModelResult(
                status=FillModelStatus.FILLED,
                simulated_trade=None,
                diagnostics=("missing trade for test",),
            )

    result = LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        fill_model=FilledWithoutTradeModel(),
    ).run(_request())

    assert result.status is BacktestStatus.ERROR
    assert result.diagnostics.messages == (
        "fill model returned FILLED without simulated trade",
    )
    assert len(result.simulated_orders) == 1
    assert len(result.fill_model_results) == 1
    assert result.simulated_trades == ()
    assert result.equity_curve == ()


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
    assert "Position" in result.diagnostics.source_of_truth_notice
