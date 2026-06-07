from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from futures_mvp.db.models import Base
from futures_mvp.db.models import FeatureSnapshot as FeatureSnapshotOrm
from futures_mvp.db.repositories import SQLAlchemyFeatureSnapshotRepository
from futures_mvp.db.unit_of_work import SQLAlchemyUnitOfWork
from futures_mvp.domain.enums import BarTimeframe, FeatureQualityStatus
from futures_mvp.domain.models import FeatureSnapshot
from futures_mvp.interfaces.repositories import FeatureSnapshotConflictError


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _snapshot(**updates: object) -> FeatureSnapshot:
    values = {
        "symbol": "au",
        "instrument_id": "au2606",
        "trade_instrument_id": "au2606",
        "exchange": "SHFE",
        "trading_day": date(2026, 6, 7),
        "timeframe": BarTimeframe.M1,
        "bar_ts": datetime(2026, 6, 7, 9),
        "feature_version": "feature-v1",
        "feature_config_hash": "config-hash-a",
        "source_bar_keys": ("SHFE|au2606|M1|2026-06-07T09:00:00|adapter",),
        "returns": None,
        "bar_return": Decimal("1"),
        "price_range": Decimal("2"),
        "range": Decimal("2"),
        "atr": None,
        "volume_ratio": None,
        "moving_average": None,
        "bias": None,
        "breakout_level": None,
        "volatility": None,
        "momentum": None,
        "source_window_start": datetime(2026, 6, 7, 9),
        "source_window_end": datetime(2026, 6, 7, 9),
        "warmup_complete": False,
        "quality_status": FeatureQualityStatus.WARMUP_INCOMPLETE,
        "missing_bar_count": 0,
        "gap_count": 0,
        "raw_payload": {"diagnostic": "a"},
    }
    values.update(updates)
    return FeatureSnapshot(**values)


def test_feature_snapshot_repository_round_trip_and_queries() -> None:
    factory = _session_factory()
    snapshot = _snapshot()

    with factory.begin() as session:
        repo = SQLAlchemyFeatureSnapshotRepository(session)
        persisted = repo.append_feature_snapshot(snapshot)
        assert persisted == snapshot
        assert (
            repo.get_by_identity(
                "SHFE",
                "au2606",
                BarTimeframe.M1,
                snapshot.bar_ts,
                "feature-v1",
                snapshot.feature_config_hash,
            )
            == snapshot
        )
        assert repo.list_by_instrument(
            "SHFE",
            "au2606",
            BarTimeframe.M1,
            snapshot.bar_ts,
            snapshot.bar_ts,
        ) == [snapshot]
        assert repo.list_by_trading_day(
            "SHFE",
            "au2606",
            BarTimeframe.M1,
            date(2026, 6, 7),
        ) == [snapshot]


def test_feature_snapshot_duplicate_same_canonical_excludes_raw_payload() -> None:
    factory = _session_factory()
    first = _snapshot(raw_payload={"diagnostic": "a"})
    second = _snapshot(raw_payload={"diagnostic": "b"})

    with factory.begin() as session:
        repo = SQLAlchemyFeatureSnapshotRepository(session)
        repo.append_feature_snapshot(first)
        duplicate = repo.append_feature_snapshot(second)
        count = session.scalar(select(func.count()).select_from(FeatureSnapshotOrm))

    assert duplicate.raw_payload == {"diagnostic": "a"}
    assert count == 1


def test_feature_snapshot_duplicate_different_canonical_conflicts() -> None:
    factory = _session_factory()

    with factory.begin() as session:
        repo = SQLAlchemyFeatureSnapshotRepository(session)
        repo.append_feature_snapshot(_snapshot())
        with pytest.raises(FeatureSnapshotConflictError):
            repo.append_feature_snapshot(_snapshot(bar_return=Decimal("99")))


def test_feature_snapshot_same_version_different_config_hash_is_separate_identity() -> None:
    factory = _session_factory()
    first = _snapshot(feature_config_hash="config-hash-a")
    second = _snapshot(feature_config_hash="config-hash-b")

    with factory.begin() as session:
        repo = SQLAlchemyFeatureSnapshotRepository(session)
        repo.append_feature_snapshot(first)
        repo.append_feature_snapshot(second)
        count = session.scalar(select(func.count()).select_from(FeatureSnapshotOrm))

    assert count == 2


def test_unit_of_work_exposes_feature_snapshots() -> None:
    factory = _session_factory()

    with SQLAlchemyUnitOfWork(session_factory=factory) as uow:
        assert hasattr(uow, "feature_snapshots")
        uow.feature_snapshots.append_feature_snapshot(_snapshot())
        uow.commit()

    with factory() as session:
        assert session.scalar(select(FeatureSnapshotOrm)) is not None
