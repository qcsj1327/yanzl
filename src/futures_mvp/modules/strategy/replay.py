from collections.abc import Iterable

from futures_mvp.domain.models import (
    FeatureSnapshot,
    StrategyConfig,
    StrategyContext,
    StrategyResult,
)
from futures_mvp.modules.strategy.protocols import Strategy
from futures_mvp.modules.strategy.service import StrategyService


class StrategyReplay:
    def __init__(self, service: StrategyService) -> None:
        self._service = service

    def replay(
        self,
        snapshots: Iterable[FeatureSnapshot],
        config: StrategyConfig,
        strategy: Strategy,
    ) -> list[StrategyResult]:
        ordered = sorted(
            snapshots,
            key=lambda snapshot: (
                snapshot.exchange,
                snapshot.instrument_id,
                snapshot.timeframe.value,
                snapshot.bar_ts,
                snapshot.feature_version,
                snapshot.feature_config_hash,
            ),
        )
        results: list[StrategyResult] = []
        for snapshot in ordered:
            context = StrategyContext(feature_snapshot=snapshot, strategy_config=config)
            results.append(self._service.generate_and_persist(context, strategy))
        return results
