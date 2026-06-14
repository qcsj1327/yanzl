from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    BidAskLevel,
    HistoricalBar,
    HistoricalBarsResult,
    HistoricalDataStatus,
    HistoricalQuote,
    HistoricalQuoteResult,
    HistoricalTick,
    HistoricalTicksResult,
)
from futures_mvp.modules.market_data.models import InstrumentResolveStatus
from futures_mvp.modules.market_data.resolver import InstrumentResolver

STATIC_HISTORICAL_FIXTURE_SOURCE = "static_historical_fixture"
STATIC_HISTORICAL_FIXTURE_WARNING = "static fixture only, not live market source"
SUPPORTED_TRADING_DAY_START = date(2026, 1, 1)
SUPPORTED_TRADING_DAY_END = date(2026, 12, 31)

_SUPPORTED_TIMEFRAMES = {timeframe.value for timeframe in BarTimeframe}
_SYMBOL_PRICE_BASE: dict[str, Decimal] = {
    "ao": Decimal("3200"),
    "rb": Decimal("3500"),
    "ag": Decimal("8200"),
    "cu": Decimal("78000"),
}


class StaticHistoricalDataFixtureProvider:
    def __init__(self, resolver: InstrumentResolver | None = None) -> None:
        self._resolver = resolver or InstrumentResolver()

    def get_bars(
        self,
        symbol: str,
        trading_day: str | date,
        timeframe: str | BarTimeframe,
        *,
        as_of: datetime | None = None,
    ) -> HistoricalBarsResult:
        normalized_timeframe = _normalize_timeframe(timeframe)
        if normalized_timeframe is None:
            return HistoricalBarsResult(
                status=HistoricalDataStatus.INVALID_INPUT,
                diagnostics=(
                    STATIC_HISTORICAL_FIXTURE_WARNING,
                    "unsupported timeframe",
                    f"supported timeframes={','.join(sorted(_SUPPORTED_TIMEFRAMES))}",
                ),
            )
        resolution = self._resolver.resolve(symbol, trading_day)
        if resolution.status is not InstrumentResolveStatus.RESOLVED:
            return HistoricalBarsResult(
                status=_fixture_status_from_resolver_status(resolution.status),
                diagnostics=(
                    STATIC_HISTORICAL_FIXTURE_WARNING,
                    f"resolver status={resolution.status.value}",
                    *resolution.diagnostics,
                ),
            )
        bars = _bars_for_resolution(
            symbol=resolution.symbol,
            instrument_id=_required(resolution.instrument_id),
            trade_instrument_id=_required(resolution.trade_instrument_id),
            exchange=_required(resolution.exchange),
            trading_day=_required_day(resolution.trading_day),
            timeframe=normalized_timeframe,
        )
        return HistoricalBarsResult(
            status=HistoricalDataStatus.OK,
            bars=_without_lookahead(bars, as_of),
            diagnostics=(
                STATIC_HISTORICAL_FIXTURE_WARNING,
                f"source={STATIC_HISTORICAL_FIXTURE_SOURCE}",
                "standardized bars only",
                "no lookahead",
            ),
        )

    def get_ticks(
        self,
        symbol: str,
        trading_day: str | date,
        *,
        as_of: datetime | None = None,
    ) -> HistoricalTicksResult:
        resolution = self._resolver.resolve(symbol, trading_day)
        if resolution.status is not InstrumentResolveStatus.RESOLVED:
            return HistoricalTicksResult(
                status=_fixture_status_from_resolver_status(resolution.status),
                diagnostics=(
                    STATIC_HISTORICAL_FIXTURE_WARNING,
                    f"resolver status={resolution.status.value}",
                    *resolution.diagnostics,
                ),
            )
        ticks = _ticks_for_resolution(
            symbol=resolution.symbol,
            instrument_id=_required(resolution.instrument_id),
            trade_instrument_id=_required(resolution.trade_instrument_id),
            exchange=_required(resolution.exchange),
            trading_day=_required_day(resolution.trading_day),
        )
        return HistoricalTicksResult(
            status=HistoricalDataStatus.OK,
            ticks=_ticks_without_lookahead(ticks, as_of),
            diagnostics=(
                STATIC_HISTORICAL_FIXTURE_WARNING,
                f"source={STATIC_HISTORICAL_FIXTURE_SOURCE}",
                "standardized ticks only",
                "no lookahead",
            ),
        )

    def get_latest_quote(
        self,
        symbol: str,
        trading_day: str | date,
        *,
        as_of: datetime | None = None,
    ) -> HistoricalQuoteResult:
        ticks_result = self.get_ticks(symbol, trading_day, as_of=as_of)
        if ticks_result.status is not HistoricalDataStatus.OK:
            return HistoricalQuoteResult(
                status=ticks_result.status,
                diagnostics=ticks_result.diagnostics,
            )
        if not ticks_result.ticks:
            return HistoricalQuoteResult(
                status=HistoricalDataStatus.NOT_FOUND,
                diagnostics=(
                    STATIC_HISTORICAL_FIXTURE_WARNING,
                    "no tick available at or before as_of",
                    "no lookahead",
                ),
            )
        latest_tick = ticks_result.ticks[-1]
        return HistoricalQuoteResult(
            status=HistoricalDataStatus.OK,
            quote=HistoricalQuote(
                symbol=latest_tick.symbol,
                instrument_id=latest_tick.instrument_id,
                trade_instrument_id=latest_tick.trade_instrument_id,
                exchange=latest_tick.exchange,
                trading_day=latest_tick.trading_day,
                session_id=latest_tick.session_id,
                ts=latest_tick.ts,
                last_price=latest_tick.last_price,
                volume=latest_tick.volume,
                turnover=latest_tick.turnover,
                open_interest=latest_tick.open_interest,
                bid_ask_ladder=latest_tick.bid_ask_ladder,
                source=STATIC_HISTORICAL_FIXTURE_SOURCE,
            ),
            diagnostics=(
                STATIC_HISTORICAL_FIXTURE_WARNING,
                f"source={STATIC_HISTORICAL_FIXTURE_SOURCE}",
                "latest standardized snapshot",
                "no lookahead",
            ),
        )


