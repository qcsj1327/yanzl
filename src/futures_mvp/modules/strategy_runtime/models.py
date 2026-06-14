from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from futures_mvp.modules.market_data.consumer import ResolverConsumerContext
from futures_mvp.modules.market_data.contracts import BarTimeframe, HistoricalBar


class StrategyRuntimeStatus(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    INVALID_INPUT = "INVALID_INPUT"
    ERROR = "ERROR"


class StrategyDecisionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"
    HOLD = "HOLD"


@dataclass(frozen=True)
class StrategyContext:
    strategy_name: str
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date | None
    timeframe: BarTimeframe
    current_bar: HistoricalBar | None
    historical_bars: tuple[HistoricalBar, ...]
    resolver_lineage: ResolverConsumerContext | None
    data_source_summary: Mapping[str, Any]
    portfolio_snapshot: Mapping[str, Any] | None
    config: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data_source_summary",
            freeze_mapping(self.data_source_summary),
        )
        object.__setattr__(
            self,
            "portfolio_snapshot",
            None
            if self.portfolio_snapshot is None
            else freeze_mapping(self.portfolio_snapshot),
        )
        object.__setattr__(self, "config", freeze_mapping(self.config))

    def frozen_copy(self) -> StrategyContext:
        return StrategyContext(
            strategy_name=self.strategy_name,
            symbol=self.symbol,
            instrument_id=self.instrument_id,
            trade_instrument_id=self.trade_instrument_id,
            exchange=self.exchange,
            trading_day=self.trading_day,
            timeframe=self.timeframe,
            current_bar=self.current_bar,
            historical_bars=tuple(self.historical_bars),
            resolver_lineage=self.resolver_lineage,
            data_source_summary=self.data_source_summary,
            portfolio_snapshot=self.portfolio_snapshot,
            config=self.config,
        )


@dataclass(frozen=True)
class StrategyDecision:
    decision: StrategyDecisionType
    side: str
    confidence: Decimal
    reason: str
    expected_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    tags: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategyRuntimeResult:
    status: StrategyRuntimeStatus
    decision: StrategyDecision | None = None
    diagnostics: tuple[str, ...] = ()


def freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {str(key): deep_freeze(item) for key, item in value.items()}
    )


def deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, tuple):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, list):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(deep_freeze(item) for item in value)
    return value
