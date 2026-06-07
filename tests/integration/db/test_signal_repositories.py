from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from futures_mvp.db.models import Base
from futures_mvp.db.models import SignalCandidate as SignalCandidateOrm
from futures_mvp.db.models import SignalEvent as SignalEventOrm
from futures_mvp.db.repositories import (
    SQLAlchemySignalCandidateRepository,
    SQLAlchemySignalEventRepository,
)
from futures_mvp.db.unit_of_work import SQLAlchemyUnitOfWork
from futures_mvp.domain.enums import (
    BarTimeframe,
    SignalDecisionType,
    SignalLifecycleStatus,
    SignalPositionSide,
    SignalSide,
)
from futures_mvp.domain.models import SignalCandidate, SignalLifecycleEvent
from futures_mvp.interfaces.repositories import (
    SignalCandidateConflictError,
    SignalLifecycleConflictError,
)
from futures_mvp.modules.strategy.canonical import (
    build_signal_event_key,
    canonical_signal_candidate_payload,
)


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _features_ref() -> dict[str, object]:
    return {
        "bar_ts": datetime(2026, 6, 7, 9, tzinfo=UTC).isoformat(),
        "exchange": "SHFE",
        "feature_config_hash": "feature-hash",
        "feature_version": "feature-v1",
        "instrument_id": "au2606",
        "symbol": "au",
        "timeframe": BarTimeframe.M1.value,
        "trade_instrument_id": "au2606",
        "trading_day": date(2026, 6, 7).isoformat(),
    }


def _candidate(**updates: object) -> SignalCandidate:
    values = {
        "signal_id": "signal-1",
        "strategy_name": "toy",
        "strategy_version": "strategy-v1",
        "strategy_config_hash": "strategy-hash",
        "runtime_id": "runtime-1",
        "symbol": "au",
        "instrument_id": "au2606",
        "trade_instrument_id": "au2606",
        "exchange": "SHFE",
        "trading_day": date(2026, 6, 7),
        "timeframe": BarTimeframe.M1,
        "bar_ts": datetime(2026, 6, 7, 9, tzinfo=UTC),
        "feature_version": "feature-v1",
        "feature_config_hash": "feature-hash",
        "decision": SignalDecisionType.BUY,
        "side": SignalSide.BUY,
        "position_side": SignalPositionSide.LONG,
        "confidence": Decimal("0.8"),
        "strength": Decimal("1"),
        "reason": "toy",
        "expected_price": Decimal("500"),
        "holding_period_hint": "intraday",
        "tags": {"rule": "toy"},
        "features_ref": _features_ref(),
        "raw_payload": {"diagnostic": "a"},
    }
    values.update(updates)
    return SignalCandidate(**values)


def _event(**updates: object) -> SignalLifecycleEvent:
    values = {
        "signal_id": "signal-1",
        "lifecycle_status": SignalLifecycleStatus.CANDIDATE,
        "event_reason": "candidate",
        "event_ts": datetime(2026, 6, 7, 9, tzinfo=UTC),
        "raw_payload": {"diagnostic": "a"},
    }
    values.update(updates)
    values.setdefault(
        "event_key",
        build_signal_event_key(
            signal_id=str(values["signal_id"]),
            lifecycle_status=values["lifecycle_status"],
            event_ts=values["event_ts"],  # type: ignore[arg-type]
            event_reason=values["event_reason"],  # type: ignore[arg-type]
        ),
    )
    return SignalLifecycleEvent(**values)


def test_signal_candidate_repository_round_trip_and_queries() -> None:
    factory = _session_factory()
    candidate = _candidate()

    with factory.begin() as session:
        repo = SQLAlchemySignalCandidateRepository(session)
        persisted = repo.append_signal_candidate(candidate)

        assert canonical_signal_candidate_payload(persisted) == canonical_signal_candidate_payload(
            candidate
        )
        fetched = repo.get_by_signal_id("signal-1")
        assert fetched is not None
        assert canonical_signal_candidate_payload(fetched) == canonical_signal_candidate_payload(
            persisted
        )
        by_strategy = repo.list_by_strategy(
            "toy",
            "strategy-v1",
            candidate.bar_ts,
            candidate.bar_ts,
        )
        by_instrument = repo.list_by_instrument(
            "SHFE",
            "au2606",
            BarTimeframe.M1,
            candidate.bar_ts,
            candidate.bar_ts,
        )

        assert [canonical_signal_candidate_payload(item) for item in by_strategy] == [
            canonical_signal_candidate_payload(candidate)
        ]
        assert [canonical_signal_candidate_payload(item) for item in by_instrument] == [
            canonical_signal_candidate_payload(candidate)
        ]


