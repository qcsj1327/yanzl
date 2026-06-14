from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from futures_mvp.modules.backtest import (
    DecisionTranslator,
    FillModelStatus,
    NoFillModel,
    SimulatedOrder,
)
from futures_mvp.modules.market_data.consumer import build_resolver_consumer_context
from futures_mvp.modules.market_data.contracts import BarTimeframe, HistoricalDataStatus
from futures_mvp.modules.market_data.fixtures import StaticHistoricalDataFixtureProvider
from futures_mvp.modules.market_data.resolver import InstrumentResolver
from futures_mvp.modules.strategy_runtime import StrategyDecision, StrategyDecisionType

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _created_order() -> SimulatedOrder:
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
    translation = DecisionTranslator().translate(
        strategy_name="buy-and-hold",
        decision=StrategyDecision(
            decision=StrategyDecisionType.BUY,
            side="BUY",
            confidence=Decimal("1"),
            reason="first eligible bar buy",
            expected_price=Decimal("101"),
        ),
        resolver_lineage=context_result.context,
        current_bar=bars_result.bars[0],
    )
    assert translation.simulated_order is not None
    return translation.simulated_order


def test_created_order_returns_no_fill_without_simulated_trade() -> None:
    order = _created_order()
    result = NoFillModel().fill(order)

    assert result.status is FillModelStatus.NO_FILL
    assert result.simulated_trade is None
    assert result.diagnostics[0] == "no fill model selected"
    assert "research-only no-fill model" in result.diagnostics


def test_no_fill_model_result_is_deterministic() -> None:
    order = _created_order()
    model = NoFillModel()

    first = model.fill(order)
    second = model.fill(order)

    assert first == second


def test_no_fill_model_does_not_mutate_order() -> None:
    order = _created_order()
    before = order

    result = NoFillModel().fill(order)

    assert result.status is FillModelStatus.NO_FILL
    assert order == before
    assert order.status is before.status
    assert order.order_id == before.order_id


def test_no_fill_model_does_not_import_db_live_schema_or_targets() -> None:
    checked_files = (
        _PROJECT_ROOT / "src/futures_mvp/modules/backtest/fill_model.py",
        _PROJECT_ROOT / "src/futures_mvp/modules/backtest/models.py",
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
