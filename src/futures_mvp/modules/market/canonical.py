from futures_mvp.domain.models import Bar, Tick


def canonical_tick_payload(tick: Tick) -> tuple[object, ...]:
    return (
        tick.exchange,
        tick.instrument_id,
        tick.trade_instrument_id,
        tick.symbol,
        tick.trading_day,
        tick.ts,
        tick.price,
        tick.volume,
        tick.turnover,
        tick.open_interest,
        tick.bid_price_1,
        tick.ask_price_1,
        tick.bid_volume_1,
        tick.ask_volume_1,
        tick.source,
    )


def canonical_bar_payload(bar: Bar) -> tuple[object, ...]:
    return (
        bar.exchange,
        bar.instrument_id,
        bar.trade_instrument_id,
        bar.symbol,
        bar.trading_day,
        bar.timeframe.value,
        bar.bar_ts,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        bar.turnover,
        bar.open_interest,
        bar.source,
        bar.quality_status.value,
    )
