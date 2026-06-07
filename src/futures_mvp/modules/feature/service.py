from collections.abc import Callable, Sequence

from futures_mvp.domain.enums import FeatureResultStatus
from futures_mvp.domain.models import Bar, FeatureBuildResult, FeatureConfig
from futures_mvp.interfaces.repositories import FeatureSnapshotConflictError, FeatureUnitOfWork
from futures_mvp.modules.feature.builder import FeatureBuilder
from futures_mvp.modules.feature.canonical import canonical_feature_snapshot_payload


class FeatureService:
    def __init__(
        self,
        uow_factory: Callable[[], FeatureUnitOfWork],
        builder: FeatureBuilder | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._builder = builder or FeatureBuilder()

    def build_and_persist(
        self,
        bars: Sequence[Bar],
        config: FeatureConfig,
    ) -> FeatureBuildResult:
        result = self._builder.build(bars, config)
        if result.snapshot is None:
            return result

        snapshot = result.snapshot
        with self._uow_factory() as uow:
            existing = uow.feature_snapshots.get_by_identity(
                snapshot.exchange,
                snapshot.instrument_id,
                snapshot.timeframe,
                snapshot.bar_ts,
                snapshot.feature_version,
                snapshot.feature_config_hash,
            )
            if existing is not None:
                if canonical_feature_snapshot_payload(
                    existing
                ) == canonical_feature_snapshot_payload(snapshot):
                    return FeatureBuildResult(
                        status=FeatureResultStatus.DUPLICATE,
                        snapshot=existing,
                        reason="duplicate",
                    )
                return FeatureBuildResult(
                    status=FeatureResultStatus.CONFLICT,
                    reason="canonical_conflict",
                )
            try:
                persisted = uow.feature_snapshots.append_feature_snapshot(snapshot)
            except FeatureSnapshotConflictError:
                return FeatureBuildResult(
                    status=FeatureResultStatus.CONFLICT,
                    reason="canonical_conflict",
                )
            uow.commit()
            return FeatureBuildResult(
                status=result.status,
                snapshot=persisted,
                reason=result.reason,
            )
