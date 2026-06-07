from datetime import UTC, date, datetime
from decimal import Decimal
from types import TracebackType

from futures_mvp.domain.enums import (
    BarTimeframe,
    FeatureQualityStatus,
    SignalDecisionType,
    SignalLifecycleStatus,
    SignalPositionSide,
    SignalSide,
)
from futures_mvp.domain.models import FeatureSnapshot, SignalCandidate, SignalLifecycleEvent
from futures_mvp.interfaces.repositories import (
    SignalCandidateRepository,
    SignalEventRepository,
    StrategySignalUnitOfWork,
)
from futures_mvp.modules.strategy.canonical import build_signal_event_key, signal_features_ref


def _snapshot() -> FeatureSnapshot:
    return FeatureSnapshot(
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        timeframe=BarTimeframe.M1,
        bar_ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
        feature_version="feature-v1",
        feature_config_hash="feature-hash",
        source_bar_keys=("bar-key",),
        bar_return=Decimal("1"),
        price_range=Decimal("2"),
        range=Decimal("2"),
        source_window_start=datetime(2026, 6, 7, 9, tzinfo=UTC),
        source_window_end=datetime(2026, 6, 7, 9, tzinfo=UTC),
        warmup_complete=False,
        quality_status=FeatureQualityStatus.WARMUP_INCOMPLETE,
    )


def _candidate() -> SignalCandidate:
    snapshot = _snapshot()
    return SignalCandidate(
        signal_id="signal-1",
        strategy_name="toy",
        strategy_version="strategy-v1",
        strategy_config_hash="strategy-hash",
        runtime_id="runtime-1",
        symbol=snapshot.symbol,
        instrument_id=snapshot.instrument_id,
        trade_instrument_id=snapshot.trade_instrument_id,
        exchange=snapshot.exchange,
        trading_day=snapshot.trading_day,
        timeframe=snapshot.timeframe,
        bar_ts=snapshot.bar_ts,
        feature_version=snapshot.feature_version,
        feature_config_hash=snapshot.feature_config_hash,
        decision=SignalDecisionType.BUY,
        side=SignalSide.BUY,
        position_side=SignalPositionSide.LONG,
        confidence=Decimal("0.8"),
        strength=Decimal("1"),
        expected_price=Decimal("500"),
        features_ref=signal_features_ref(snapshot),
    )


class FakeSignalCandidateRepository:
    def append_signal_candidate(self, candidate: SignalCandidate) -> SignalCandidate:
        return candidate

    def get_by_signal_id(self, signal_id: str) -> SignalCandidate | None:
        del signal_id
        return None

    def list_by_strategy(
        self,
        strategy_name: str,
        strategy_version: str,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[SignalCandidate]:
        del strategy_name, strategy_version, start_bar_ts, end_bar_ts
        return []

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[SignalCandidate]:
        del exchange, instrument_id, timeframe, start_bar_ts, end_bar_ts
        return []


class FakeSignalEventRepository:
    def append_signal_event(self, event: SignalLifecycleEvent) -> SignalLifecycleEvent:
        return event

    def get_by_event_key(self, event_key: str) -> SignalLifecycleEvent | None:
        del event_key
        return None

    def list_by_signal_id(self, signal_id: str) -> list[SignalLifecycleEvent]:
        del signal_id
        return []

    def get_latest_status(self, signal_id: str) -> SignalLifecycleEvent | None:
        del signal_id
        return None


class FakeStrategySignalUnitOfWork:
    signal_candidates = FakeSignalCandidateRepository()
    signal_events = FakeSignalEventRepository()

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def __enter__(self) -> "FakeStrategySignalUnitOfWork":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        del exc_type, exc, tb
        return None


def test_signal_candidate_repository_protocol() -> None:
    repo = FakeSignalCandidateRepository()
    candidate = _candidate()

    assert isinstance(repo, SignalCandidateRepository)
    assert repo.append_signal_candidate(candidate) is candidate


def test_signal_event_repository_protocol() -> None:
    repo = FakeSignalEventRepository()
    event = SignalLifecycleEvent(
        event_key=build_signal_event_key(
            signal_id="signal-1",
            lifecycle_status=SignalLifecycleStatus.CANDIDATE,
            event_ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
            event_reason=None,
        ),
        signal_id="signal-1",
        lifecycle_status=SignalLifecycleStatus.CANDIDATE,
        event_ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
    )

    assert isinstance(repo, SignalEventRepository)
    assert repo.append_signal_event(event) is event


def test_strategy_signal_uow_protocol_exposes_signal_repos() -> None:
    uow = FakeStrategySignalUnitOfWork()

    assert isinstance(uow, StrategySignalUnitOfWork)
    assert isinstance(uow.signal_candidates, SignalCandidateRepository)
    assert isinstance(uow.signal_events, SignalEventRepository)
