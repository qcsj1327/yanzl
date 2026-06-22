from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from futures_mvp.modules.backtest import (
    BacktestRequest,
    BacktestResult,
    FixedCommissionModel,
    FixedSlippageModel,
    LocalBacktestEngine,
    NextBarOpenFillModel,
)
from futures_mvp.modules.market_data.fixtures import StaticHistoricalDataFixtureProvider
from futures_mvp.modules.market_data.resolver import InstrumentResolver
from futures_mvp.modules.operator_console import paper_runtime_console_view
from futures_mvp.modules.paper_trading import (
    MOCK_ONLY_TARGET,
    PaperResearchRuntime,
    PaperResearchSession,
    PaperRuntimeStatus,
    PaperSessionLifecycle,
)
from futures_mvp.modules.strategy_runtime import BuyAndHoldStrategy

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _research_result(
    *,
    symbol: str = "ao",
    symbols: list[str] | tuple[str, ...] = (),
    quantity_mode: str = "fixed_quantity",
    allocation_per_symbol: Decimal | None = None,
    commission_model: object | None = None,
    slippage_model: object | None = None,
) -> BacktestResult:
    resolver = InstrumentResolver()
    data_provider = StaticHistoricalDataFixtureProvider(resolver)
    return LocalBacktestEngine(
        strategy=BuyAndHoldStrategy(),
        fill_model=NextBarOpenFillModel(),
    ).run(
        BacktestRequest(
            strategy_name="noop",
            symbol=symbol,
            symbols=symbols,
            start_trading_day=date(2026, 6, 12),
            end_trading_day=date(2026, 6, 12),
            timeframe="1m",
            initial_cash=Decimal("100000"),
            quantity_mode=quantity_mode,
            allocation_per_symbol=allocation_per_symbol,
            commission_model=commission_model,
            slippage_model=slippage_model,
            resolver=resolver,
            data_provider=data_provider,
        )
    )


def test_full_research_paper_lifecycle() -> None:
    runtime_result = PaperResearchRuntime().run(_research_result())

    assert runtime_result.status is PaperRuntimeStatus.COMPLETED
    assert len(runtime_result.orders) == 1
    assert len(runtime_result.fills) == 1
    assert len(runtime_result.positions) == 1
    assert runtime_result.portfolio is not None
    assert runtime_result.report is not None

    order = runtime_result.orders[0]
    fill = runtime_result.fills[0]
    position = runtime_result.positions[0]
    portfolio = runtime_result.portfolio
    report = runtime_result.report

    assert order.symbol == "ao"
    assert order.trade_instrument_id == "ao2609"
    assert order.quantity == Decimal("1")
    assert fill.order_id == order.order_id
    assert fill.fill_price == Decimal("3201")
    assert position.symbol == "ao"
    assert position.quantity == Decimal("1")
    assert position.market_value == Decimal("3203")
    assert "trade_instrument_id=ao2609" in position.resolver_lineage_summary
    assert "resolver_source=static_fixture" in position.resolver_lineage_summary
    assert position.resolver_diagnostics
    assert portfolio.cash == Decimal("96799")
    assert portfolio.equity == Decimal("100002")
    assert portfolio.positions == (position,)
    assert portfolio.allocation[0].allocation == Decimal("100000")
    assert report.equity == portfolio.equity
    assert report.orders == (order,)
    assert report.fills == (fill,)
    assert report.positions == (position,)
    assert runtime_result.consistency is not None
    assert runtime_result.consistency.all_match


def test_multi_symbol_research_paper_portfolio_aggregation_and_consistency() -> None:
    runtime_result = PaperResearchRuntime().run(
        _research_result(symbols=("ao", "rb", "ag", "cu"))
    )

    assert runtime_result.status is PaperRuntimeStatus.COMPLETED
    assert len(runtime_result.orders) == 4
    assert len(runtime_result.fills) == 4
    assert len(runtime_result.positions) == 4
    assert runtime_result.portfolio is not None
    assert runtime_result.report is not None
    assert runtime_result.consistency is not None

    portfolio = runtime_result.portfolio
    assert portfolio.cash == Decimal("7096")
    assert portfolio.equity == Decimal("100008")
    assert sum(position.market_value for position in portfolio.positions) == Decimal(
        "92912"
    )
    assert {
        position.symbol: position.trade_instrument_id
        for position in runtime_result.positions
    } == {
        "ag": "ag2608",
        "ao": "ao2609",
        "cu": "cu2608",
        "rb": "rb2610",
    }
    assert tuple(item.symbol for item in portfolio.allocation) == (
        "ag",
        "ao",
        "cu",
        "rb",
    )
    assert {item.symbol: item.allocation for item in portfolio.allocation} == {
        "ag": Decimal("25000"),
        "ao": Decimal("25000"),
        "cu": Decimal("25000"),
        "rb": Decimal("25000"),
    }
    assert runtime_result.report.equity == portfolio.equity
    assert runtime_result.report.positions == runtime_result.positions
    assert runtime_result.consistency.all_match


