from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from typing import TypedDict

from futures_mvp.domain.enums import BarTimeframe, FeatureQualityStatus, FeatureResultStatus
from futures_mvp.domain.models import Bar, FeatureBuildResult, FeatureConfig, FeatureSnapshot


class _FeatureValues(TypedDict):
    returns: Decimal | None
    bar_return: Decimal | None
    price_range: Decimal | None
    range: Decimal | None
    atr: Decimal | None
    volume_ratio: Decimal | None
    moving_average: Decimal | None
    bias: Decimal | None
    breakout_level: Decimal | None
    volatility: Decimal | None
    momentum: Decimal | None


def source_bar_key(bar: Bar) -> str:
    return (
        f"{bar.exchange}|{bar.instrument_id}|{bar.timeframe.value}|"
        f"{bar.bar_ts.isoformat()}|{bar.source}"
    )


class FeatureBuilder:
    def build(self, bars: Sequence[Bar], config: FeatureConfig) -> FeatureBuildResult:
        ordered_bars = tuple(bars)
        if not ordered_bars:
            return FeatureBuildResult(
                status=FeatureResultStatus.REJECTED_EMPTY_INPUT,
                reason="bars are required",
            )

        validation = _validate_bars(ordered_bars, config)
        if validation is not None:
            return validation

        gap_count, missing_bar_count = _gap_counts(ordered_bars, config.timeframe)
        if gap_count > 0 and not config.allow_gap:
            return FeatureBuildResult(
                status=FeatureResultStatus.REJECTED_GAP,
                reason="source bars are not contiguous",
            )

        latest = ordered_bars[-1]
        values = _calculate_feature_values(ordered_bars, config)
        warmup_complete = all(value is not None for value in values.values())
        quality_status = _quality_status(
            gap_count=gap_count,
            warmup_complete=warmup_complete,
        )
        result_status = (
            FeatureResultStatus.WARMUP_INCOMPLETE
            if quality_status is FeatureQualityStatus.WARMUP_INCOMPLETE
            else FeatureResultStatus.ACCEPTED
        )

        snapshot = FeatureSnapshot(
            symbol=latest.symbol,
            instrument_id=latest.instrument_id,
            trade_instrument_id=latest.trade_instrument_id,
            exchange=latest.exchange,
            trading_day=latest.trading_day,
            timeframe=latest.timeframe,
            bar_ts=latest.bar_ts,
            feature_version=config.feature_version,
            feature_config_hash=config.config_hash(),
            source_bar_keys=tuple(source_bar_key(bar) for bar in ordered_bars),
            source_window_start=ordered_bars[0].bar_ts,
            source_window_end=latest.bar_ts,
            warmup_complete=warmup_complete,
            quality_status=quality_status,
            missing_bar_count=missing_bar_count,
            gap_count=gap_count,
            returns=values["returns"],
            bar_return=values["bar_return"],
            price_range=values["price_range"],
            range=values["range"],
            atr=values["atr"],
            volume_ratio=values["volume_ratio"],
            moving_average=values["moving_average"],
            bias=values["bias"],
            breakout_level=values["breakout_level"],
            volatility=values["volatility"],
            momentum=values["momentum"],
        )
        return FeatureBuildResult(status=result_status, snapshot=snapshot)


def _validate_bars(
    bars: tuple[Bar, ...],
    config: FeatureConfig,
) -> FeatureBuildResult | None:
    first = bars[0]
    if first.timeframe is not config.timeframe:
        return FeatureBuildResult(
            status=FeatureResultStatus.REJECTED_TIMEFRAME_MISMATCH,
            reason="config timeframe must match source bars",
        )
    for previous, current in zip(bars, bars[1:], strict=False):
        if current.bar_ts <= previous.bar_ts:
            return FeatureBuildResult(
                status=FeatureResultStatus.REJECTED_NON_MONOTONIC,
                reason="bar_ts must be strictly increasing",
            )
        if current.timeframe is not config.timeframe:
            return FeatureBuildResult(
                status=FeatureResultStatus.REJECTED_TIMEFRAME_MISMATCH,
                reason="source bar timeframe mismatch",
            )
        if not _same_identity(first, current):
            return FeatureBuildResult(
                status=FeatureResultStatus.REJECTED_IDENTITY_MISMATCH,
                reason="source bar identity mismatch",
            )
    return None


