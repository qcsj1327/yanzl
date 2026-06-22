from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from futures_mvp.modules.backtest.models import (
    BacktestEquityPoint,
    ResearchPnLPoint,
    ResearchPortfolio,
    ResearchPortfolioEquityPoint,
    ResearchPortfolioMetrics,
    ResearchPosition,
    ResearchPositionWeight,
    ResearchSymbolContribution,
)
from futures_mvp.modules.market_data.consumer import ResolverConsumerContext


@dataclass(frozen=True)
class FixedCashAllocation:
    initial_cash: Decimal
    symbols: tuple[str, ...]
    allocation_per_symbol_override: Decimal | None = None

    def allocation_per_symbol(self) -> Decimal:
        if self.allocation_per_symbol_override is not None:
            return self.allocation_per_symbol_override
        if not self.symbols:
            return Decimal("0")
        return self.initial_cash / Decimal(len(self.symbols))

    def allocations(self) -> dict[str, Decimal]:
        allocation = self.allocation_per_symbol()
        return {symbol: allocation for symbol in self.symbols}


@dataclass(frozen=True)
class PortfolioAggregator:
    strategy_name: str
    initial_cash: Decimal

    def aggregate(
        self,
        *,
        positions: Iterable[ResearchPosition],
        pnl_points: Iterable[ResearchPnLPoint],
        cash: Decimal,
        portfolio_equity_curve: Iterable[BacktestEquityPoint] = (),
        diagnostics: Iterable[str] = (),
    ) -> ResearchPortfolio:
        positions_tuple = tuple(positions)
        pnl_points_tuple = tuple(pnl_points)
        portfolio_equity_curve_tuple = _portfolio_equity_curve(portfolio_equity_curve)
        diagnostics_tuple = tuple(diagnostics) + (
            "ResearchPortfolio is research/observability only and is not a "
            "production portfolio, accounting ledger, broker account, or live "
            "position truth.",
        )
        total_market_value = sum(
            (position.market_value for position in positions_tuple),
            Decimal("0"),
        )
        total_equity = cash + total_market_value
        symbol_contributions = _symbol_contributions(
            positions=positions_tuple,
            pnl_points=pnl_points_tuple,
            initial_cash=self.initial_cash,
        )
        position_weights = _position_weights(
            positions=positions_tuple,
            total_equity=total_equity,
        )
        cash_weight = cash / total_equity if total_equity else Decimal("0")
        metrics = _portfolio_metrics(
            initial_cash=self.initial_cash,
            total_equity=total_equity,
            portfolio_equity_curve=portfolio_equity_curve_tuple,
        )
        portfolio_id = _portfolio_id(
            strategy_name=self.strategy_name,
            initial_cash=self.initial_cash,
            cash=cash,
            total_market_value=total_market_value,
            total_equity=total_equity,
            positions=positions_tuple,
            pnl_points=pnl_points_tuple,
            portfolio_equity_curve=portfolio_equity_curve_tuple,
            symbol_contributions=symbol_contributions,
            position_weights=position_weights,
            cash_weight=cash_weight,
            metrics=metrics,
        )
        return ResearchPortfolio(
            portfolio_id=portfolio_id,
            strategy_name=self.strategy_name,
            initial_cash=self.initial_cash,
            cash=cash,
            total_market_value=total_market_value,
            total_equity=total_equity,
            positions=positions_tuple,
            pnl_points=pnl_points_tuple,
            diagnostics=diagnostics_tuple,
            portfolio_equity_curve=portfolio_equity_curve_tuple,
            symbol_contributions=symbol_contributions,
            position_weights=position_weights,
            cash_weight=cash_weight,
            metrics=metrics,
        )


