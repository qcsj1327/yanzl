from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from futures_mvp.modules.backtest import (
    DecisionTranslator,
    FillModelStatus,
    NextBarOpenFillModel,
    SimulatedOrder,
    SimulatedOrderIntent,
    SimulatedOrderStatus,
)
from futures_mvp.modules.market_data.consumer import build_resolver_consumer_context
from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    HistoricalBar,
    HistoricalDataStatus,
)
from futures_mvp.modules.market_data.fixtures import StaticHistoricalDataFixtureProvider
from futures_mvp.modules.market_data.resolver import InstrumentResolver
from futures_mvp.modules.strategy_runtime import StrategyDecision, StrategyDecisionType


def _created_order_and_bars(
    decision_type: StrategyDecisionType = StrategyDecisionType.BUY,
    *,
    side: str = "BUY",
) -> tuple[SimulatedOrder, tuple[HistoricalBar, ...]]:
    resolver = InstrumentResolver()
    trading_day = date(2026, 6, 12)
    resolution = resolver.resolve("ao", trading_day)
    context_result = build_resolver_consumer_context(resolution)
    assert context_result.context is not None
    bars_result = StaticHistoricalDataFixtureProvider(resolver).get_bars(
        "ao",
        trading_day,
        BarTimeframe.M1,
    )
    assert bars_result.status is HistoricalDataStatus.OK
    assert len(bars_result.bars) >= 2
    translation = DecisionTranslator().translate(
        strategy_name="buy-and-hold",
        decision=StrategyDecision(
            decision=decision_type,
            side=side,
            confidence=Decimal("1"),
            reason=f"{decision_type.value} next-bar-open fill test",
            expected_price=Decimal("101"),
        ),
        resolver_lineage=context_result.context,
        current_bar=bars_result.bars[0],
    )
    assert translation.simulated_order is not None
    return translation.simulated_order, bars_result.bars


def test_created_buy_order_fills_at_next_bar_open() -> None:
    order, bars = _created_order_and_bars()

    result = NextBarOpenFillModel().fill(order, bars)

    assert result.status is FillModelStatus.FILLED
    assert result.simulated_trade is not None
    trade = result.simulated_trade
    next_bar = bars[1]
    assert trade.order_id == order.order_id
    assert trade.fill_price == next_bar.open
    assert trade.fill_qty == order.quantity
    assert trade.fill_bar_ts == next_bar.bar_ts
    assert trade.symbol == order.symbol
    assert trade.instrument_id == order.instrument_id
    assert trade.trade_instrument_id == order.trade_instrument_id
    assert trade.exchange == order.exchange
    assert trade.trading_day == order.trading_day
    assert trade.resolver_source == order.resolver_source
    assert trade.resolver_confidence == order.resolver_confidence
    assert trade.resolver_lineage == order.resolver_lineage
    assert trade.intent is SimulatedOrderIntent.ENTRY
    assert "research-only ENTRY next-bar-open simulated trade" in trade.diagnostics
    assert result.diagnostics == (
        "next-bar-open fill generated research-only ENTRY simulated trade",
    )


def test_created_exit_order_fills_at_next_bar_open() -> None:
    order, bars = _created_order_and_bars(
        StrategyDecisionType.CLOSE,
        side="CLOSE",
    )

    result = NextBarOpenFillModel().fill(order, bars)

    assert result.status is FillModelStatus.FILLED
    assert result.simulated_trade is not None
    trade = result.simulated_trade
    next_bar = bars[1]
    assert order.intent is SimulatedOrderIntent.EXIT
    assert order.side == "CLOSE"
    assert trade.order_id == order.order_id
    assert trade.fill_price == next_bar.open
    assert trade.fill_qty == order.quantity
    assert trade.fill_bar_ts == next_bar.bar_ts
    assert trade.symbol == order.symbol
    assert trade.instrument_id == order.instrument_id
    assert trade.trade_instrument_id == order.trade_instrument_id
    assert trade.exchange == order.exchange
    assert trade.trading_day == order.trading_day
    assert trade.resolver_source == order.resolver_source
    assert trade.resolver_confidence == order.resolver_confidence
    assert trade.resolver_lineage == order.resolver_lineage
    assert trade.intent is SimulatedOrderIntent.EXIT
    assert "research-only EXIT next-bar-open simulated trade" in trade.diagnostics
    assert result.diagnostics == (
        "next-bar-open fill generated research-only EXIT simulated trade",
    )


