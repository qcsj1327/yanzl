from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from futures_mvp.modules.market_data.models import InstrumentContract


class HistoricalDataStatus(StrEnum):
    OK = "OK"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    BLOCKED = "BLOCKED"


class MarketDataSource(StrEnum):
    STATIC_FIXTURE = "static_fixture"
    LOCAL_HISTORICAL_CACHE = "local_historical_cache_placeholder"
    LOCAL_HISTORICAL_DB = "local_historical_db"
    READ_ONLY_ADAPTER = "real_market_data"


class BarTimeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    D1 = "1d"


@dataclass(frozen=True)
class BidAskLevel:
    level: int
    bid_price: Decimal
    bid_volume: Decimal
    ask_price: Decimal
    ask_volume: Decimal


@dataclass(frozen=True)
class HistoricalBar:
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    session_id: str
    timeframe: BarTimeframe
    bar_ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal
    open_interest: Decimal


@dataclass(frozen=True)
class HistoricalTick:
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    session_id: str
    ts: datetime
    last_price: Decimal
    volume: Decimal
    turnover: Decimal
    open_interest: Decimal
    bid_ask_ladder: tuple[BidAskLevel, ...]


@dataclass(frozen=True)
class HistoricalQuote:
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    session_id: str
    ts: datetime
    last_price: Decimal
    volume: Decimal
    turnover: Decimal
    open_interest: Decimal
    bid_ask_ladder: tuple[BidAskLevel, ...]
    source: str


@dataclass(frozen=True)
class HistoricalBarsResult:
    status: HistoricalDataStatus
    bars: tuple[HistoricalBar, ...] = ()
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalTicksResult:
    status: HistoricalDataStatus
    ticks: tuple[HistoricalTick, ...] = ()
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalQuoteResult:
    status: HistoricalDataStatus
    quote: HistoricalQuote | None = None
    diagnostics: tuple[str, ...] = ()


class MarketDataAdapter(Protocol):
    def list_symbols(self) -> tuple[str, ...]: ...

    def list_contracts(
        self,
        symbol: str,
        trading_day: str | date,
    ) -> tuple[InstrumentContract, ...]: ...

    def get_main_contract(
        self,
        symbol: str,
        trading_day: str | date,
    ) -> InstrumentContract | None: ...

    def get_trade_contract(
        self,
        symbol: str,
        trading_day: str | date,
    ) -> InstrumentContract | None: ...

    def get_bars(
        self,
        identity: object,
        timeframe: str | BarTimeframe,
        start: datetime | date | None = None,
        end: datetime | date | None = None,
        as_of: datetime | None = None,
    ) -> HistoricalBarsResult: ...

    def get_latest_quote(
        self,
        identity: object,
        as_of: datetime | None = None,
    ) -> HistoricalQuoteResult: ...
