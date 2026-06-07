from collections.abc import Callable
from datetime import UTC, datetime

from futures_mvp.domain.enums import SignalLifecycleStatus, SignalResultStatus, StrategyResultStatus
from futures_mvp.domain.models import (
    SignalCandidate,
    SignalDecision,
    SignalLifecycleEvent,
    StrategyContext,
    StrategyResult,
    TriggerResult,
)
from futures_mvp.interfaces.repositories import (
    SignalCandidateConflictError,
    StrategySignalUnitOfWork,
)
from futures_mvp.modules.strategy.canonical import (
    build_signal_event_key,
    build_signal_id,
    canonical_signal_candidate_payload,
    signal_features_ref,
)
from futures_mvp.modules.strategy.lifecycle import SignalLifecycleRules
from futures_mvp.modules.strategy.protocols import Strategy


def _lifecycle_event(
    *,
    signal_id: str,
    status: SignalLifecycleStatus,
    reason: str,
) -> SignalLifecycleEvent:
    event_ts = datetime.now(UTC)
    return SignalLifecycleEvent(
        event_key=build_signal_event_key(
            signal_id=signal_id,
            lifecycle_status=status,
            event_ts=event_ts,
            event_reason=reason,
        ),
        signal_id=signal_id,
        lifecycle_status=status,
        event_reason=reason,
        event_ts=event_ts,
    )


