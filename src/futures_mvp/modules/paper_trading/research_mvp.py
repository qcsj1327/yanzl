from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from futures_mvp.modules.backtest import (
    BacktestResult,
    BacktestStatus,
    ResearchPnLPoint,
    ResearchPortfolio,
    ResearchPosition,
    SimulatedOrder,
    SimulatedTrade,
)

MOCK_ONLY_TARGET = "MOCK"


class PaperRuntimeStatus(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class PaperSessionLifecycle(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PaperOrder:
    order_id: str
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    side: str
    quantity: Decimal
    expected_price: Decimal
    status: str
    source: str = "paper_research_only_order"


@dataclass(frozen=True)
class PaperFill:
    fill_id: str
    order_id: str
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    fill_price: Decimal
    fill_qty: Decimal
    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    source: str = "paper_research_only_mock_fill"


@dataclass(frozen=True)
class PaperPosition:
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    side: str
    quantity: Decimal
    avg_price: Decimal
    market_value: Decimal
    resolver_lineage_summary: str
    resolver_diagnostics: tuple[str, ...] = ()
    source: str = "paper_research_only_position"


@dataclass(frozen=True)
class PaperPnL:
    symbol: str
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    equity: Decimal
    cash: Decimal
    source: str = "paper_research_only_pnl"


@dataclass(frozen=True)
class PaperAllocation:
    symbol: str
    allocation: Decimal
    source: str = "paper_research_only_allocation"


@dataclass(frozen=True)
class PaperPortfolio:
    cash: Decimal
    positions: tuple[PaperPosition, ...]
    equity: Decimal
    pnl_points: tuple[PaperPnL, ...]
    allocation: tuple[PaperAllocation, ...] = ()
    source: str = "paper_research_only_portfolio"


@dataclass(frozen=True)
class PaperReport:
    equity: Decimal
    positions: tuple[PaperPosition, ...]
    orders: tuple[PaperOrder, ...]
    fills: tuple[PaperFill, ...]
    source: str = "paper_research_only_report"


@dataclass(frozen=True)
class PaperConsistencyReport:
    cash_matches: bool
    equity_matches: bool
    positions_match: bool
    orders_match: bool
    fills_match: bool
    source: str = "paper_research_consistency_report"

    @property
    def all_match(self) -> bool:
        return (
            self.cash_matches
            and self.equity_matches
            and self.positions_match
            and self.orders_match
            and self.fills_match
        )


@dataclass(frozen=True)
class PaperRuntimeResult:
    status: PaperRuntimeStatus
    reason: str | None = None
    orders: tuple[PaperOrder, ...] = ()
    fills: tuple[PaperFill, ...] = ()
    positions: tuple[PaperPosition, ...] = ()
    pnl_points: tuple[PaperPnL, ...] = ()
    portfolio: PaperPortfolio | None = None
    report: PaperReport | None = None
    consistency: PaperConsistencyReport | None = None
    diagnostics: tuple[str, ...] = (
        "Paper runtime is MOCK only",
        "Paper outputs are research-only diagnostics, not source-of-truth",
    )


@dataclass(frozen=True)
class PaperSessionResult:
    lifecycle: PaperSessionLifecycle
    runtime_result: PaperRuntimeResult | None = None
    reason: str | None = None


class PaperResearchRuntime:
    def run(
        self,
        result: BacktestResult,
        *,
        execution_target: str = MOCK_ONLY_TARGET,
    ) -> PaperRuntimeResult:
        if execution_target != MOCK_ONLY_TARGET:
            return PaperRuntimeResult(
                status=PaperRuntimeStatus.BLOCKED,
                reason="paper research runtime supports MOCK only",
            )
        if result.status is not BacktestStatus.COMPLETED:
            return PaperRuntimeResult(
                status=PaperRuntimeStatus.BLOCKED,
                reason=f"backtest result is not COMPLETED: {result.status.value}",
            )
        orders = tuple(_paper_order(order) for order in result.simulated_orders)
        fills = tuple(_paper_fill(trade) for trade in result.simulated_trades)
        positions = tuple(_paper_position(position) for position in result.research_positions)
        pnl_points = tuple(_paper_pnl(point) for point in result.research_pnl_curve)
        portfolio = _paper_portfolio(
            result.research_portfolio,
            positions=positions,
            pnl_points=pnl_points,
        )
        if portfolio is None:
            return PaperRuntimeResult(
                status=PaperRuntimeStatus.BLOCKED,
                reason="paper runtime requires research portfolio output",
            )
        report = PaperReport(
            equity=portfolio.equity,
            positions=positions,
            orders=orders,
            fills=fills,
        )
        consistency = _paper_consistency(
            result,
            orders=orders,
            fills=fills,
            positions=positions,
            portfolio=portfolio,
        )
        return PaperRuntimeResult(
            status=PaperRuntimeStatus.COMPLETED,
            orders=orders,
            fills=fills,
            positions=positions,
            pnl_points=pnl_points,
            portfolio=portfolio,
            report=report,
            consistency=consistency,
        )


class PaperResearchSession:
    def __init__(
        self,
        *,
        runtime: PaperResearchRuntime | None = None,
        execution_target: str = MOCK_ONLY_TARGET,
    ) -> None:
        self._runtime = runtime or PaperResearchRuntime()
        self._execution_target = execution_target
        self._lifecycle = PaperSessionLifecycle.IDLE

    @property
    def lifecycle(self) -> PaperSessionLifecycle:
        return self._lifecycle

    def run(self, result: BacktestResult) -> PaperSessionResult:
        if self._lifecycle is PaperSessionLifecycle.STOPPED:
            return PaperSessionResult(
                lifecycle=PaperSessionLifecycle.STOPPED,
                reason="paper session is stopped",
            )
        self._lifecycle = PaperSessionLifecycle.RUNNING
        runtime_result = self._runtime.run(
            result,
            execution_target=self._execution_target,
        )
        if runtime_result.status is PaperRuntimeStatus.BLOCKED:
            self._lifecycle = PaperSessionLifecycle.BLOCKED
            return PaperSessionResult(
                lifecycle=self._lifecycle,
                runtime_result=runtime_result,
                reason=runtime_result.reason,
            )
        self._lifecycle = PaperSessionLifecycle.COMPLETED
        return PaperSessionResult(
            lifecycle=self._lifecycle,
            runtime_result=runtime_result,
        )

    def pause(self) -> PaperSessionResult:
        if self._lifecycle is PaperSessionLifecycle.RUNNING:
            self._lifecycle = PaperSessionLifecycle.PAUSED
        return PaperSessionResult(lifecycle=self._lifecycle)

    def stop(self) -> PaperSessionResult:
        self._lifecycle = PaperSessionLifecycle.STOPPED
        return PaperSessionResult(lifecycle=self._lifecycle)


def _paper_order(order: SimulatedOrder) -> PaperOrder:
    return PaperOrder(
        order_id=order.order_id,
        symbol=order.symbol,
        instrument_id=order.instrument_id,
        trade_instrument_id=order.trade_instrument_id,
        exchange=order.exchange,
        side=order.side,
        quantity=order.quantity,
        expected_price=order.expected_price,
        status=order.status.value,
    )


def _paper_fill(trade: SimulatedTrade) -> PaperFill:
    return PaperFill(
        fill_id=trade.trade_id,
        order_id=trade.order_id,
        symbol=trade.symbol,
        instrument_id=trade.instrument_id,
        trade_instrument_id=trade.trade_instrument_id,
        exchange=trade.exchange,
        fill_price=trade.fill_price,
        fill_qty=trade.fill_qty,
        commission=trade.commission,
        slippage=trade.slippage,
    )


def _paper_position(position: ResearchPosition) -> PaperPosition:
    return PaperPosition(
        symbol=position.symbol,
        instrument_id=position.instrument_id,
        trade_instrument_id=position.trade_instrument_id,
        exchange=position.exchange,
        side=position.side,
        quantity=position.quantity,
        avg_price=position.avg_price,
        market_value=position.market_value,
        resolver_lineage_summary=_resolver_lineage_summary(position),
        resolver_diagnostics=_resolver_diagnostics(position),
    )


def _paper_pnl(point: ResearchPnLPoint) -> PaperPnL:
    return PaperPnL(
        symbol=point.symbol,
        realized_pnl=point.realized_pnl,
        unrealized_pnl=point.unrealized_pnl,
        equity=point.equity,
        cash=point.cash,
    )


def _resolver_lineage_summary(position: ResearchPosition) -> str:
    lineage = position.resolver_lineage.lineage
    return (
        f"symbol={position.symbol}; "
        f"instrument_id={position.instrument_id}; "
        f"trade_instrument_id={position.trade_instrument_id}; "
        f"exchange={position.exchange}; "
        f"resolver_source={lineage.resolver_source}; "
        f"resolver_confidence={lineage.resolver_confidence}; "
        f"effective_from={lineage.resolver_effective_from.isoformat()}; "
        f"effective_to={lineage.resolver_effective_to.isoformat()}"
    )


def _resolver_diagnostics(position: ResearchPosition) -> tuple[str, ...]:
    lineage = position.resolver_lineage.lineage
    diagnostics = []
    if lineage.resolver_diagnostics_summary:
        diagnostics.append(lineage.resolver_diagnostics_summary)
    if lineage.metadata_summary:
        diagnostics.append(lineage.metadata_summary)
    return tuple(diagnostics)


def _paper_portfolio(
    portfolio: ResearchPortfolio | None,
    *,
    positions: tuple[PaperPosition, ...],
    pnl_points: tuple[PaperPnL, ...],
) -> PaperPortfolio | None:
    if portfolio is None:
        return None
    return PaperPortfolio(
        cash=portfolio.cash,
        positions=positions,
        equity=portfolio.total_equity,
        pnl_points=pnl_points,
        allocation=_paper_allocation(portfolio),
    )


def _paper_allocation(portfolio: ResearchPortfolio) -> tuple[PaperAllocation, ...]:
    if not portfolio.positions:
        return ()
    allocation_per_position = portfolio.initial_cash / Decimal(len(portfolio.positions))
    symbols = sorted({position.symbol for position in portfolio.positions})
    return tuple(
        PaperAllocation(symbol=symbol, allocation=allocation_per_position)
        for symbol in symbols
    )


def _paper_consistency(
    result: BacktestResult,
    *,
    orders: tuple[PaperOrder, ...],
    fills: tuple[PaperFill, ...],
    positions: tuple[PaperPosition, ...],
    portfolio: PaperPortfolio,
) -> PaperConsistencyReport:
    research_portfolio = result.research_portfolio
    cash_matches = (
        research_portfolio is not None and portfolio.cash == research_portfolio.cash
    )
    equity_matches = (
        research_portfolio is not None
        and portfolio.equity == research_portfolio.total_equity
    )
    return PaperConsistencyReport(
        cash_matches=cash_matches,
        equity_matches=equity_matches,
        positions_match=_paper_positions_identity(positions)
        == _research_positions_identity(result.research_positions),
        orders_match=_paper_orders_identity(orders)
        == _research_orders_identity(result.simulated_orders),
        fills_match=_paper_fills_identity(fills)
        == _research_fills_identity(result.simulated_trades),
    )


def _paper_positions_identity(
    positions: tuple[PaperPosition, ...],
) -> tuple[tuple[str, str, str, Decimal, Decimal], ...]:
    return tuple(
        (
            position.symbol,
            position.instrument_id,
            position.trade_instrument_id,
            position.quantity,
            position.market_value,
        )
        for position in positions
    )


def _research_positions_identity(
    positions: tuple[ResearchPosition, ...],
) -> tuple[tuple[str, str, str, Decimal, Decimal], ...]:
    return tuple(
        (
            position.symbol,
            position.instrument_id,
            position.trade_instrument_id,
            position.quantity,
            position.market_value,
        )
        for position in positions
    )


def _paper_orders_identity(
    orders: tuple[PaperOrder, ...],
) -> tuple[tuple[str, str, str, Decimal, Decimal], ...]:
    return tuple(
        (
            order.order_id,
            order.symbol,
            order.trade_instrument_id,
            order.quantity,
            order.expected_price,
        )
        for order in orders
    )


def _research_orders_identity(
    orders: tuple[SimulatedOrder, ...],
) -> tuple[tuple[str, str, str, Decimal, Decimal], ...]:
    return tuple(
        (
            order.order_id,
            order.symbol,
            order.trade_instrument_id,
            order.quantity,
            order.expected_price,
        )
        for order in orders
    )


def _paper_fills_identity(
    fills: tuple[PaperFill, ...],
) -> tuple[tuple[str, str, Decimal, Decimal, Decimal, Decimal], ...]:
    return tuple(
        (
            fill.order_id,
            fill.trade_instrument_id,
            fill.fill_price,
            fill.fill_qty,
            fill.commission,
            fill.slippage,
        )
        for fill in fills
    )


def _research_fills_identity(
    trades: tuple[SimulatedTrade, ...],
) -> tuple[tuple[str, str, Decimal, Decimal, Decimal, Decimal], ...]:
    return tuple(
        (
            trade.order_id,
            trade.trade_instrument_id,
            trade.fill_price,
            trade.fill_qty,
            trade.commission,
            trade.slippage,
        )
        for trade in trades
    )
