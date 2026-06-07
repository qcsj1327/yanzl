from datetime import UTC, date, datetime
from decimal import Decimal
from types import TracebackType

from futures_mvp.domain.enums import (
    BarTimeframe,
    FeatureQualityStatus,
    SignalDecisionType,
    SignalLifecycleStatus,
    SignalPositionSide,
    SignalResultStatus,
    SignalSide,
    StrategyResultStatus,
)
from futures_mvp.domain.models import (
    FeatureSnapshot,
    SignalCandidate,
    SignalDecision,
    SignalLifecycleEvent,
    StrategyConfig,
    StrategyContext,
    StrategyResult,
)
from futures_mvp.interfaces.repositories import SignalCandidateConflictError
from futures_mvp.modules.strategy import build_signal_id
from futures_mvp.modules.strategy.canonical import (
    canonical_signal_candidate_payload,
    canonical_signal_event_payload,
)
from futures_mvp.modules.strategy.replay import StrategyReplay
from futures_mvp.modules.strategy.service import SignalLifecycleService, StrategyService


def _config() -> StrategyConfig:
    return StrategyConfig.build(
        strategy_name="toy",
        strategy_version="strategy-v1",
        feature_version="feature-v1",
        feature_config_hash="feature-hash",
        timeframe=BarTimeframe.M1,
        params={"threshold": Decimal("1")},
    )


def _snapshot(bar_ts: datetime | None = None) -> FeatureSnapshot:
    ts = bar_ts or datetime(2026, 6, 7, 9, tzinfo=UTC)
    return FeatureSnapshot(
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        timeframe=BarTimeframe.M1,
        bar_ts=ts,
        feature_version="feature-v1",
        feature_config_hash="feature-hash",
        source_bar_keys=("bar-key",),
        bar_return=Decimal("1"),
        price_range=Decimal("2"),
        range=Decimal("2"),
        source_window_start=ts,
        source_window_end=ts,
        warmup_complete=False,
        quality_status=FeatureQualityStatus.WARMUP_INCOMPLETE,
    )


def _decision(
    context: StrategyContext,
    *,
    expected_price: Decimal = Decimal("500"),
    signal_id: str | None = None,
    runtime_id: str = "runtime-1",
) -> SignalDecision:
    snapshot = context.feature_snapshot
    config = context.strategy_config
    computed_signal_id = build_signal_id(
        strategy_name=config.strategy_name,
        strategy_version=config.strategy_version,
        strategy_config_hash=config.strategy_config_hash,
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
        expected_price=expected_price,
    )
    return SignalDecision(
        signal_id=signal_id or computed_signal_id,
        strategy_name=config.strategy_name,
        strategy_version=config.strategy_version,
        strategy_config_hash=config.strategy_config_hash,
        runtime_id=runtime_id,
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
        confidence=Decimal("0.9"),
        strength=Decimal("1"),
        expected_price=expected_price,
        tags={"source": "toy"},
    )


class ToyStrategy:
    def generate_signal(self, context: StrategyContext) -> SignalDecision:
        return _decision(context)


class RejectingStrategy:
    def generate_signal(self, context: StrategyContext) -> StrategyResult:
        del context
        return StrategyResult(status=StrategyResultStatus.REJECTED_DISABLED, reason="disabled")


class BadSignalIdStrategy:
    def generate_signal(self, context: StrategyContext) -> SignalDecision:
        return _decision(context, signal_id="bad-signal-id")


class RejectedWithDecisionStrategy:
    def generate_signal(self, context: StrategyContext) -> StrategyResult:
        return StrategyResult(
            status=StrategyResultStatus.REJECTED_DISABLED,
            decision=_decision(context),
            reason="invalid result",
        )


class GeneratedWithoutDecisionStrategy:
    def generate_signal(self, context: StrategyContext) -> StrategyResult:
        del context
        return StrategyResult(status=StrategyResultStatus.GENERATED)