class StrategyService:
    def __init__(self, uow_factory: Callable[[], StrategySignalUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def generate_and_persist(
        self,
        context: StrategyContext,
        strategy: Strategy,
    ) -> StrategyResult:
        generated = strategy.generate_signal(context)
        if isinstance(generated, StrategyResult):
            invalid_result_reason = self._invalid_strategy_result_reason(generated)
            if invalid_result_reason is not None:
                return StrategyResult(
                    status=StrategyResultStatus.ERROR,
                    reason=invalid_result_reason,
                )
            if generated.status is not StrategyResultStatus.GENERATED:
                return generated
            decision = generated.decision
            if decision is None:
                return StrategyResult(
                    status=StrategyResultStatus.ERROR,
                    reason="generated result missing decision",
                )
        else:
            decision = generated

        invalid_reason = self._decision_context_mismatch(decision, context)
        if invalid_reason is not None:
            return StrategyResult(
                status=StrategyResultStatus.REJECTED_INVALID_CONTEXT,
                reason=invalid_reason,
            )

        if decision.signal_id != self._expected_signal_id(decision):
            return StrategyResult(
                status=StrategyResultStatus.REJECTED_INVALID_SIGNAL_ID,
                reason="signal_id mismatch",
            )

        candidate = self._candidate_from_decision(decision, context)
        with self._uow_factory() as uow:
            existing = uow.signal_candidates.get_by_signal_id(candidate.signal_id)
            if existing is not None:
                if canonical_signal_candidate_payload(
                    existing
                ) == canonical_signal_candidate_payload(candidate):
                    return StrategyResult(
                        status=StrategyResultStatus.DUPLICATE,
                        candidate=existing,
                        reason="duplicate",
                    )
                return StrategyResult(
                    status=StrategyResultStatus.CONFLICT,
                    reason="canonical_conflict",
                )
            try:
                persisted = uow.signal_candidates.append_signal_candidate(candidate)
            except SignalCandidateConflictError:
                return StrategyResult(
                    status=StrategyResultStatus.CONFLICT,
                    reason="canonical_conflict",
                )
            uow.signal_events.append_signal_event(
                _lifecycle_event(
                    signal_id=persisted.signal_id,
                    status=SignalLifecycleStatus.CANDIDATE,
                    reason="candidate_created",
                )
            )
            uow.commit()
            return StrategyResult(status=StrategyResultStatus.GENERATED, candidate=persisted)

    def _candidate_from_decision(
        self,
        decision: SignalDecision,
        context: StrategyContext,
    ) -> SignalCandidate:
        return SignalCandidate(
            signal_id=decision.signal_id,
            strategy_name=decision.strategy_name,
            strategy_version=decision.strategy_version,
            strategy_config_hash=decision.strategy_config_hash,
            runtime_id=decision.runtime_id,
            symbol=decision.symbol,
            instrument_id=decision.instrument_id,
            trade_instrument_id=decision.trade_instrument_id,
            exchange=decision.exchange,
            trading_day=decision.trading_day,
            timeframe=decision.timeframe,
            bar_ts=decision.bar_ts,
            feature_version=decision.feature_version,
            feature_config_hash=decision.feature_config_hash,
            decision=decision.decision,
            side=decision.side,
            position_side=decision.position_side,
            confidence=decision.confidence,
            strength=decision.strength,
            reason=decision.reason,
            expected_price=decision.expected_price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            tags=decision.tags,
            features_ref=signal_features_ref(context.feature_snapshot),
            raw_payload=decision.raw_payload,
        )

    def _invalid_strategy_result_reason(self, result: StrategyResult) -> str | None:
        if result.status is StrategyResultStatus.GENERATED:
            if result.decision is None:
                return "GENERATED result requires decision"
            return None
        if result.decision is not None:
            return f"{result.status.value} result cannot include decision"
        return None

    def _expected_signal_id(self, decision: SignalDecision) -> str:
        return build_signal_id(
            strategy_name=decision.strategy_name,
            strategy_version=decision.strategy_version,
            strategy_config_hash=decision.strategy_config_hash,
            symbol=decision.symbol,
            instrument_id=decision.instrument_id,
            trade_instrument_id=decision.trade_instrument_id,
            exchange=decision.exchange,
            trading_day=decision.trading_day,
            timeframe=decision.timeframe,
            bar_ts=decision.bar_ts,
            feature_version=decision.feature_version,
            feature_config_hash=decision.feature_config_hash,
            decision=decision.decision,
            side=decision.side,
            position_side=decision.position_side,
            expected_price=decision.expected_price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
        )

    def _decision_context_mismatch(
        self,
        decision: SignalDecision,
        context: StrategyContext,
    ) -> str | None:
        snapshot = context.feature_snapshot
        config = context.strategy_config
        checks = {
            "strategy_name": (decision.strategy_name, config.strategy_name),
            "strategy_version": (decision.strategy_version, config.strategy_version),
            "strategy_config_hash": (
                decision.strategy_config_hash,
                config.strategy_config_hash,
            ),
            "symbol": (decision.symbol, snapshot.symbol),
            "instrument_id": (decision.instrument_id, snapshot.instrument_id),
            "trade_instrument_id": (
                decision.trade_instrument_id,
                snapshot.trade_instrument_id,
            ),
            "exchange": (decision.exchange, snapshot.exchange),
            "trading_day": (decision.trading_day, snapshot.trading_day),
            "timeframe": (decision.timeframe, snapshot.timeframe),
            "bar_ts": (decision.bar_ts, snapshot.bar_ts),
            "feature_version": (decision.feature_version, snapshot.feature_version),
            "feature_config_hash": (
                decision.feature_config_hash,
                snapshot.feature_config_hash,
            ),
        }
        for field_name, (actual, expected) in checks.items():
            if actual != expected:
                return f"{field_name} mismatch"
        return None


class SignalLifecycleService:
    def __init__(self, uow_factory: Callable[[], StrategySignalUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def confirm(self, signal_id: str) -> SignalLifecycleEvent:
        return self._append_status(signal_id, SignalLifecycleStatus.CONFIRMED, "confirmed")

    def block(self, signal_id: str, reason: str) -> SignalLifecycleEvent:
        return self._append_status(signal_id, SignalLifecycleStatus.BLOCKED, reason)

    def expire(self, signal_id: str, reason: str) -> SignalLifecycleEvent:
        return self._append_status(signal_id, SignalLifecycleStatus.EXPIRED, reason)

    def trigger(self, signal_id: str) -> TriggerResult:
        with self._uow_factory() as uow:
            candidate = uow.signal_candidates.get_by_signal_id(signal_id)
            if candidate is None:
                return TriggerResult(
                    status=SignalResultStatus.ERROR,
                    signal_id=signal_id,
                    reason="signal not found",
                )
            latest = uow.signal_events.get_latest_status(signal_id)
            blocked_result = SignalLifecycleRules.can_trigger(latest)
            if blocked_result is not None:
                return blocked_result
            event = uow.signal_events.append_signal_event(
                _lifecycle_event(
                    signal_id=signal_id,
                    status=SignalLifecycleStatus.TRIGGERED,
                    reason="triggered",
                )
            )
            uow.commit()
            return TriggerResult(
                status=SignalResultStatus.TRIGGERED,
                signal_id=event.signal_id,
                reason=event.event_reason,
                intent={"signal_id": event.signal_id},
            )

    def _append_status(
        self,
        signal_id: str,
        status: SignalLifecycleStatus,
        reason: str,
        ) -> SignalLifecycleEvent:
        with self._uow_factory() as uow:
            event = uow.signal_events.append_signal_event(
                _lifecycle_event(
                    signal_id=signal_id,
                    status=status,
                    reason=reason,
                )
            )
            uow.commit()
            return event