def test_signal_candidate_duplicate_same_canonical_excludes_raw_payload() -> None:
    factory = _session_factory()
    first = _candidate(raw_payload={"diagnostic": "a"})
    second = _candidate(raw_payload={"diagnostic": "b"})

    with factory.begin() as session:
        repo = SQLAlchemySignalCandidateRepository(session)
        repo.append_signal_candidate(first)
        duplicate = repo.append_signal_candidate(second)
        count = session.scalar(select(func.count()).select_from(SignalCandidateOrm))

    assert duplicate.raw_payload == {"diagnostic": "a"}
    assert count == 1


def test_signal_candidate_duplicate_different_canonical_conflicts() -> None:
    factory = _session_factory()

    with factory.begin() as session:
        repo = SQLAlchemySignalCandidateRepository(session)
        repo.append_signal_candidate(_candidate())
        with pytest.raises(SignalCandidateConflictError):
            repo.append_signal_candidate(_candidate(confidence=Decimal("0.7")))


def test_signal_candidate_composite_duplicate_different_signal_id_conflicts() -> None:
    factory = _session_factory()

    with factory.begin() as session:
        repo = SQLAlchemySignalCandidateRepository(session)
        repo.append_signal_candidate(_candidate(signal_id="signal-1"))
        with pytest.raises(SignalCandidateConflictError):
            repo.append_signal_candidate(_candidate(signal_id="signal-2"))


def test_signal_event_repository_append_list_latest() -> None:
    factory = _session_factory()
    first = _event(lifecycle_status=SignalLifecycleStatus.CANDIDATE)
    second = _event(
        lifecycle_status=SignalLifecycleStatus.CONFIRMED,
        event_ts=datetime(2026, 6, 7, 9, 1, tzinfo=UTC),
    )

    with factory.begin() as session:
        repo = SQLAlchemySignalEventRepository(session)
        repo.append_signal_event(first)
        latest = repo.append_signal_event(second)
        events = repo.list_by_signal_id("signal-1")
        count = session.scalar(select(func.count()).select_from(SignalEventOrm))

    assert [event.lifecycle_status for event in events] == [
        SignalLifecycleStatus.CANDIDATE,
        SignalLifecycleStatus.CONFIRMED,
    ]
    assert latest.lifecycle_status is SignalLifecycleStatus.CONFIRMED
    assert count == 2


def test_signal_event_duplicate_same_canonical_noop_excludes_raw_payload() -> None:
    factory = _session_factory()
    first = _event(raw_payload={"diagnostic": "a"})
    second = _event(raw_payload={"diagnostic": "b"})

    with factory.begin() as session:
        repo = SQLAlchemySignalEventRepository(session)
        repo.append_signal_event(first)
        duplicate = repo.append_signal_event(second)
        count = session.scalar(select(func.count()).select_from(SignalEventOrm))

    assert duplicate.raw_payload == {"diagnostic": "a"}
    assert count == 1


def test_signal_event_duplicate_same_key_different_canonical_conflicts() -> None:
    factory = _session_factory()
    first = _event()
    conflicting = _event(event_key=first.event_key, event_reason="changed")

    with factory.begin() as session:
        repo = SQLAlchemySignalEventRepository(session)
        repo.append_signal_event(first)
        with pytest.raises(SignalLifecycleConflictError):
            repo.append_signal_event(conflicting)


def test_unit_of_work_exposes_signal_repositories() -> None:
    factory = _session_factory()

    with SQLAlchemyUnitOfWork(session_factory=factory) as uow:
        assert hasattr(uow, "signal_candidates")
        assert hasattr(uow, "signal_events")
        uow.signal_candidates.append_signal_candidate(_candidate())
        uow.signal_events.append_signal_event(_event())
        uow.commit()

    with factory() as session:
        assert session.scalar(select(SignalCandidateOrm)) is not None
        assert session.scalar(select(SignalEventOrm)) is not None
