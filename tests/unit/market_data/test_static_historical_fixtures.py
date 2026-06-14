from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal

import pytest

from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    HistoricalDataStatus,
)
from futures_mvp.modules.market_data.fixtures import StaticHistoricalDataFixtureProvider


def test_supported_symbols_return_all_supported_bar_timeframes() -> None:
    provider = StaticHistoricalDataFixtureProvider()
    expected_contracts = {
        "ao": ("ao9999", "ao2609"),
        "rb": ("rb9999", "rb2610"),
        "ag": ("ag9999", "ag2608"),
        "cu": ("cu9999", "cu2608"),
    }

    for symbol, (instrument_id, trade_instrument_id) in expected_contracts.items():
        for timeframe in BarTimeframe:
            result = provider.get_bars(symbol.upper(), date(2026, 6, 12), timeframe)

            assert result.status is HistoricalDataStatus.OK
            assert result.bars
            assert "static fixture only, not live market source" in result.diagnostics
            assert "no lookahead" in result.diagnostics
            for bar in result.bars:
                assert bar.symbol == symbol
                assert bar.instrument_id == instrument_id
                assert bar.trade_instrument_id == trade_instrument_id
                assert bar.exchange == "SHFE"
                assert bar.trading_day == date(2026, 6, 12)
                assert bar.session_id == "day"
                assert bar.timeframe is timeframe
                assert bar.high >= max(bar.open, bar.low, bar.close)
                assert bar.low <= min(bar.open, bar.high, bar.close)
                assert bar.volume >= 0
                assert bar.turnover >= 0
                assert bar.open_interest >= 0


def test_tick_fixture_returns_deterministic_standardized_stream() -> None:
    provider = StaticHistoricalDataFixtureProvider()

    first = provider.get_ticks("ao", "2026-06-12")
    second = provider.get_ticks("ao", "2026-06-12")

    assert first == second
    assert first.status is HistoricalDataStatus.OK
    assert len(first.ticks) == 4
    assert tuple(tick.ts for tick in first.ticks) == tuple(sorted(tick.ts for tick in first.ticks))
    assert first.ticks[0].last_price == Decimal("3200")
    assert first.ticks[0].bid_ask_ladder[0].level == 1
    assert first.ticks[0].bid_ask_ladder[0].bid_price < first.ticks[0].last_price
    assert first.ticks[0].bid_ask_ladder[0].ask_price > first.ticks[0].last_price


def test_latest_quote_uses_latest_tick_without_lookahead() -> None:
    provider = StaticHistoricalDataFixtureProvider()
    as_of = datetime(2026, 6, 12, 9, 0, 30)

    quote_result = provider.get_latest_quote("ao", "2026-06-12", as_of=as_of)

    assert quote_result.status is HistoricalDataStatus.OK
    assert quote_result.quote is not None
    assert quote_result.quote.ts == as_of
    assert quote_result.quote.last_price == Decimal("3201")
    assert quote_result.quote.source == "static_historical_fixture"
    assert "latest standardized snapshot" in quote_result.diagnostics


def test_bars_ticks_and_quotes_do_not_look_ahead() -> None:
    provider = StaticHistoricalDataFixtureProvider()
    as_of = datetime(2026, 6, 12, 9, 1)

    bars = provider.get_bars("ao", "2026-06-12", "1m", as_of=as_of)
    ticks = provider.get_ticks("ao", "2026-06-12", as_of=as_of)
    quote = provider.get_latest_quote("ao", "2026-06-12", as_of=as_of)

    assert bars.status is HistoricalDataStatus.OK
    assert ticks.status is HistoricalDataStatus.OK
    assert quote.status is HistoricalDataStatus.OK
    assert all(bar.bar_ts <= as_of for bar in bars.bars)
    assert all(tick.ts <= as_of for tick in ticks.ticks)
    assert quote.quote is not None
    assert quote.quote.ts <= as_of
    assert len(bars.bars) == 2
    assert len(ticks.ticks) == 3


def test_fixture_objects_are_immutable() -> None:
    provider = StaticHistoricalDataFixtureProvider()
    bars = provider.get_bars("ao", "2026-06-12", "1m")
    ticks = provider.get_ticks("ao", "2026-06-12")
    quote = provider.get_latest_quote("ao", "2026-06-12")

    assert bars.bars
    assert ticks.ticks
    assert quote.quote is not None
    with pytest.raises(FrozenInstanceError):
        bars.bars[0].close = Decimal("1")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        ticks.ticks[0].last_price = Decimal("1")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        quote.quote.last_price = Decimal("1")  # type: ignore[misc]


def test_unsupported_symbol_returns_not_found() -> None:
    provider = StaticHistoricalDataFixtureProvider()

    bars = provider.get_bars("zz", "2026-06-12", "1m")
    ticks = provider.get_ticks("zz", "2026-06-12")
    quote = provider.get_latest_quote("zz", "2026-06-12")

    assert bars.status is HistoricalDataStatus.NOT_FOUND
    assert ticks.status is HistoricalDataStatus.NOT_FOUND
    assert quote.status is HistoricalDataStatus.NOT_FOUND
    assert "resolver status=NOT_FOUND" in bars.diagnostics


def test_unsupported_timeframe_returns_invalid_input() -> None:
    result = StaticHistoricalDataFixtureProvider().get_bars("ao", "2026-06-12", "30m")

    assert result.status is HistoricalDataStatus.INVALID_INPUT
    assert result.bars == ()
    assert "unsupported timeframe" in result.diagnostics


def test_trading_day_outside_2026_fixture_window_returns_not_found() -> None:
    result = StaticHistoricalDataFixtureProvider().get_bars("ao", "2027-01-01", "1m")

    assert result.status is HistoricalDataStatus.NOT_FOUND
    assert "resolver status=EXPIRED" in result.diagnostics