def test_same_bar_is_not_eligible_for_fill() -> None:
    order, bars = _created_order_and_bars()

    result = NextBarOpenFillModel().fill(order, (bars[0],))

    assert result.status is FillModelStatus.DATA_GAP
    assert result.simulated_trade is None
    assert result.diagnostics == ("next available bar not found",)


def test_exit_same_bar_is_not_eligible_for_fill() -> None:
    order, bars = _created_order_and_bars(
        StrategyDecisionType.CLOSE,
        side="CLOSE",
    )

    result = NextBarOpenFillModel().fill(order, (bars[0],))

    assert result.status is FillModelStatus.DATA_GAP
    assert result.simulated_trade is None
    assert result.diagnostics == ("next available bar not found",)


def test_no_next_bar_returns_data_gap_without_trade() -> None:
    order, _ = _created_order_and_bars()

    result = NextBarOpenFillModel().fill(order, ())

    assert result.status is FillModelStatus.DATA_GAP
    assert result.simulated_trade is None


def test_exit_no_next_bar_returns_data_gap_without_trade() -> None:
    order, _ = _created_order_and_bars(
        StrategyDecisionType.CLOSE,
        side="CLOSE",
    )

    result = NextBarOpenFillModel().fill(order, ())

    assert result.status is FillModelStatus.DATA_GAP
    assert result.simulated_trade is None


def test_next_bar_open_must_be_positive() -> None:
    order, bars = _created_order_and_bars()
    invalid_next_bar = replace(bars[1], open=Decimal("0"))

    result = NextBarOpenFillModel().fill(order, (bars[0], invalid_next_bar))

    assert result.status is FillModelStatus.DATA_GAP
    assert result.simulated_trade is None
    assert result.diagnostics == ("next bar open must be greater than 0",)


def test_identity_mismatch_bars_do_not_fill_across_identity() -> None:
    order, bars = _created_order_and_bars()
    mismatched_bar = replace(bars[1], trade_instrument_id="ao9998")

    result = NextBarOpenFillModel().fill(order, (bars[0], mismatched_bar))

    assert result.status is FillModelStatus.DATA_GAP
    assert result.simulated_trade is None


def test_exit_identity_mismatch_bars_do_not_fill_across_identity() -> None:
    order, bars = _created_order_and_bars(
        StrategyDecisionType.CLOSE,
        side="CLOSE",
    )
    mismatched_bar = replace(bars[1], trade_instrument_id="ao9998")

    result = NextBarOpenFillModel().fill(order, (bars[0], mismatched_bar))

    assert result.status is FillModelStatus.DATA_GAP
    assert result.simulated_trade is None


def test_non_created_order_is_blocked() -> None:
    order, bars = _created_order_and_bars()
    cancelled_order = replace(order, status=SimulatedOrderStatus.CANCELLED)

    result = NextBarOpenFillModel().fill(cancelled_order, bars)

    assert result.status is FillModelStatus.BLOCKED
    assert result.simulated_trade is None
    assert result.diagnostics == ("order status must be CREATED",)


def test_non_positive_quantity_is_blocked() -> None:
    order, bars = _created_order_and_bars()
    zero_quantity_order = replace(order, quantity=Decimal("0"))

    result = NextBarOpenFillModel().fill(zero_quantity_order, bars)

    assert result.status is FillModelStatus.BLOCKED
    assert result.simulated_trade is None
    assert result.diagnostics == ("order quantity must be greater than 0",)


def test_unsupported_side_is_rejected() -> None:
    order, bars = _created_order_and_bars()
    sell_order = replace(order, side="SELL")

    result = NextBarOpenFillModel().fill(sell_order, bars)

    assert result.status is FillModelStatus.REJECTED
    assert result.simulated_trade is None
    assert result.diagnostics == ("order side SELL does not match ENTRY intent",)


def test_close_side_with_entry_intent_is_rejected() -> None:
    order, bars = _created_order_and_bars()
    close_order = replace(order, side="CLOSE")

    result = NextBarOpenFillModel().fill(close_order, bars)

    assert result.status is FillModelStatus.REJECTED
    assert result.simulated_trade is None
    assert result.diagnostics == ("order side CLOSE does not match ENTRY intent",)


def test_trade_id_is_deterministic_for_same_order_and_next_bar() -> None:
    order, bars = _created_order_and_bars()
    model = NextBarOpenFillModel()

    first = model.fill(order, bars)
    second = model.fill(order, bars)

    assert first.status is FillModelStatus.FILLED
    assert second.status is FillModelStatus.FILLED
    assert first.simulated_trade is not None
    assert second.simulated_trade is not None
    assert first.simulated_trade.trade_id == second.simulated_trade.trade_id
