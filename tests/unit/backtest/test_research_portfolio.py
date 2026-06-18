from __future__ import annotations

import inspect
from datetime import UTC, date, datetime
from decimal import Decimal

from futures_mvp.modules import backtest as backtest_package
from futures_mvp.modules.backtest import PortfolioAggregator, ResearchPosition
from futures_mvp.modules.backtest import engine as engine_module
from futures_mvp.modules.backtest import portfolio as portfolio_module
from futures_mvp.modules.backtest.models import ResearchPnLPoint
from futures_mvp.modules.market_data.consumer import build_resolver_consumer_context
from futures_mvp.modules.market_data.resolver import InstrumentResolver


def _resolver_context(symbol: str = "ao"):
    trading_day = date(2026, 6, 12)
    result = build_resolver_consumer_context(
        InstrumentResolver().resolve(symbol, trading_day)
    )
    assert result.context is not None
    return result.context


def _position(
    *,
    symbol: str = "ao",
    instrument_id: str = "ao9999",
    trade_instrument_id: str = "ao2609",
    quantity: Decimal = Decimal("1"),
    avg_price: Decimal = Decimal("3200"),
    market_value: Decimal = Decimal("3205"),
) -> ResearchPosition:
    context = _resolver_context(symbol)
    return ResearchPosition(
        symbol=symbol,
        instrument_id=instrument_id,
        trade_instrument_id=trade_instrument_id,
        exchange=context.identity.exchange,
        trading_day=context.identity.trading_day,
        side="LONG",
        quantity=quantity,
        avg_price=avg_price,
        resolver_lineage=context,
        market_value=market_value,
    )


def _pnl_point(
    *,
    cash: Decimal = Decimal("96800"),
    position_quantity: Decimal = Decimal("1"),
    avg_price: Decimal = Decimal("3200"),
    mark_price: Decimal = Decimal("3205"),
    market_value: Decimal = Decimal("3205"),
) -> ResearchPnLPoint:
    return ResearchPnLPoint(
        trading_day=date(2026, 6, 12),
        ts=datetime(2026, 6, 12, 9, 1, tzinfo=UTC),
        cash=cash,
        position_quantity=position_quantity,
        avg_price=avg_price,
        mark_price=mark_price,
        market_value=market_value,
        realized_pnl=Decimal("0"),
        unrealized_pnl=(mark_price - avg_price) * position_quantity,
        equity=cash + market_value,
    )


def test_empty_portfolio() -> None:
    portfolio = PortfolioAggregator(
        strategy_name="noop",
        initial_cash=Decimal("100000"),
    ).aggregate(positions=(), pnl_points=(), cash=Decimal("100000"))

    assert portfolio.strategy_name == "noop"
    assert portfolio.initial_cash == Decimal("100000")
    assert portfolio.cash == Decimal("100000")
    assert portfolio.total_market_value == Decimal("0")
    assert portfolio.total_equity == Decimal("100000")
    assert portfolio.positions == ()
    assert portfolio.pnl_points == ()
    assert portfolio.portfolio_id.startswith("research_portfolio_")
    assert "production portfolio" in portfolio.diagnostics[-1]


def test_single_position_portfolio_preserves_resolver_identity() -> None:
    position = _position()
    portfolio = PortfolioAggregator(
        strategy_name="buy_and_hold",
        initial_cash=Decimal("100000"),
    ).aggregate(
        positions=(position,),
        pnl_points=(_pnl_point(),),
        cash=Decimal("96800"),
    )

    assert portfolio.positions == (position,)
    assert portfolio.positions[0].symbol == "ao"
    assert portfolio.positions[0].instrument_id == "ao9999"
    assert portfolio.positions[0].trade_instrument_id == "ao2609"
    assert portfolio.positions[0].resolver_lineage == position.resolver_lineage
    assert portfolio.total_market_value == Decimal("3205")
    assert portfolio.total_equity == Decimal("100005")


def test_multi_position_portfolio() -> None:
    first = _position(
        symbol="ao",
        instrument_id="ao9999",
        trade_instrument_id="ao2609",
        market_value=Decimal("3205"),
    )
    second = _position(
        symbol="rb",
        instrument_id="rb9999",
        trade_instrument_id="rb2610",
        market_value=Decimal("3500"),
    )

    portfolio = PortfolioAggregator(
        strategy_name="multi_symbol",
        initial_cash=Decimal("100000"),
    ).aggregate(positions=(first, second), pnl_points=(), cash=Decimal("93300"))

    assert portfolio.positions == (first, second)
    assert tuple(position.symbol for position in portfolio.positions) == ("ao", "rb")
    assert portfolio.total_market_value == Decimal("6705")
    assert portfolio.total_equity == Decimal("100005")


def test_equity_aggregation() -> None:
    portfolio = PortfolioAggregator(
        strategy_name="equity",
        initial_cash=Decimal("100000"),
    ).aggregate(
        positions=(
            _position(symbol="ao", market_value=Decimal("3000")),
            _position(
                symbol="rb",
                instrument_id="rb9999",
                trade_instrument_id="rb2610",
                market_value=Decimal("4000"),
            ),
        ),
        pnl_points=(),
        cash=Decimal("93000"),
    )

    assert portfolio.total_market_value == Decimal("7000")
    assert portfolio.total_equity == Decimal("100000")


def test_deterministic_output() -> None:
    position = _position()
    pnl_point = _pnl_point()
    aggregator = PortfolioAggregator(
        strategy_name="deterministic",
        initial_cash=Decimal("100000"),
    )

    first = aggregator.aggregate(
        positions=(position,),
        pnl_points=(pnl_point,),
        cash=Decimal("96800"),
    )
    second = aggregator.aggregate(
        positions=(position,),
        pnl_points=(pnl_point,),
        cash=Decimal("96800"),
    )

    assert first == second
    assert first.portfolio_id == second.portfolio_id


def test_portfolio_module_has_no_db_live_or_network_imports() -> None:
    source = "\n".join(
        (
            inspect.getsource(portfolio_module),
            inspect.getsource(engine_module),
        )
    )

    forbidden_fragments = (
        "from futures_mvp.db",
        "import futures_mvp.db",
        "from futures_mvp.modules.oms",
        "from futures_mvp.modules.oms_to_trade",
        "from futures_mvp.modules.position",
        "from futures_mvp.modules.pnl",
        "from futures_mvp.modules.margin",
        "from futures_mvp.modules.settlement",
        "from futures_mvp.modules.execution_gateway",
        "from futures_mvp.modules.broker_adapter",
        "import socket",
        "import requests",
        "import httpx",
        "import urllib",
        "ExecutionTarget.PAPER",
        "ExecutionTarget.SIM",
        "ExecutionTarget.LIVE",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)
    assert backtest_package.PortfolioAggregator is PortfolioAggregator
