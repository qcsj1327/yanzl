from futures_mvp.domain.models import FeatureSnapshot


def canonical_feature_snapshot_payload(snapshot: FeatureSnapshot) -> tuple[object, ...]:
    return (
        snapshot.exchange,
        snapshot.instrument_id,
        snapshot.trade_instrument_id,
        snapshot.symbol,
        snapshot.trading_day,
        snapshot.timeframe.value,
        snapshot.bar_ts,
        snapshot.feature_version,
        snapshot.feature_config_hash,
        snapshot.source_bar_keys,
        snapshot.returns,
        snapshot.bar_return,
        snapshot.price_range,
        snapshot.range,
        snapshot.atr,
        snapshot.volume_ratio,
        snapshot.moving_average,
        snapshot.bias,
        snapshot.breakout_level,
        snapshot.volatility,
        snapshot.momentum,
        snapshot.source_window_start,
        snapshot.source_window_end,
        snapshot.warmup_complete,
        snapshot.quality_status.value,
        snapshot.missing_bar_count,
        snapshot.gap_count,
    )