class FakeSignalCandidateRepository:
    def __init__(self) -> None:
        self.candidates: dict[str, SignalCandidate] = {}
        self.force_conflict = False

    def append_signal_candidate(self, candidate: SignalCandidate) -> SignalCandidate:
        if self.force_conflict:
            raise SignalCandidateConflictError("conflict")
        existing = self.candidates.get(candidate.signal_id)
        if existing is not None:
            if canonical_signal_candidate_payload(existing) != canonical_signal_candidate_payload(
                candidate
            ):
                raise SignalCandidateConflictError("conflict")
            return existing
        self.candidates[candidate.signal_id] = candidate
        return candidate

    def get_by_signal_id(self, signal_id: str) -> SignalCandidate | None:
        return self.candidates.get(signal_id)

    def list_by_strategy(
        self,
        strategy_name: str,
        strategy_version: str,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[SignalCandidate]:
        return [
            candidate
            for candidate in self.candidates.values()
            if candidate.strategy_name == strategy_name
            and candidate.strategy_version == strategy_version
            and start_bar_ts <= candidate.bar_ts <= end_bar_ts
        ]

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[SignalCandidate]:
        return [
            candidate
            for candidate in self.candidates.values()
            if candidate.exchange == exchange
            and candidate.instrument_id == instrument_id
            and candidate.timeframe is timeframe
            and start_bar_ts <= candidate.bar_ts <= end_bar_ts
        ]


class FakeSignalEventRepository:
    def __init__(self) -> None:
        self.events: list[SignalLifecycleEvent] = []

    def append_signal_event(self, event: SignalLifecycleEvent) -> SignalLifecycleEvent:
        for existing in self.events:
            if existing.event_key == event.event_key:
                if canonical_signal_event_payload(
                    existing
                ) != canonical_signal_event_payload(event):
                    raise AssertionError("event conflict")
                return existing
        persisted = event.model_copy(update={"id": str(len(self.events) + 1)})
        self.events.append(persisted)
        return persisted

    def get_by_event_key(self, event_key: str) -> SignalLifecycleEvent | None:
        for event in self.events:
            if event.event_key == event_key:
                return event
        return None

    def list_by_signal_id(self, signal_id: str) -> list[SignalLifecycleEvent]:
        return [event for event in self.events if event.signal_id == signal_id]

    def get_latest_status(self, signal_id: str) -> SignalLifecycleEvent | None:
        events = self.list_by_signal_id(signal_id)
        return events[-1] if events else None


class FakeUow:
    def __init__(self) -> None:
        self.signal_candidates = FakeSignalCandidateRepository()
        self.signal_events = FakeSignalEventRepository()
        self.committed = 0
        self.rolled_back = 0

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1

    def __enter__(self) -> "FakeUow":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        del exc_type, exc, tb
        return None


def test_strategy_service_persists_candidate_and_candidate_event() -> None:
    uow = FakeUow()
    service = StrategyService(lambda: uow)
    result = service.generate_and_persist(
        StrategyContext(feature_snapshot=_snapshot(), strategy_config=_config()),
        ToyStrategy(),
    )

    assert result.status is StrategyResultStatus.GENERATED
    assert result.candidate is not None
    assert result.candidate.signal_id in uow.signal_candidates.candidates
    assert uow.signal_events.events[0].lifecycle_status is SignalLifecycleStatus.CANDIDATE
    assert uow.committed == 1


def test_rejected_strategy_result_has_no_persistence() -> None:
    uow = FakeUow()
    result = StrategyService(lambda: uow).generate_and_persist(
        StrategyContext(feature_snapshot=_snapshot(), strategy_config=_config()),
        RejectingStrategy(),
    )

    assert result.status is StrategyResultStatus.REJECTED_DISABLED
    assert uow.signal_candidates.candidates == {}
    assert uow.signal_events.events == []
    assert uow.committed == 0


def test_strategy_service_rejects_invalid_signal_id_without_persistence() -> None:
    uow = FakeUow()
    result = StrategyService(lambda: uow).generate_and_persist(
        StrategyContext(feature_snapshot=_snapshot(), strategy_config=_config()),
        BadSignalIdStrategy(),
    )

    assert result.status is StrategyResultStatus.REJECTED_INVALID_SIGNAL_ID
    assert uow.signal_candidates.candidates == {}
    assert uow.signal_events.events == []
    assert uow.committed == 0


def test_strategy_result_invalid_status_combinations_have_no_persistence() -> None:
    context = StrategyContext(feature_snapshot=_snapshot(), strategy_config=_config())
    rejected_uow = FakeUow()
    generated_uow = FakeUow()

    rejected = StrategyService(lambda: rejected_uow).generate_and_persist(
        context,
        RejectedWithDecisionStrategy(),
    )
    generated = StrategyService(lambda: generated_uow).generate_and_persist(
        context,
        GeneratedWithoutDecisionStrategy(),
    )

    assert rejected.status is StrategyResultStatus.ERROR
    assert rejected_uow.signal_candidates.candidates == {}
    assert rejected_uow.signal_events.events == []
    assert rejected_uow.committed == 0
    assert generated.status is StrategyResultStatus.ERROR
    assert generated_uow.signal_candidates.candidates == {}
    assert generated_uow.signal_events.events == []
    assert generated_uow.committed == 0


def test_duplicate_same_canonical_and_conflict_paths() -> None:
    uow = FakeUow()
    service = StrategyService(lambda: uow)
    context = StrategyContext(feature_snapshot=_snapshot(), strategy_config=_config())

    first = service.generate_and_persist(context, ToyStrategy())
    duplicate = service.generate_and_persist(context, ToyStrategy())
    uow.signal_candidates.force_conflict = True
    conflict = service.generate_and_persist(
        StrategyContext(
            feature_snapshot=_snapshot(datetime(2026, 6, 7, 9, 1, tzinfo=UTC)),
            strategy_config=_config(),
        ),
        ToyStrategy(),
    )

    assert first.status is StrategyResultStatus.GENERATED
    assert duplicate.status is StrategyResultStatus.DUPLICATE
    assert conflict.status is StrategyResultStatus.CONFLICT


def test_lifecycle_confirm_block_expire_and_trigger_rules() -> None:
    uow = FakeUow()
    strategy_service = StrategyService(lambda: uow)
    lifecycle = SignalLifecycleService(lambda: uow)
    result = strategy_service.generate_and_persist(
        StrategyContext(feature_snapshot=_snapshot(), strategy_config=_config()),
        ToyStrategy(),
    )
    assert result.candidate is not None

    confirmed = lifecycle.confirm(result.candidate.signal_id)
    triggered = lifecycle.trigger(result.candidate.signal_id)
    event_count = len(uow.signal_events.events)
    duplicate = lifecycle.trigger(result.candidate.signal_id)
    lifecycle.block(result.candidate.signal_id, "blocked")
    blocked = lifecycle.trigger(result.candidate.signal_id)
    lifecycle.expire(result.candidate.signal_id, "expired")
    expired = lifecycle.trigger(result.candidate.signal_id)

    assert confirmed.lifecycle_status is SignalLifecycleStatus.CONFIRMED
    assert triggered.status is SignalResultStatus.TRIGGERED
    assert triggered.intent == {"signal_id": result.candidate.signal_id}
    assert duplicate.status is SignalResultStatus.DUPLICATE
    assert duplicate.intent is None
    assert len(uow.signal_events.events) == event_count + 2
    assert blocked.status is SignalResultStatus.BLOCKED
    assert expired.status is SignalResultStatus.EXPIRED


def test_strategy_replay_is_deterministic_and_duplicate_noop() -> None:
    uow = FakeUow()
    service = StrategyService(lambda: uow)
    replay = StrategyReplay(service)
    snapshots = [
        _snapshot(datetime(2026, 6, 7, 9, 1, tzinfo=UTC)),
        _snapshot(datetime(2026, 6, 7, 9, tzinfo=UTC)),
    ]

    first = replay.replay(snapshots, _config(), ToyStrategy())
    second = replay.replay(reversed(snapshots), _config(), ToyStrategy())

    assert [result.status for result in first] == [
        StrategyResultStatus.GENERATED,
        StrategyResultStatus.GENERATED,
    ]
    assert [result.status for result in second] == [
        StrategyResultStatus.DUPLICATE,
        StrategyResultStatus.DUPLICATE,
    ]


def test_signal_id_excludes_runtime_id_for_replay_identity() -> None:
    context = StrategyContext(feature_snapshot=_snapshot(), strategy_config=_config())

    first = _decision(context, runtime_id="runtime-1")
    second = _decision(context, runtime_id="runtime-2")

    assert first.signal_id == second.signal_id
