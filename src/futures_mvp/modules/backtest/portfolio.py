from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from futures_mvp.modules.backtest.models import (
    ResearchPnLPoint,
    ResearchPortfolio,
    ResearchPosition,
)
from futures_mvp.modules.market_data.consumer import ResolverConsumerContext


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
        diagnostics: Iterable[str] = (),
    ) -> ResearchPortfolio:
        positions_tuple = tuple(positions)
        pnl_points_tuple = tuple(pnl_points)
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
        portfolio_id = _portfolio_id(
            strategy_name=self.strategy_name,
            initial_cash=self.initial_cash,
            cash=cash,
            total_market_value=total_market_value,
            total_equity=total_equity,
            positions=positions_tuple,
            pnl_points=pnl_points_tuple,
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
) -> str:
    payload = {
        "cash": _decimal_text(cash),
        "initial_cash": _decimal_text(initial_cash),
        "pnl_points": [_pnl_point_payload(point) for point in pnl_points],
        "positions": [_position_payload(position) for position in positions],
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
        "equity": _decimal_text(point.equity),
        "market_value": _decimal_text(point.market_value),
        "mark_price": _decimal_text(point.mark_price),
        "position_quantity": _decimal_text(point.position_quantity),
        "realized_pnl": _decimal_text(point.realized_pnl),
        "trading_day": _date_text(point.trading_day),
        "ts": _datetime_text(point.ts),
        "unrealized_pnl": _decimal_text(point.unrealized_pnl),
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