def get_bars(
    symbol: str,
    trading_day: str | date,
    timeframe: str | BarTimeframe,
    *,
    as_of: datetime | None = None,
) -> HistoricalBarsResult:
    return StaticHistoricalDataFixtureProvider().get_bars(
        symbol,
        trading_day,
        timeframe,
        as_of=as_of,
    )


def get_ticks(
    symbol: str,
    trading_day: str | date,
    *,
    as_of: datetime | None = None,
) -> HistoricalTicksResult:
    return StaticHistoricalDataFixtureProvider().get_ticks(symbol, trading_day, as_of=as_of)


def get_latest_quote(
    symbol: str,
    trading_day: str | date,
    *,
    as_of: datetime | None = None,
) -> HistoricalQuoteResult:
    return StaticHistoricalDataFixtureProvider().get_latest_quote(
        symbol,
        trading_day,
        as_of=as_of,
    )


def _normalize_timeframe(timeframe: str | BarTimeframe) -> BarTimeframe | None:
    if isinstance(timeframe, BarTimeframe):
        return timeframe
    try:
        return BarTimeframe(timeframe.strip().lower())
    except ValueError:
        return None


def _fixture_status_from_resolver_status(
    status: InstrumentResolveStatus,
) -> HistoricalDataStatus:
    if status is InstrumentResolveStatus.INVALID_INPUT:
        return HistoricalDataStatus.INVALID_INPUT
    return HistoricalDataStatus.NOT_FOUND


def _bars_for_resolution(
    *,
    symbol: str,
    instrument_id: str,
    trade_instrument_id: str,
    exchange: str,
    trading_day: date,
    timeframe: BarTimeframe,
) -> tuple[HistoricalBar, ...]:
    session_id = "day"
    timestamps = _bar_timestamps(trading_day, timeframe)
    base_price = _SYMBOL_PRICE_BASE[symbol]
    return tuple(
        _bar(
            symbol=symbol,
            instrument_id=instrument_id,
            trade_instrument_id=trade_instrument_id,
            exchange=exchange,
            trading_day=trading_day,
            session_id=session_id,
            timeframe=timeframe,
            bar_ts=bar_ts,
            base_price=base_price + Decimal(index),
            index=index,
        )
        for index, bar_ts in enumerate(timestamps)
    )


