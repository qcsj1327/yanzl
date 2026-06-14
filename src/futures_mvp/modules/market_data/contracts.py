from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class HistoricalDataStatus(StrEnum):
    OK = "OK"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"


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
