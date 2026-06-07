from datetime import UTC, date, datetime
from decimal import Decimal
from types import TracebackType

from futures_mvp.domain.enums import (
    BarTimeframe,
    FeatureResultStatus,
    MarketDataResultStatus,
)
from futures_mvp.domain.models import Bar, FeatureConfig, FeatureSnapshot
from futures_mvp.interfaces.repositories import FeatureSnapshotConflictError
from futures_mvp.modules.feature import (
    FeatureService,
    canonical_feature_snapshot_payload,
    replay_feature_bars,
)


def _config(**updates: object) -> FeatureConfig:
    values = {
        "feature_version": "feature-v1",
        "timeframe": BarTimeframe.M1,
        "ma_window": 1,
        "atr_window": 1,
        "volume_window": 1,
        "breakout_window": 1,
        "volatility_window": 1,
        "momentum_window": 1,
        "allow_gap": False,
    }
    values.update(updates)
    return FeatureConfig(**values)


def _bar(minute: int, close: Decimal) -> Bar:
    return Bar(
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        timeframe=BarTimeframe.M1,
        bar_ts=datetime(2026, 6, 7, 9, minute, tzinfo=UTC),
        open=close - Decimal("1"),
        high=close + Decimal("1"),
        low=close - Decimal("2"),
        close=close,
        volume=Decimal("10") + Decimal(minute),
        turnover=Decimal("1"),
        open_interest=Decimal("1"),
        source="adapter",
        quality_status=MarketDataResultStatus.ACCEPTED,
    )


class FakeFeatureSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: dict[
            tuple[str, str, BarTimeframe, datetime, str, str],
            FeatureSnapshot,
        ] = {}

    def append_feature_snapshot(self, snapshot: FeatureSnapshot) -> FeatureSnapshot:
        key = _key(snapshot)
        existing = self.snapshots.get(key)
        if existing is not None:
            if canonical_feature_snapshot_payload(existing) != canonical_feature_snapshot_payload(
                snapshot
            ):
                raise FeatureSnapshotConflictError("feature conflict")
            return existing
        self.snapshots[key] = snapshot
        return snapshot

    def get_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        bar_ts: datetime,
        feature_version: str,
        feature_config_hash: str,
    ) -> FeatureSnapshot | None:
        return self.snapshots.get(
            (exchange, instrument_id, timeframe, bar_ts, feature_version, feature_config_hash)
        )

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[FeatureSnapshot]:
        return [
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.exchange == exchange
            and snapshot.instrument_id == instrument_id
            and snapshot.timeframe == timeframe
            and start_bar_ts <= snapshot.bar_ts <= end_bar_ts
        ]

    def list_by_trading_day(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        trading_day: date,
    ) -> list[FeatureSnapshot]:
        return [
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.exchange == exchange
            and snapshot.instrument_id == instrument_id
            and snapshot.timeframe == timeframe
            and snapshot.trading_day == trading_day
        ]


class FakeFeatureUnitOfWork:
    def __init__(self, repository: FakeFeatureSnapshotRepository | None = None) -> None:
        self.feature_snapshots = repository or FakeFeatureSnapshotRepository()
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def __enter__(self) -> "FakeFeatureUnitOfWork":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        del exc_type, exc, tb
        return None


def _key(snapshot: FeatureSnapshot) -> tuple[str, str, BarTimeframe, datetime, str, str]:
    return (
        snapshot.exchange,
        snapshot.instrument_id,
        snapshot.timeframe,
        snapshot.bar_ts,
        snapshot.feature_version,
        snapshot.feature_config_hash,
    )


def test_feature_service_persists_duplicate_and_conflict_paths() -> None:
    repository = FakeFeatureSnapshotRepository()
    uows: list[FakeFeatureUnitOfWork] = []

    def uow_factory() -> FakeFeatureUnitOfWork:
        uow = FakeFeatureUnitOfWork(repository)
        uows.append(uow)
        return uow

    service = FeatureService(uow_factory)
    bars = (_bar(0, Decimal("100")), _bar(1, Decimal("102")))

    first = service.build_and_persist(bars, _config())
    assert first.snapshot is not None
    duplicate = service.build_and_persist(bars, _config())
    conflicting_snapshot = first.snapshot.model_copy(update={"bar_return": Decimal("99")})
    repository.snapshots[_key(first.snapshot)] = conflicting_snapshot
    conflict = service.build_and_persist(bars, _config())

    assert first.status is FeatureResultStatus.ACCEPTED
    assert duplicate.status is FeatureResultStatus.DUPLICATE
    assert conflict.status is FeatureResultStatus.CONFLICT
    assert [uow.commits for uow in uows] == [1, 0, 0]


def test_feature_service_does_not_persist_fatal_rejection() -> None:
    uow = FakeFeatureUnitOfWork()
    service = FeatureService(lambda: uow)

    result = service.build_and_persist((), _config())

    assert result.status is FeatureResultStatus.REJECTED_EMPTY_INPUT
    assert not uow.feature_snapshots.snapshots
    assert uow.commits == 0


def test_feature_replay_is_deterministic_and_uses_duplicate_noop() -> None:
    repository = FakeFeatureSnapshotRepository()
    service = FeatureService(lambda: FakeFeatureUnitOfWork(repository))
    bars = (_bar(0, Decimal("100")), _bar(1, Decimal("102")), _bar(2, Decimal("103")))

    first = replay_feature_bars(service, bars, _config())
    second = replay_feature_bars(service, tuple(reversed(bars)), _config())

    assert [result.status for result in first.results] == [
        FeatureResultStatus.WARMUP_INCOMPLETE,
        FeatureResultStatus.ACCEPTED,
        FeatureResultStatus.ACCEPTED,
    ]
    assert [result.status for result in second.results] == [
        FeatureResultStatus.DUPLICATE,
        FeatureResultStatus.DUPLICATE,
        FeatureResultStatus.DUPLICATE,
    ]
    assert len(repository.snapshots) == 3


def test_feature_replay_separates_same_version_with_different_config_hash() -> None:
    repository = FakeFeatureSnapshotRepository()
    service = FeatureService(lambda: FakeFeatureUnitOfWork(repository))
    bars = (_bar(0, Decimal("100")), _bar(1, Decimal("102")), _bar(2, Decimal("103")))

    first = replay_feature_bars(service, bars, _config())
    second = replay_feature_bars(service, bars, _config(ma_window=2))

    assert all(result.status is not FeatureResultStatus.CONFLICT for result in first.results)
    assert all(result.status is not FeatureResultStatus.CONFLICT for result in second.results)
    assert len(repository.snapshots) == 6


def test_feature_service_and_replay_do_not_expose_accounting_or_market_mutation() -> None:
    uow = FakeFeatureUnitOfWork()
    service = FeatureService(lambda: uow)
    replay_feature_bars(service, (_bar(0, Decimal("100")), _bar(1, Decimal("102"))), _config())

    assert not hasattr(uow, "market_bars")
    assert not hasattr(uow, "account_snapshots")
    assert not hasattr(uow, "positions")
