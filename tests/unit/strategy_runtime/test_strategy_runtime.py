from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal

import pytest

from futures_mvp.modules.market_data.consumer import build_resolver_consumer_context
from futures_mvp.modules.market_data.contracts import BarTimeframe, HistoricalBar
from futures_mvp.modules.market_data.fixtures import StaticHistoricalDataFixtureProvider
from futures_mvp.modules.market_data.resolver import InstrumentResolver
from futures_mvp.modules.strategy_runtime import (
    BuyAndHoldStrategy,
    NoOpStrategy,
    StrategyContext,
    StrategyDecision,
    StrategyDecisionType,
    StrategyRuntime,
    StrategyRuntimeStatus,
)


def _context() -> StrategyContext:
    resolver = InstrumentResolver()
    context_result = build_resolver_consumer_context(resolver.resolve("ao", "2026-06-12"))
    assert context_result.context is not None
    bars_result = StaticHistoricalDataFixtureProvider(resolver).get_bars(
        "ao",
        "2026-06-12",
        "1m",
    )
    assert len(bars_result.bars) == 3
    current_bar = bars_result.bars[1]
    return StrategyContext(
        strategy_name="noop",
        symbol="ao",
        instrument_id="ao9999",
        trade_instrument_id="ao2609",
        exchange="SHFE",
        trading_day=date(2026, 6, 12),
        timeframe=BarTimeframe.M1,
        current_bar=current_bar,
        historical_bars=bars_result.bars[:2],
        resolver_lineage=context_result.context,
        data_source_summary={"source": "static_historical_fixture"},
        portfolio_snapshot=None,
        config={"strategy": "noop"},
    )


def test_noop_strategy_returns_hold() -> None:
    result = StrategyRuntime(NoOpStrategy()).run(_context())

    assert result.status is StrategyRuntimeStatus.COMPLETED
    assert result.decision is not None
    assert result.decision.decision is StrategyDecisionType.HOLD
    assert result.decision.side == "NONE"
    assert result.decision.expected_price is None


def test_noop_strategy_output_is_deterministic() -> None:
    runtime = StrategyRuntime(NoOpStrategy())
    context = _context()

    first = runtime.run(context)
    second = runtime.run(context)

    assert first == second
    assert first.decision == second.decision


def test_buy_and_hold_first_bar_returns_buy() -> None:
    context = _context()
    first_bar_context = replace(
        context,
        current_bar=context.historical_bars[0],
        historical_bars=context.historical_bars[:1],
    )

    decision = BuyAndHoldStrategy().evaluate(first_bar_context)

    assert decision.decision is StrategyDecisionType.BUY
    assert decision.side == "BUY"
    assert decision.expected_price == first_bar_context.historical_bars[0].close
    assert decision.reason == "first eligible bar buy"


def test_buy_and_hold_second_or_later_bar_returns_hold() -> None:
    context = _context()

    decision = BuyAndHoldStrategy().evaluate(context)

    assert decision.decision is StrategyDecisionType.HOLD
    assert decision.side == "NONE"
    assert decision.expected_price is None
    assert decision.reason == "already entered hold"


def test_buy_and_hold_output_is_deterministic() -> None:
    strategy = BuyAndHoldStrategy()
    context = _context()

    assert strategy.evaluate(context) == strategy.evaluate(context)


def test_buy_and_hold_does_not_mutate_context() -> None:
    context = replace(
        _context(),
        config={"nested": {"x": "original"}},
        data_source_summary={"source": "static_historical_fixture"},
        portfolio_snapshot={"positions": [{"qty": 1}]},
    )

    before_config = context.config
    before_data_source = context.data_source_summary
    before_portfolio = context.portfolio_snapshot
    before_bars = context.historical_bars

    decision = BuyAndHoldStrategy().evaluate(context)

    assert decision.decision is StrategyDecisionType.HOLD
    assert context.config == before_config
    assert context.data_source_summary == before_data_source
    assert context.portfolio_snapshot == before_portfolio
    assert context.historical_bars == before_bars


def test_strategy_cannot_mutate_context_config() -> None:
    class MutatingStrategy:
        def evaluate(self, context: StrategyContext) -> StrategyDecision:
            context.config["x"] = "changed"  # type: ignore[index]
            return NoOpStrategy().evaluate(context)

    result = StrategyRuntime(MutatingStrategy()).run(_context())

    assert result.status is StrategyRuntimeStatus.ERROR
    assert result.decision is None
    assert result.diagnostics[0].startswith("strategy exception: TypeError:")