def _ticks_for_resolution(
    *,
    symbol: str,
    instrument_id: str,
    trade_instrument_id: str,
    exchange: str,
    trading_day: date,
) -> tuple[HistoricalTick, ...]:
    base_price = _SYMBOL_PRICE_BASE[symbol]
    timestamps = (
        datetime.combine(trading_day, time(9, 0)),
        datetime.combine(trading_day, time(9, 0, 30)),
        datetime.combine(trading_day, time(9, 1)),
        datetime.combine(trading_day, time(9, 1, 30)),
    )
    return tuple(
        _tick(
            symbol=symbol,
            instrument_id=instrument_id,
            trade_instrument_id=trade_instrument_id,
            exchange=exchange,
            trading_day=trading_day,
            session_id="day",
            ts=ts,
            last_price=base_price + Decimal(index),
            index=index,
        )
        for index, ts in enumerate(timestamps)
    )


def _bar_timestamps(trading_day: date, timeframe: BarTimeframe) -> tuple[datetime, ...]:
    if timeframe is BarTimeframe.M1:
        return (
            datetime.combine(trading_day, time(9, 0)),
            datetime.combine(trading_day, time(9, 1)),
            datetime.combine(trading_day, time(9, 2)),
        )
    if timeframe is BarTimeframe.M5:
        return (
            datetime.combine(trading_day, time(9, 0)),
            datetime.combine(trading_day, time(9, 5)),
            datetime.combine(trading_day, time(9, 10)),
        )
    if timeframe is BarTimeframe.M15:
        return (
            datetime.combine(trading_day, time(9, 0)),
            datetime.combine(trading_day, time(9, 15)),
            datetime.combine(trading_day, time(9, 30)),
        )
    if timeframe is BarTimeframe.H1:
        return (
            datetime.combine(trading_day, time(9, 0)),
            datetime.combine(trading_day, time(10, 0)),
            datetime.combine(trading_day, time(11, 0)),
        )
    return (datetime.combine(trading_day, time(15, 0)),)


def _bar(
    *,
    symbol: str,
    instrument_id: str,
    trade_instrument_id: str,
    exchange: str,
    trading_day: date,
    session_id: str,
    timeframe: BarTimeframe,
    bar_ts: datetime,
    base_price: Decimal,
    index: int,
) -> HistoricalBar:
    return HistoricalBar(
        symbol=symbol,
        instrument_id=instrument_id,
        trade_instrument_id=trade_instrument_id,
        exchange=exchange,
        trading_day=trading_day,
        session_id=session_id,
        timeframe=timeframe,
        bar_ts=bar_ts,
        open=base_price,
        high=base_price + Decimal("2"),
        low=base_price - Decimal("1"),
        close=base_price + Decimal("1"),
        volume=Decimal("10") + Decimal(index),
        turnover=(base_price + Decimal("1")) * (Decimal("10") + Decimal(index)),
        open_interest=Decimal("100") + Decimal(index),
    )


def _tick(
    *,
    symbol: str,
    instrument_id: str,
    trade_instrument_id: str,
    exchange: str,
    trading_day: date,
    session_id: str,
    ts: datetime,
    last_price: Decimal,
    index: int,
) -> HistoricalTick:
    bid_price = last_price - Decimal("1")
    ask_price = last_price + Decimal("1")
    volume = Decimal("1") + Decimal(index)
    return HistoricalTick(
        symbol=symbol,
        instrument_id=instrument_id,
        trade_instrument_id=trade_instrument_id,
        exchange=exchange,
        trading_day=trading_day,
        session_id=session_id,
        ts=ts,
        last_price=last_price,
        volume=volume,
        turnover=last_price * volume,
        open_interest=Decimal("100") + Decimal(index),
        bid_ask_ladder=(
            BidAskLevel(
                level=1,
                bid_price=bid_price,
                bid_volume=Decimal("5") + Decimal(index),
                ask_price=ask_price,
                ask_volume=Decimal("6") + Decimal(index),
            ),
        ),
    )


def _without_lookahead(
    bars: tuple[HistoricalBar, ...],
    as_of: datetime | None,
) -> tuple[HistoricalBar, ...]:
    if as_of is None:
        return bars
    return tuple(bar for bar in bars if bar.bar_ts <= as_of)


def _ticks_without_lookahead(
    ticks: tuple[HistoricalTick, ...],
    as_of: datetime | None,
) -> tuple[HistoricalTick, ...]:
    if as_of is None:
        return ticks
    return tuple(tick for tick in ticks if tick.ts <= as_of)


def _required(value: str | None) -> str:
    if value is None:
        raise AssertionError("resolved fixture identity is missing")
    return value


def _required_day(value: date | None) -> date:
    if value is None:
        raise AssertionError("resolved fixture trading_day is missing")
    return value
