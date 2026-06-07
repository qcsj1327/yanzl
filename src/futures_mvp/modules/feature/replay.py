from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from futures_mvp.domain.enums import FeatureResultStatus
from futures_mvp.domain.models import Bar, FeatureBuildResult, FeatureConfig
from futures_mvp.modules.feature.service import FeatureService


@dataclass(frozen=True)
class FeatureReplayResult:
    results: tuple[FeatureBuildResult, ...]

    @property
    def has_error(self) -> bool:
        return any(
            result.status in {FeatureResultStatus.CONFLICT, FeatureResultStatus.ERROR}
            for result in self.results
        )


def replay_feature_bars(
    service: FeatureService,
    bars: Sequence[Bar],
    config: FeatureConfig,
) -> FeatureReplayResult:
    feature_config_hash = config.config_hash()
    grouped: dict[tuple[str, str, str, str, str], list[Bar]] = defaultdict(list)
    for bar in bars:
        grouped[
            (
                bar.exchange,
                bar.instrument_id,
                bar.timeframe.value,
                config.feature_version,
                feature_config_hash,
            )
        ].append(bar)

    results: list[FeatureBuildResult] = []
    for group in sorted(grouped.values(), key=_group_sort_key):
        ordered_group = sorted(group, key=_bar_sort_key)
        for index in range(1, len(ordered_group) + 1):
            results.append(service.build_and_persist(ordered_group[:index], config))
    return FeatureReplayResult(results=tuple(results))


def _group_sort_key(group: list[Bar]) -> tuple[object, ...]:
    first = min(group, key=_bar_sort_key)
    return (first.exchange, first.instrument_id, first.timeframe.value, first.bar_ts)


def _bar_sort_key(bar: Bar) -> tuple[object, ...]:
    return (
        bar.bar_ts,
        bar.exchange,
        bar.instrument_id,
        bar.timeframe.value,
        bar.symbol,
        bar.trade_instrument_id,
        bar.source,
        _bar_fingerprint(bar),
    )


def _bar_fingerprint(bar: Bar) -> str:
    return repr(
        (
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
    )