def test_strategy_cannot_mutate_context_data_source_summary() -> None:
    class MutatingStrategy:
        def evaluate(self, context: StrategyContext) -> StrategyDecision:
            context.data_source_summary["x"] = "changed"  # type: ignore[index]
            return NoOpStrategy().evaluate(context)

    result = StrategyRuntime(MutatingStrategy()).run(_context())

    assert result.status is StrategyRuntimeStatus.ERROR
    assert result.decision is None
    assert result.diagnostics[0].startswith("strategy exception: TypeError:")


def test_strategy_cannot_mutate_nested_context_mapping() -> None:
    class MutatingStrategy:
        def evaluate(self, context: StrategyContext) -> StrategyDecision:
            nested = context.config["nested"]
            nested["x"] = "changed"
            return NoOpStrategy().evaluate(context)

    context = replace(_context(), config={"nested": {"x": "original"}})
    result = StrategyRuntime(MutatingStrategy()).run(context)

    assert result.status is StrategyRuntimeStatus.ERROR
    assert result.decision is None
    assert result.diagnostics[0].startswith("strategy exception: TypeError:")


def test_original_input_dict_mutation_does_not_change_context() -> None:
    config = {"nested": {"x": "original"}, "items": ["a"]}
    data_source_summary = {"source": "static_historical_fixture"}
    portfolio_snapshot = {"positions": [{"qty": 1}]}

    context = replace(
        _context(),
        config=config,
        data_source_summary=data_source_summary,
        portfolio_snapshot=portfolio_snapshot,
    )
    config["nested"]["x"] = "changed"
    config["items"].append("b")
    data_source_summary["source"] = "changed"
    portfolio_snapshot["positions"].append({"qty": 2})

    assert context.config["nested"]["x"] == "original"
    assert context.config["items"] == ("a",)
    assert context.data_source_summary["source"] == "static_historical_fixture"
    assert context.portfolio_snapshot is not None
    positions = context.portfolio_snapshot["positions"]
    assert positions[0]["qty"] == 1
    assert len(positions) == 1


def test_context_nested_mappings_are_mapping_proxies() -> None:
    context = replace(_context(), config={"nested": {"x": "original"}})
    nested = context.config["nested"]

    with pytest.raises(TypeError):
        context.config["x"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        nested["x"] = "changed"  # type: ignore[index]


def test_missing_resolver_lineage_blocks_strategy_call() -> None:
    result = StrategyRuntime(NoOpStrategy()).run(
        replace(_context(), resolver_lineage=None)
    )

    assert result.status is StrategyRuntimeStatus.BLOCKED
    assert result.decision is None
    assert result.diagnostics == ("resolver lineage is required",)


def test_missing_current_bar_blocks_strategy_call() -> None:
    result = StrategyRuntime(NoOpStrategy()).run(replace(_context(), current_bar=None))

    assert result.status is StrategyRuntimeStatus.BLOCKED
    assert result.decision is None
    assert result.diagnostics == ("current bar is required",)


def test_future_bar_in_historical_bars_blocks_strategy_call() -> None:
    context = _context()
    future_bar = HistoricalBar(
        symbol="ao",
        instrument_id="ao9999",
        trade_instrument_id="ao2609",
        exchange="SHFE",
        trading_day=date(2026, 6, 12),
        session_id="day",
        timeframe=BarTimeframe.M1,
        bar_ts=datetime.combine(date(2026, 6, 12), time(9, 2)),
        open=Decimal("3202"),
        high=Decimal("3204"),
        low=Decimal("3201"),
        close=Decimal("3203"),
        volume=Decimal("12"),
        turnover=Decimal("38436"),
        open_interest=Decimal("102"),
    )

    result = StrategyRuntime(NoOpStrategy()).run(
        replace(context, historical_bars=(*context.historical_bars, future_bar))
    )

    assert result.status is StrategyRuntimeStatus.BLOCKED
    assert result.decision is None
    assert result.diagnostics == (
        "historical bars must not include bars after current_bar",
    )


def test_strategy_exception_returns_error() -> None:
    class FailingStrategy:
        def evaluate(self, context: StrategyContext) -> StrategyDecision:
            raise RuntimeError("boom")

    result = StrategyRuntime(FailingStrategy()).run(_context())

    assert result.status is StrategyRuntimeStatus.ERROR
    assert result.decision is None
    assert result.diagnostics == ("strategy exception: RuntimeError: boom",)
