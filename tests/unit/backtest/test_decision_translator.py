from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from futures_mvp.modules.backtest import (
    DecisionTranslationStatus,
    DecisionTranslator,
    SimulatedOrderIntent,
    SimulatedOrderStatus,
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
from futures_mvp.modules.market_data.fixtures import StaticHistoricalDataFixtureProvider
from futures_mvp.modules.market_data.resolver import InstrumentResolver
from futures_mvp.modules.strategy_runtime import StrategyDecision, StrategyDecisionType

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _resolver_context_and_bar() -> tuple[ResolverConsumerContext, HistoricalBar]:
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
    assert bars_result.bars
    return context_result.context, bars_result.bars[0]


def _decision(
    decision_type: StrategyDecisionType,
    *,
    side: str,
    expected_price: Decimal | None = Decimal("101"),
) -> StrategyDecision:
    return StrategyDecision(
        decision=decision_type,
        side=side,
        confidence=Decimal("1"),
        reason=f"{decision_type.value} for translator test",
        expected_price=expected_price,
    )


def test_buy_decision_creates_research_only_simulated_order() -> None:
    resolver_lineage, current_bar = _resolver_context_and_bar()
    result = DecisionTranslator().translate(
        strategy_name="buy-and-hold",
        decision=_decision(StrategyDecisionType.BUY, side="BUY"),
        resolver_lineage=resolver_lineage,
        current_bar=current_bar,
    )

    assert result.status is DecisionTranslationStatus.CREATED
    assert result.simulated_order is not None
    assert result.simulated_trades == ()
    order = result.simulated_order
    assert order.status is SimulatedOrderStatus.CREATED
    assert order.strategy_name == "buy-and-hold"
    assert order.symbol == "ao"
    assert order.instrument_id == "ao9999"
    assert order.trade_instrument_id == "ao2609"
    assert order.exchange == "SHFE"
    assert order.trading_day == date(2026, 6, 12)
    assert order.side == "BUY"
    assert order.intent is SimulatedOrderIntent.ENTRY
    assert order.quantity == Decimal("1")
    assert order.expected_price == Decimal("101")
    assert order.order_type == "MARKET"
    assert order.created_bar_ts == current_bar.bar_ts
    assert order.resolver_source == "static_fixture"
    assert order.resolver_confidence == "static_fixture"
    assert order.resolver_lineage == resolver_lineage
    assert "research-only simulated order" in order.diagnostics


def test_buy_decision_without_expected_price_uses_current_bar_close() -> None:
    resolver_lineage, current_bar = _resolver_context_and_bar()
    result = DecisionTranslator().translate(
        strategy_name="buy-and-hold",
        decision=_decision(
            StrategyDecisionType.BUY,
            side="BUY",
            expected_price=None,
        ),
        resolver_lineage=resolver_lineage,
        current_bar=current_bar,
    )

    assert result.status is DecisionTranslationStatus.CREATED
    assert result.simulated_order is not None
    assert result.simulated_order.expected_price == current_bar.close


def test_buy_decision_with_non_positive_expected_price_is_blocked() -> None:
    resolver_lineage, current_bar = _resolver_context_and_bar()
    result = DecisionTranslator().translate(
        strategy_name="buy-and-hold",
        decision=_decision(
            StrategyDecisionType.BUY,
            side="BUY",
            expected_price=Decimal("0"),
        ),
        resolver_lineage=resolver_lineage,
        current_bar=current_bar,
    )

    assert result.status is DecisionTranslationStatus.BLOCKED
    assert result.simulated_order is None
    assert result.simulated_trades == ()
    assert result.diagnostics == ("BUY decision requires a positive expected price",)


def test_hold_decision_is_skipped_without_order_or_trade() -> None:
    resolver_lineage, current_bar = _resolver_context_and_bar()
    result = DecisionTranslator().translate(
        strategy_name="noop",
        decision=_decision(
            StrategyDecisionType.HOLD,
            side="NONE",
            expected_price=None,
        ),
        resolver_lineage=resolver_lineage,
        current_bar=current_bar,
    )

    assert result.status is DecisionTranslationStatus.SKIPPED
    assert result.simulated_order is None
    assert result.simulated_trades == ()


def test_close_decision_creates_research_only_exit_simulated_order() -> None:
    resolver_lineage, current_bar = _resolver_context_and_bar()
    result = DecisionTranslator().translate(
        strategy_name="exit-reference",
        decision=_decision(StrategyDecisionType.CLOSE, side="CLOSE"),
        resolver_lineage=resolver_lineage,
        current_bar=current_bar,
    )

    assert result.status is DecisionTranslationStatus.CREATED
    assert result.simulated_order is not None
    assert result.simulated_trades == ()
    order = result.simulated_order
    assert order.status is SimulatedOrderStatus.CREATED
    assert order.side == "CLOSE"
    assert order.intent is SimulatedOrderIntent.EXIT
    assert order.quantity == Decimal("1")
    assert order.expected_price == Decimal("101")
    assert "intent=EXIT" in order.diagnostics
    assert result.diagnostics == (
        "CLOSE decision translated to CREATED EXIT simulated order",
    )


def test_sell_is_rejected_by_long_only_research_skeleton() -> None:
    resolver_lineage, current_bar = _resolver_context_and_bar()
    result = DecisionTranslator().translate(
        strategy_name="reference",
        decision=_decision(StrategyDecisionType.SELL, side="SELL"),
        resolver_lineage=resolver_lineage,
        current_bar=current_bar,
    )

    assert result.status is DecisionTranslationStatus.REJECTED
    assert result.simulated_order is None
    assert result.simulated_trades == ()
    assert result.diagnostics == (
        "SELL decision translation is not supported by the long-only research skeleton",
    )


def test_missing_resolver_lineage_blocks_translation() -> None:
    _, current_bar = _resolver_context_and_bar()
    result = DecisionTranslator().translate(
        strategy_name="buy-and-hold",
        decision=_decision(StrategyDecisionType.BUY, side="BUY"),
        resolver_lineage=None,
        current_bar=current_bar,
    )

    assert result.status is DecisionTranslationStatus.BLOCKED
    assert result.simulated_order is None
    assert result.simulated_trades == ()
    assert result.diagnostics == ("resolver lineage is required",)


def test_order_id_is_deterministic_for_same_decision_bar_and_identity() -> None:
    resolver_lineage, current_bar = _resolver_context_and_bar()
    translator = DecisionTranslator()
    decision = _decision(StrategyDecisionType.BUY, side="BUY")

    first = translator.translate(
        strategy_name="buy-and-hold",
        decision=decision,
        resolver_lineage=resolver_lineage,
        current_bar=current_bar,
    )
    second = translator.translate(
        strategy_name="buy-and-hold",
        decision=decision,
        resolver_lineage=resolver_lineage,
        current_bar=current_bar,
    )

    assert first.status is DecisionTranslationStatus.CREATED
    assert second.status is DecisionTranslationStatus.CREATED
    assert first.simulated_order is not None
    assert second.simulated_order is not None
    assert first.simulated_order.order_id == second.simulated_order.order_id


def test_decision_translator_does_not_import_db_live_schema_or_targets() -> None:
    checked_files = (
        _PROJECT_ROOT / "src/futures_mvp/modules/backtest/models.py",
        _PROJECT_ROOT / "src/futures_mvp/modules/backtest/translator.py",
    )
    forbidden_tokens = (
        "import sqlalchemy",
        "from sqlalchemy",
        "import alembic",
        "from alembic",
        "import repository",
        "from futures_mvp.modules.repository",
        "unit_of_work",
        "import broker",
        "from futures_mvp.modules.broker",
        "import ctp",
        "import simnow",
        "import network",
        "ExecutionTarget.PAPER",
        "ExecutionTarget.SIM",
        "ExecutionTarget.LIVE",
    )

    for path in checked_files:
        content = path.read_text()
        assert not any(token in content for token in forbidden_tokens)