def _portfolio_id(
    *,
    strategy_name: str,
    initial_cash: Decimal,
    cash: Decimal,
    total_market_value: Decimal,
    total_equity: Decimal,
    positions: tuple[ResearchPosition, ...],
    pnl_points: tuple[ResearchPnLPoint, ...],
    portfolio_equity_curve: tuple[ResearchPortfolioEquityPoint, ...],
    symbol_contributions: tuple[ResearchSymbolContribution, ...],
    position_weights: tuple[ResearchPositionWeight, ...],
    cash_weight: Decimal,
    metrics: ResearchPortfolioMetrics,
) -> str:
    payload = {
        "cash": _decimal_text(cash),
        "cash_weight": _decimal_text(cash_weight),
        "initial_cash": _decimal_text(initial_cash),
        "pnl_points": [_pnl_point_payload(point) for point in pnl_points],
        "portfolio_equity_curve": [
            _portfolio_equity_point_payload(point)
            for point in portfolio_equity_curve
        ],
        "positions": [_position_payload(position) for position in positions],
        "position_weights": [
            _position_weight_payload(weight)
            for weight in position_weights
        ],
        "symbol_contributions": [
            _symbol_contribution_payload(contribution)
            for contribution in symbol_contributions
        ],
        "metrics": _metrics_payload(metrics),
        "strategy_name": strategy_name,
        "total_equity": _decimal_text(total_equity),
        "total_market_value": _decimal_text(total_market_value),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"research_portfolio_{digest[:24]}"


def _position_payload(position: ResearchPosition) -> dict[str, object]:
    return {
        "avg_price": _decimal_text(position.avg_price),
        "exchange": position.exchange,
        "instrument_id": position.instrument_id,
        "market_value": _decimal_text(position.market_value),
        "quantity": _decimal_text(position.quantity),
        "resolver_lineage": _resolver_lineage_payload(position.resolver_lineage),
        "side": position.side,
        "symbol": position.symbol,
        "trade_instrument_id": position.trade_instrument_id,
        "trading_day": _date_text(position.trading_day),
    }


def _pnl_point_payload(point: ResearchPnLPoint) -> dict[str, object]:
    return {
        "avg_price": _decimal_text(point.avg_price),
        "cash": _decimal_text(point.cash),
        "commission": _decimal_text(point.commission),
        "equity": _decimal_text(point.equity),
        "market_value": _decimal_text(point.market_value),
        "mark_price": _decimal_text(point.mark_price),
        "position_quantity": _decimal_text(point.position_quantity),
        "realized_pnl": _decimal_text(point.realized_pnl),
        "symbol": point.symbol,
        "trading_day": _date_text(point.trading_day),
        "ts": _datetime_text(point.ts),
        "unrealized_pnl": _decimal_text(point.unrealized_pnl),
    }


def _portfolio_equity_curve(
    points: Iterable[BacktestEquityPoint],
) -> tuple[ResearchPortfolioEquityPoint, ...]:
    return tuple(
        ResearchPortfolioEquityPoint(
            trading_day=point.trading_day,
            ts=point.ts,
            cash=point.cash,
            total_market_value=point.equity - point.cash,
            equity=point.equity,
        )
        for point in points
    )


def _symbol_contributions(
    *,
    positions: tuple[ResearchPosition, ...],
    pnl_points: tuple[ResearchPnLPoint, ...],
    initial_cash: Decimal,
) -> tuple[ResearchSymbolContribution, ...]:
    latest_by_symbol = _latest_pnl_by_symbol(positions=positions, pnl_points=pnl_points)
    contributions: list[ResearchSymbolContribution] = []
    for position in positions:
        pnl_point = latest_by_symbol.get(position.symbol)
        pnl_contribution = (
            pnl_point.realized_pnl + pnl_point.unrealized_pnl - pnl_point.commission
            if pnl_point is not None
            else Decimal("0")
        )
        contributions.append(
            ResearchSymbolContribution(
                symbol=position.symbol,
                market_value=position.market_value,
                equity_contribution=position.market_value + pnl_contribution,
                pnl_contribution=pnl_contribution,
            )
        )
    return tuple(sorted(contributions, key=lambda item: item.symbol))


def _latest_pnl_by_symbol(
    *,
    positions: tuple[ResearchPosition, ...],
    pnl_points: tuple[ResearchPnLPoint, ...],
) -> dict[str, ResearchPnLPoint]:
    position_symbols = {position.symbol for position in positions}
    latest: dict[str, ResearchPnLPoint] = {}
    for point in pnl_points:
        if point.symbol in position_symbols:
            latest[point.symbol] = point
    return latest


def _position_weights(
    *,
    positions: tuple[ResearchPosition, ...],
    total_equity: Decimal,
) -> tuple[ResearchPositionWeight, ...]:
    return tuple(
        ResearchPositionWeight(
            symbol=position.symbol,
            market_value=position.market_value,
            weight=(position.market_value / total_equity if total_equity else Decimal("0")),
        )
        for position in sorted(positions, key=lambda item: item.symbol)
    )


def _portfolio_metrics(
    *,
    initial_cash: Decimal,
    total_equity: Decimal,
    portfolio_equity_curve: tuple[ResearchPortfolioEquityPoint, ...],
) -> ResearchPortfolioMetrics:
    equities = tuple(point.equity for point in portfolio_equity_curve)
    max_equity = max(equities) if equities else total_equity
    min_equity = min(equities) if equities else total_equity
    return ResearchPortfolioMetrics(
        total_return=(total_equity - initial_cash) / initial_cash,
        max_equity=max_equity,
        min_equity=min_equity,
    )


def _portfolio_equity_point_payload(
    point: ResearchPortfolioEquityPoint,
) -> dict[str, object]:
    return {
        "cash": _decimal_text(point.cash),
        "equity": _decimal_text(point.equity),
        "total_market_value": _decimal_text(point.total_market_value),
        "trading_day": _date_text(point.trading_day),
        "ts": _datetime_text(point.ts),
    }


def _symbol_contribution_payload(
    contribution: ResearchSymbolContribution,
) -> dict[str, object]:
    return {
        "equity_contribution": _decimal_text(contribution.equity_contribution),
        "market_value": _decimal_text(contribution.market_value),
        "pnl_contribution": _decimal_text(contribution.pnl_contribution),
        "symbol": contribution.symbol,
    }


def _position_weight_payload(weight: ResearchPositionWeight) -> dict[str, object]:
    return {
        "market_value": _decimal_text(weight.market_value),
        "symbol": weight.symbol,
        "weight": _decimal_text(weight.weight),
    }


def _metrics_payload(metrics: ResearchPortfolioMetrics) -> dict[str, object]:
    return {
        "max_equity": _decimal_text(metrics.max_equity),
        "min_equity": _decimal_text(metrics.min_equity),
        "total_return": _decimal_text(metrics.total_return),
    }


def _resolver_lineage_payload(context: ResolverConsumerContext) -> dict[str, object]:
    identity = context.identity
    lineage = context.lineage
    return {
        "exchange": identity.exchange,
        "instrument_id": identity.instrument_id,
        "metadata_summary": lineage.metadata_summary,
        "resolver_confidence": lineage.resolver_confidence,
        "resolver_diagnostics_summary": lineage.resolver_diagnostics_summary,
        "resolver_effective_from": _date_text(lineage.resolver_effective_from),
        "resolver_effective_to": _date_text(lineage.resolver_effective_to),
        "resolver_source": lineage.resolver_source,
        "symbol": identity.symbol,
        "trade_instrument_id": identity.trade_instrument_id,
        "trading_day": _date_text(identity.trading_day),
    }


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _date_text(value: date) -> str:
    return value.isoformat()


def _datetime_text(value: datetime) -> str:
    return value.isoformat()