def _same_identity(left: Bar, right: Bar) -> bool:
    return (
        left.symbol == right.symbol
        and left.instrument_id == right.instrument_id
        and left.trade_instrument_id == right.trade_instrument_id
        and left.exchange == right.exchange
        and left.trading_day == right.trading_day
        and left.timeframe is right.timeframe
    )


def _gap_counts(bars: tuple[Bar, ...], timeframe: BarTimeframe) -> tuple[int, int]:
    expected_delta = _timeframe_delta(timeframe)
    gap_count = 0
    missing_bar_count = 0
    for previous, current in zip(bars, bars[1:], strict=False):
        delta = current.bar_ts - previous.bar_ts
        if delta != expected_delta:
            gap_count += 1
            if delta > expected_delta:
                missing_bar_count += max(int(delta / expected_delta) - 1, 0)
    return gap_count, missing_bar_count


def _timeframe_delta(timeframe: BarTimeframe) -> timedelta:
    match timeframe:
        case BarTimeframe.M1:
            return timedelta(minutes=1)
        case BarTimeframe.M5:
            return timedelta(minutes=5)
        case BarTimeframe.M15:
            return timedelta(minutes=15)
        case BarTimeframe.M30:
            return timedelta(minutes=30)
        case BarTimeframe.H1:
            return timedelta(hours=1)
        case BarTimeframe.D1:
            return timedelta(days=1)


def _quality_status(
    *,
    gap_count: int,
    warmup_complete: bool,
) -> FeatureQualityStatus:
    if gap_count > 0:
        return FeatureQualityStatus.GAP_DETECTED
    if not warmup_complete:
        return FeatureQualityStatus.WARMUP_INCOMPLETE
    return FeatureQualityStatus.ACCEPTED


def _calculate_feature_values(
    bars: tuple[Bar, ...],
    config: FeatureConfig,
) -> _FeatureValues:
    latest = bars[-1]
    moving_average: Decimal | None = _average([bar.close for bar in bars[-config.ma_window :]])
    if len(bars) < config.ma_window:
        moving_average = None

    return {
        "returns": _returns(bars),
        "bar_return": latest.close - latest.open,
        "price_range": latest.high - latest.low,
        "range": latest.high - latest.low,
        "atr": _atr(bars, config.atr_window),
        "volume_ratio": _volume_ratio(bars, config.volume_window),
        "moving_average": moving_average,
        "bias": latest.close - moving_average if moving_average is not None else None,
        "breakout_level": _breakout_level(bars, config.breakout_window),
        "volatility": _volatility(bars, config.volatility_window),
        "momentum": _momentum(bars, config.momentum_window),
    }


def _returns(bars: tuple[Bar, ...]) -> Decimal | None:
    if len(bars) < 2:
        return None
    return bars[-1].close - bars[-2].close


def _atr(bars: tuple[Bar, ...], window: int) -> Decimal | None:
    if len(bars) < window + 1:
        return None
    true_ranges: list[Decimal] = []
    for previous, current in zip(bars[-window - 1 :], bars[-window:], strict=False):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return _average(true_ranges)


def _volume_ratio(bars: tuple[Bar, ...], window: int) -> Decimal | None:
    if len(bars) < window + 1:
        return None
    previous_average = _average([bar.volume for bar in bars[-window - 1 : -1]])
    if previous_average == 0:
        return None
    return bars[-1].volume / previous_average


def _breakout_level(bars: tuple[Bar, ...], window: int) -> Decimal | None:
    if len(bars) < window:
        return None
    return max(bar.high for bar in bars[-window:])


def _volatility(bars: tuple[Bar, ...], window: int) -> Decimal | None:
    if len(bars) < window + 1:
        return None
    changes = [
        abs(current.close - previous.close)
        for previous, current in zip(bars[-window - 1 :], bars[-window:], strict=False)
    ]
    return _average(changes)


def _momentum(bars: tuple[Bar, ...], window: int) -> Decimal | None:
    if len(bars) < window + 1:
        return None
    return bars[-1].close - bars[-window - 1].close


def _average(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))