def test_reuses_research_commission_slippage_and_sizing_outputs() -> None:
    runtime_result = PaperResearchRuntime().run(
        _research_result(
            quantity_mode="fixed_cash",
            allocation_per_symbol=Decimal("6402"),
            commission_model=FixedCommissionModel(),
            slippage_model=FixedSlippageModel(),
        )
    )

    assert runtime_result.status is PaperRuntimeStatus.COMPLETED
    assert runtime_result.portfolio is not None
    assert runtime_result.consistency is not None

    order = runtime_result.orders[0]
    fill = runtime_result.fills[0]
    position = runtime_result.positions[0]
    portfolio = runtime_result.portfolio

    assert order.quantity == Decimal("2")
    assert fill.fill_price == Decimal("3202")
    assert fill.fill_qty == Decimal("2")
    assert fill.commission == Decimal("0.6404")
    assert fill.slippage == Decimal("1")
    assert position.quantity == Decimal("2")
    assert position.market_value == Decimal("6406")
    assert portfolio.cash == Decimal("93595.3596")
    assert portfolio.equity == Decimal("100001.3596")
    assert runtime_result.consistency.all_match


def test_operator_console_displays_paper_runtime_report() -> None:
    runtime_result = PaperResearchRuntime().run(
        _research_result(symbols=("ao", "rb", "ag", "cu"))
    )

    view = paper_runtime_console_view(runtime_result)

    assert view.status == "COMPLETED"
    assert view.equity == "100008"
    assert ("cash", "7096") in view.portfolio
    assert ("equity", "100008") in view.portfolio
    assert len(view.orders) == 4
    assert len(view.fills) == 4
    assert len(view.positions) == 4
    assert dict(view.allocation) == {
        "ag": "25000",
        "ao": "25000",
        "cu": "25000",
        "rb": "25000",
    }
    assert ("all_match", "True") in view.consistency


def test_paper_session_run_pause_stop_and_mock_only_block() -> None:
    research_result = _research_result()
    session = PaperResearchSession()

    paused_before_run = session.pause()
    assert paused_before_run.lifecycle is PaperSessionLifecycle.IDLE

    run_result = session.run(research_result)
    assert run_result.lifecycle is PaperSessionLifecycle.COMPLETED
    assert run_result.runtime_result is not None
    assert run_result.runtime_result.status is PaperRuntimeStatus.COMPLETED

    stopped = session.stop()
    assert stopped.lifecycle is PaperSessionLifecycle.STOPPED
    blocked_after_stop = session.run(research_result)
    assert blocked_after_stop.lifecycle is PaperSessionLifecycle.STOPPED
    assert blocked_after_stop.reason == "paper session is stopped"

    non_mock = PaperResearchSession(execution_target="PAPER")
    non_mock_result = non_mock.run(research_result)
    assert non_mock_result.lifecycle is PaperSessionLifecycle.BLOCKED
    assert non_mock_result.reason == "paper research runtime supports MOCK only"


def test_research_paper_mvp_has_no_forbidden_imports() -> None:
    source = (
        PROJECT_ROOT
        / "src"
        / "futures_mvp"
        / "modules"
        / "paper_trading"
        / "research_mvp.py"
    ).read_text()

    forbidden = (
        "futures_mvp.db",
        "futures_mvp.modules.oms",
        "futures_mvp.modules.oms_to_trade",
        "futures_mvp.modules.position",
        "futures_mvp.modules.pnl",
        "futures_mvp.modules.margin",
        "futures_mvp.modules.settlement",
        "futures_mvp.modules.broker_adapter",
        "ExecutionTarget.PAPER",
        "ExecutionTarget.SIM",
        "ExecutionTarget.LIVE",
        "socket",
        "requests",
        "httpx",
        "urllib",
    )
    assert MOCK_ONLY_TARGET == "MOCK"
    assert all(fragment not in source for fragment in forbidden)
